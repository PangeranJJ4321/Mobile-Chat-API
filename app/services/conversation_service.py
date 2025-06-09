from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.orm import selectinload, joinedload
from fastapi import HTTPException, status
from typing import List, Optional
from datetime import datetime
import uuid

from app.models.conversation import Conversation, Participant, ParticipantRole
from app.models.user import User
from app.models.message import Message
from app.models.settings import ConversationSettings

from app.schemas.conversation import (
    ConversationCreate, ConversationUpdate, ConversationResponse,
    ConversationListResponse, ParticipantAdd, 
    ParticipantUpdate, 
    ParticipantResponse,
    ParticipantMuteUpdate
)

class ConversationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def update_participant_mute_status(self, conversation_id: str, participant_user_id: str, mute_data: ParticipantMuteUpdate, user_id: str):

        requesting_participant = await self._check_participant_permission(
            conversation_id, user_id, [ParticipantRole.ADMIN, ParticipantRole.MODERATOR, ParticipantRole.MEMBER]
        )
        
        if user_id != participant_user_id:
            # Jika user_id ingin mengubah status mute user lain, dia harus ADMIN
            if requesting_participant.role not in [ParticipantRole.ADMIN]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only change your own mute status unless you are an admin."
                )

        # Dapatkan objek Participant yang akan diupdate status mute-nya
        result = await self.db.execute(
            select(Participant).where(and_(
                Participant.conversation_id == conversation_id,
                Participant.user_id == participant_user_id
            ))
        )
        participant = result.scalar_one_or_none()

        if not participant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Participant not found in this conversation."
            )

        # Perbarui status is_muted
        participant.is_muted = mute_data.is_muted
        
        self.db.add(participant)
        await self.db.commit()
        await self.db.refresh(participant)

    async def create_conversation(self, conversation_data: ConversationCreate, creator_id: str) -> ConversationResponse:
        """Create a new conversation."""
        # Validate participants exist
        participant_ids = list(set(conversation_data.participant_ids))  # Remove duplicates
        if creator_id not in participant_ids:
            participant_ids.append(creator_id)

        result = await self.db.execute(select(User).where(User.id.in_(participant_ids)))
        users = result.scalars().all()

        if len(users) != len(participant_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more participants not found"
            )

        # For non-group conversations, check if conversation already exists
        if not conversation_data.is_group and len(participant_ids) == 2:
            existing = await self._find_direct_conversation(participant_ids[0], participant_ids[1])
            if existing:
                return await self.get_conversation(existing.id, creator_id)

        # Create conversation
        conversation = Conversation(
            id=str(uuid.uuid4()),
            name=conversation_data.name,
            description=conversation_data.description,
            is_group=conversation_data.is_group,
            avatar=conversation_data.avatar,
            created_by=creator_id
        )

        self.db.add(conversation)
        await self.db.flush()
        for user_id in participant_ids:
            role = ParticipantRole.ADMIN if user_id == creator_id else ParticipantRole.MEMBER
            participant = Participant(
                user_id=user_id,
                conversation_id=conversation.id,
                role=role
            )
            self.db.add(participant)

        await self.db.commit()
        await self.db.refresh(conversation, attribute_names=['participants'])
        return await self.get_conversation(conversation.id, creator_id)

    async def get_conversation(self, conversation_id: str, user_id: str) -> ConversationResponse:
        """Get conversation details"""
        participant_check = await self.db.execute(
            select(Participant).where(
                and_(Participant.conversation_id == conversation_id, Participant.user_id == user_id)
            )
        )
        if not participant_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a participant in this conversation"
            )

        result = await self.db.execute(
            select(Conversation)
            .options(
                selectinload(Conversation.participants).selectinload(Participant.user)
            )
            .where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        unread_count = await self._get_unread_count(conversation_id, user_id)

        last_message_result = await self.db.execute(
            select(Message)
            .where(and_(Message.conversation_id == conversation_id, Message.is_deleted == False))
            .order_by(desc(Message.sent_at))
            .limit(1)
        )
        last_message = last_message_result.scalar_one_or_none()

        participants = []
        for participant in conversation.participants:
            participants.append(ParticipantResponse(
                user_id=participant.user.id,
                username=participant.user.username,
                email=participant.user.email,
                role=participant.role,
                joined_at=participant.joined_at,
                last_seen_at=participant.last_seen_at,
                is_muted=participant.is_muted,
                is_pinned=participant.is_pinned,
                is_online=participant.user.is_online,
                profile_picture=participant.user.profile_picture
            ))

        return ConversationResponse(
            id=conversation.id,
            name=conversation.name,
            description=conversation.description,
            is_group=conversation.is_group,
            avatar=conversation.avatar,
            created_by=conversation.created_by,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            last_message_at=conversation.last_message_at,
            participants=participants,
            unread_count=unread_count,
            last_message=last_message.content if last_message else None
        )

    async def get_user_conversations(
        self,
        user_id: str,
        page: int = 1,
        per_page: int = 20,
        search_query: Optional[str] = None, # Parameter baru
        is_group_filter: Optional[bool] = None, # Parameter baru
        unread_only_filter: Optional[bool] = None # Parameter baru
    ) -> List[ConversationListResponse]:
        """Get user's conversations with pagination, search, and filters."""
        offset = (page - 1) * per_page

        # Base query to get conversations where user is a participant
        base_query = select(Conversation, Participant) \
            .join(Participant, Conversation.id == Participant.conversation_id) \
            .options(
                selectinload(Conversation.participants).selectinload(Participant.user)
            ) \
            .where(Participant.user_id == user_id)

        # Apply filters
        if is_group_filter is not None:
            base_query = base_query.where(Conversation.is_group == is_group_filter)

        if search_query:
            # Query untuk mencari berdasarkan nama grup ATAU username peserta lain (untuk chat pribadi)
            # Ini akan menjadi sedikit lebih kompleks karena kita perlu mencari di relasi.
            # Pendekatan: Menggunakan JOIN tambahan untuk mencari user di participant_ids
            # Untuk chat pribadi, `name` di Conversation seringkali NULL, jadi kita cari di username participant.
            # Untuk grup chat, `name` di Conversation yang relevan.
            search_pattern = f"%{search_query.lower()}%"

            # Kita perlu mencari di Conversation.name (untuk grup)
            # Atau di User.username dari participant (untuk private/group jika nama grup tidak ada)
            # Subquery untuk menemukan conversation_ids yang match dengan username peserta
            participant_search_subquery = select(Participant.conversation_id) \
                .join(User, Participant.user_id == User.id) \
                .where(func.lower(User.username).like(search_pattern)) \
                .scalar_subquery() # Mengembalikan subquery yang menghasilkan satu kolom

            base_query = base_query.where(
                or_(
                    func.lower(Conversation.name).like(search_pattern),
                    Conversation.id.in_(participant_search_subquery)
                )
            )

        # Execute the query to get the main conversation list
        # Sorting is applied after filtering for efficiency
        result = await self.db.execute(
            base_query.order_by(desc(Conversation.last_message_at))
            .offset(offset)
            .limit(per_page)
        )

        conversations_data = result.unique().all()
        conversations_list_response = []

        for conversation, user_participant in conversations_data:
            # Calculate unread count for current conversation
            current_unread_count = await self._get_unread_count(conversation.id, user_id)

            # Apply unread_only_filter here, as _get_unread_count is an async operation
            if unread_only_filter and current_unread_count == 0:
                continue # Skip this conversation if filter is true and no unread messages

            # Get participant count
            participant_count_result = await self.db.execute(
                select(func.count(Participant.user_id))
                .where(Participant.conversation_id == conversation.id)
            )
            participant_count = participant_count_result.scalar()

            # Get last message with sender info
            last_message_result = await self.db.execute(
                select(Message, User)
                .join(User, Message.sender_id == User.id)
                .where(and_(Message.conversation_id == conversation.id, Message.is_deleted == False))
                .order_by(desc(Message.sent_at))
                .limit(1)
            )
            last_message_data = last_message_result.first()

            last_message = None
            last_message_sender = None
            if last_message_data:
                message, sender = last_message_data
                last_message = message.content
                last_message_sender = sender.username

            display_name = conversation.name
            display_avatar = conversation.avatar
            other_participant_id = None
            other_participant_username = None
            other_participant_avatar = None
            other_participant_email = None 

            if not conversation.is_group:
                for p in conversation.participants:
                    if p.user_id != user_id:
                        other_participant_id = p.user.id
                        display_name = p.user.username
                        display_avatar = p.user.profile_picture
                        other_participant_username = p.user.username
                        other_participant_avatar = p.user.profile_picture
                        other_participant_email = p.user.email
                        break

            conversations_list_response.append(ConversationListResponse(
                id=conversation.id,
                name=display_name,
                is_group=conversation.is_group,
                avatar=display_avatar,
                created_at=conversation.created_at,
                last_message_at=conversation.last_message_at,
                unread_count=current_unread_count, # Menggunakan unread count yang sudah dihitung
                last_message=last_message,
                last_message_sender=last_message_sender,
                participants_count=participant_count,
                is_muted=user_participant.is_muted,
                is_pinned=user_participant.is_pinned,
                other_participant_id=other_participant_id,
                other_participant_username=other_participant_username,
                other_participant_avatar=other_participant_avatar,
                other_participant_email=other_participant_email
            ))

        return conversations_list_response

    async def update_conversation(self, conversation_id: str, conversation_data: ConversationUpdate, user_id: str) -> ConversationResponse:
        """Update conversation (admin/moderator only)"""
        participant = await self._check_participant_permission(conversation_id, user_id, [ParticipantRole.ADMIN, ParticipantRole.MODERATOR])

        result = await self.db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        if conversation_data.name is not None:
            conversation.name = conversation_data.name
        if conversation_data.description is not None:
            conversation.description = conversation_data.description
        if conversation_data.avatar is not None:
            conversation.avatar = conversation_data.avatar

        conversation.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(conversation)

        return await self.get_conversation(conversation_id, user_id)

    async def delete_conversation(self, conversation_id: str, user_id: str):
        """Delete conversation (creator only)"""
        result = await self.db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        if conversation.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only conversation creator can delete it"
            )

        await self.db.delete(conversation)
        await self.db.commit()

    async def add_participants(self, conversation_id: str, participant_data: ParticipantAdd, user_id: str):
        """Add participants to conversation (admin/moderator only)"""
        participant = await self._check_participant_permission(conversation_id, user_id, [ParticipantRole.ADMIN, ParticipantRole.MODERATOR])

        conversation_result = await self.db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conversation = conversation_result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        if not conversation.is_group:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot add participants to a non-group conversation. Please create a new group chat instead."
            )
        result = await self.db.execute(select(User).where(User.id.in_(participant_data.user_ids)))
        users = result.scalars().all()

        if len(users) != len(participant_data.user_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more users not found"
            )

        existing_result = await self.db.execute(
            select(Participant.user_id)
            .where(and_(
                Participant.conversation_id == conversation_id,
                Participant.user_id.in_(participant_data.user_ids)
            ))
        )
        existing_user_ids = set(existing_result.scalars().all())

        for new_user_id in participant_data.user_ids:
            if new_user_id not in existing_user_ids:
                participant_to_add = Participant(
                    user_id=new_user_id,
                    conversation_id=conversation_id,
                    role=ParticipantRole.MEMBER
                )
                self.db.add(participant_to_add)

        await self.db.commit()

    async def remove_participant(self, conversation_id: str, participant_user_id: str, user_id: str):
        """Remove participant from conversation"""
        current_participant = await self._check_participant_permission(
            conversation_id, user_id, [ParticipantRole.ADMIN, ParticipantRole.MODERATOR]
        )

        result = await self.db.execute(
            select(Participant).where(and_(
                Participant.conversation_id == conversation_id,
                Participant.user_id == participant_user_id
            ))
        )
        participant_to_remove = result.scalar_one_or_none()

        if not participant_to_remove:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Participant not found"
            )

        if participant_to_remove.role == ParticipantRole.ADMIN and current_participant.role != ParticipantRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot remove admin"
            )

        await self.db.delete(participant_to_remove)
        await self.db.commit()

    async def update_participant_role(self, conversation_id: str, participant_user_id: str, role_data: ParticipantUpdate, user_id: str):
        """Update participant role (admin only)"""
        await self._check_participant_permission(conversation_id, user_id, [ParticipantRole.ADMIN])

        result = await self.db.execute(
            select(Participant).where(and_(
                Participant.conversation_id == conversation_id,
                Participant.user_id == participant_user_id
            ))
        )
        participant = result.scalar_one_or_none()

        if not participant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Participant not found"
            )

        participant.role = role_data.role
        await self.db.commit()
        await self.db.refresh(participant)

    async def leave_conversation(self, conversation_id: str, user_id: str):
        """Leave conversation"""
        result = await self.db.execute(
            select(Participant).where(and_(
                Participant.conversation_id == conversation_id,
                Participant.user_id == user_id
            ))
        )
        participant = result.scalar_one_or_none()

        if not participant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Not a participant in this conversation"
            )

        await self.db.delete(participant)
        await self.db.commit()

    async def _find_direct_conversation(self, user1_id: str, user2_id: str) -> Optional[Conversation]:
        """Find existing direct conversation between two users"""
        result = await self.db.execute(
            select(Conversation)
            .options(joinedload(Conversation.participants))
            .join(Participant, Conversation.id == Participant.conversation_id)
            .where(and_(
                Conversation.is_group == False,
                or_(
                    Participant.user_id == user1_id,
                    Participant.user_id == user2_id
                )
            ))
            .group_by(Conversation.id)
            .having(func.count(Participant.user_id) == 2)
        )

        conversations = result.unique().scalars().all()

        for conv in conversations:
            participant_ids = [p.user_id for p in conv.participants]
            if set(participant_ids) == {user1_id, user2_id}:
                return conv
        return None

    async def _get_unread_count(self, conversation_id: str, user_id: str) -> int:
        """Get unread message count for user in conversation"""
        settings_result = await self.db.execute(
            select(ConversationSettings).where(and_(
                ConversationSettings.conversation_id == conversation_id,
                ConversationSettings.user_id == user_id
            ))
        )
        settings = settings_result.scalar_one_or_none()

        # Dapatkan pesan terakhir yang dikirim oleh user ini di percakapan ini
        # Ini penting untuk skenario jika last_read_message_id belum ada atau ada tapi menunjuk ke pesan yang dihapus
        # atau pesan lama. Kita perlu batas bawah yang "aman" yaitu pesan terakhir yang dikirim sendiri.
        last_sent_message_by_user_result = await self.db.execute(
            select(Message.sent_at)
            .where(and_(
                Message.conversation_id == conversation_id,
                Message.sender_id == user_id,
                Message.is_deleted == False
            ))
            .order_by(desc(Message.sent_at))
            .limit(1)
        )
        last_sent_message_time_by_user = last_sent_message_by_user_result.scalar_one_or_none()

        last_read_time_for_unread_calc = None

        if settings and settings.last_read_message_id:
            last_read_message_time_result = await self.db.execute(
                select(Message.sent_at).where(Message.id == settings.last_read_message_id)
            )
            last_read_time_from_settings = last_read_message_time_result.scalar_one_or_none()

            # Pilih waktu terbaca yang paling baru antara setting user dan pesan terakhir yang dikirim sendiri
            if last_read_time_from_settings and last_sent_message_time_by_user:
                last_read_time_for_unread_calc = max(last_read_time_from_settings, last_sent_message_time_by_user)
            elif last_read_time_from_settings:
                last_read_time_for_unread_calc = last_read_time_from_settings
            elif last_sent_message_time_by_user:
                last_read_time_for_unread_calc = last_sent_message_time_by_user
            # Jika keduanya None, last_read_time_for_unread_calc tetap None
        else:
            # Jika tidak ada setting, gunakan waktu pesan terakhir yang dikirim sendiri sebagai batas bawah
            last_read_time_for_unread_calc = last_sent_message_time_by_user
        
        # Sekarang hitung pesan yang belum dibaca:
        # Pesan yang lebih baru dari last_read_time_for_unread_calc
        # DAN BUKAN dari user_id yang sedang dihitung
        # DAN tidak dihapus
        if last_read_time_for_unread_calc:
            result = await self.db.execute(
                select(func.count(Message.id))
                .where(and_(
                    Message.conversation_id == conversation_id,
                    Message.sent_at > last_read_time_for_unread_calc,
                    Message.is_deleted == False,
                    Message.sender_id != user_id # <--- INI PENTING: Mengecualikan pesan sendiri
                ))
            )
            return result.scalar() or 0
        else:
            # Jika tidak ada last_read_time_for_unread_calc (misal, percakapan baru, user belum kirim/terima pesan)
            # Hitung semua pesan yang bukan dari user ini
            result = await self.db.execute(
                select(func.count(Message.id))
                .where(and_(
                    Message.conversation_id == conversation_id,
                    Message.is_deleted == False,
                    Message.sender_id != user_id # <--- INI PENTING: Mengecualikan pesan sendiri
                ))
            )
            return result.scalar() or 0

    async def _check_participant_permission(self, conversation_id: str, user_id: str, required_roles: List[ParticipantRole]) -> Participant:
        """Check if user has required permission in conversation"""
        result = await self.db.execute(
            select(Participant).where(and_(
                Participant.conversation_id == conversation_id,
                Participant.user_id == user_id
            ))
        )
        participant = result.scalar_one_or_none()

        if not participant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a participant in this conversation"
            )

        if participant.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )

        return participant
    

    async def get_user_conversation_list_response(self, conversation_id: str, user_id: str) -> Optional[ConversationListResponse]:
        """
        Fetches a single ConversationListResponse object for a given conversation_id and user_id.
        This is useful for Pusher updates.
        """
        # Base query to get the specific conversation where user is a participant
        base_query = select(Conversation, Participant) \
            .join(Participant, Conversation.id == Participant.conversation_id) \
            .options(
                selectinload(Conversation.participants).selectinload(Participant.user)
            ) \
            .where(and_(Conversation.id == conversation_id, Participant.user_id == user_id))

        result = await self.db.execute(base_query)
        conversation_data = result.unique().first() # Use first() since we expect one result

        if not conversation_data:
            # User is not a participant or conversation not found
            return None

        conversation, user_participant = conversation_data

        # Calculate unread count for current conversation
        current_unread_count = await self._get_unread_count(conversation.id, user_id)

        # Get participant count
        participant_count_result = await self.db.execute(
            select(func.count(Participant.user_id))
            .where(Participant.conversation_id == conversation.id)
        )
        participant_count = participant_count_result.scalar()

        # Get last message with sender info
        last_message_result = await self.db.execute(
            select(Message, User)
            .join(User, Message.sender_id == User.id)
            .where(and_(Message.conversation_id == conversation.id, Message.is_deleted == False))
            .order_by(desc(Message.sent_at))
            .limit(1)
        )
        last_message_data = last_message_result.first()

        last_message_content = None
        last_message_sender_username = None
        if last_message_data:
            message, sender = last_message_data
            last_message_content = message.content
            last_message_sender_username = sender.username

        display_name = conversation.name
        display_avatar = conversation.avatar
        other_participant_id = None
        other_participant_username = None
        other_participant_avatar = None
        other_participant_email = None

        if not conversation.is_group:
            for p in conversation.participants:
                if p.user_id != user_id:
                    other_participant_id = p.user.id
                    display_name = p.user.username
                    display_avatar = p.user.profile_picture
                    other_participant_username = p.user.username
                    other_participant_avatar = p.user.profile_picture
                    other_participant_email = p.user.email
                    break
        
        # Build and return the ConversationListResponse
        return ConversationListResponse(
            id=conversation.id,
            name=display_name,
            is_group=conversation.is_group,
            avatar=display_avatar,
            created_at=conversation.created_at,
            last_message_at=conversation.last_message_at,
            unread_count=current_unread_count,
            last_message=last_message_content,
            last_message_sender=last_message_sender_username,
            participants_count=participant_count,
            is_muted=user_participant.is_muted,
            is_pinned=user_participant.is_pinned,
            other_participant_id=other_participant_id,
            other_participant_username=other_participant_username,
            other_participant_avatar=other_participant_avatar,
            other_participant_email=other_participant_email
        )
