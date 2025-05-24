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
    ConversationListResponse, ParticipantAdd, ParticipantUpdate, ParticipantResponse
)

class ConversationService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_conversation(self, conversation_data: ConversationCreate, creator_id: str) -> ConversationResponse:
        """Create a new conversation"""
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
        await self.db.flush() # Flush to get conversation.id for participants
        
        # Add participants
        for user_id in participant_ids:
            role = ParticipantRole.ADMIN if user_id == creator_id else ParticipantRole.MEMBER
            participant = Participant(
                user_id=user_id,
                conversation_id=conversation.id,
                role=role
            )
            self.db.add(participant)
        
        await self.db.commit()
        # Refresh conversation to load new participants relationship
        await self.db.refresh(conversation, attribute_names=['participants'])
        return await self.get_conversation(conversation.id, creator_id) # Call get_conversation to get full response
    
    async def get_conversation(self, conversation_id: str, user_id: str) -> ConversationResponse:
        """Get conversation details"""
        # Check if user is participant
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
        
        # Get conversation with participants
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
        
        # Get unread count for current user
        unread_count = await self._get_unread_count(conversation_id, user_id)
        
        # Get last message
        last_message_result = await self.db.execute(
            select(Message)
            .where(and_(Message.conversation_id == conversation_id, Message.is_deleted == False))
            .order_by(desc(Message.sent_at))
            .limit(1)
        )
        last_message = last_message_result.scalar_one_or_none()
        
        # Build participants response
        participants = []
        for participant in conversation.participants:
            participants.append(ParticipantResponse(
                user_id=participant.user.id,
                username=participant.user.username,
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
    
    async def get_user_conversations(self, user_id: str, page: int = 1, per_page: int = 20) -> List[ConversationListResponse]:
        """Get user's conversations with pagination"""
        offset = (page - 1) * per_page
        
        # Get conversations where user is participant
        result = await self.db.execute(
            select(Conversation, Participant)
            .join(Participant, Conversation.id == Participant.conversation_id)
            .where(Participant.user_id == user_id)
            .order_by(desc(Conversation.last_message_at))
            .offset(offset)
            .limit(per_page)
        )
        
        conversations_data = result.all()
        conversations = []
        
        for conversation, user_participant in conversations_data:
            # Get participant count
            participant_count_result = await self.db.execute(
                select(func.count(Participant.user_id))
                .where(Participant.conversation_id == conversation.id)
            )
            participant_count = participant_count_result.scalar()
            
            # Get unread count
            unread_count = await self._get_unread_count(conversation.id, user_id)
            
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
            
            conversations.append(ConversationListResponse(
                id=conversation.id,
                name=conversation.name,
                is_group=conversation.is_group,
                avatar=conversation.avatar,
                created_at=conversation.created_at,
                last_message_at=conversation.last_message_at,
                unread_count=unread_count,
                last_message=last_message,
                last_message_sender=last_message_sender,
                participants_count=participant_count,
                is_muted=user_participant.is_muted,
                is_pinned=user_participant.is_pinned
            ))
        
        return conversations
    
    async def update_conversation(self, conversation_id: str, conversation_data: ConversationUpdate, user_id: str) -> ConversationResponse:
        """Update conversation (admin/moderator only)"""
        # Check permissions
        participant = await self._check_participant_permission(conversation_id, user_id, [ParticipantRole.ADMIN, ParticipantRole.MODERATOR])
        
        # Get conversation
        result = await self.db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        # Update fields
        if conversation_data.name is not None:
            conversation.name = conversation_data.name
        if conversation_data.description is not None:
            conversation.description = conversation_data.description
        if conversation_data.avatar is not None:
            conversation.avatar = conversation_data.avatar
        
        conversation.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(conversation) # Refresh the object after commit
        
        return await self.get_conversation(conversation_id, user_id)
    
    async def delete_conversation(self, conversation_id: str, user_id: str):
        """Delete conversation (creator only)"""
        # Get conversation
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
        # Check permissions
        await self._check_participant_permission(conversation_id, user_id, [ParticipantRole.ADMIN, ParticipantRole.MODERATOR])
        
        # Validate new participants exist
        result = await self.db.execute(select(User).where(User.id.in_(participant_data.user_ids)))
        users = result.scalars().all()
        
        if len(users) != len(participant_data.user_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more users not found"
            )
        
        # Check if users are already participants
        existing_result = await self.db.execute(
            select(Participant.user_id)
            .where(and_(
                Participant.conversation_id == conversation_id,
                Participant.user_id.in_(participant_data.user_ids)
            ))
        )
        existing_user_ids = set(existing_result.scalars().all())
        
        # Add new participants
        for user_id in participant_data.user_ids:
            if user_id not in existing_user_ids:
                participant = Participant(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    role=ParticipantRole.MEMBER
                )
                self.db.add(participant)
        
        await self.db.commit()
    
    async def remove_participant(self, conversation_id: str, participant_user_id: str, user_id: str):
        """Remove participant from conversation"""
        # Check if user can remove participant
        current_participant = await self._check_participant_permission(
            conversation_id, user_id, [ParticipantRole.ADMIN, ParticipantRole.MODERATOR]
        )
        
        # Get participant to remove
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
        
        # Can't remove admin unless you're admin
        if participant_to_remove.role == ParticipantRole.ADMIN and current_participant.role != ParticipantRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot remove admin"
            )
        
        await self.db.delete(participant_to_remove)
        await self.db.commit()
    
    async def update_participant_role(self, conversation_id: str, participant_user_id: str, role_data: ParticipantUpdate, user_id: str):
        """Update participant role (admin only)"""
        # Check permissions (admin only)
        await self._check_participant_permission(conversation_id, user_id, [ParticipantRole.ADMIN])
        
        # Get participant
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
        await self.db.refresh(participant) # Refresh to reflect changes
    
    async def leave_conversation(self, conversation_id: str, user_id: str):
        """Leave conversation"""
        # Get participant
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
    
    # Helper methods
    async def _find_direct_conversation(self, user1_id: str, user2_id: str) -> Optional[Conversation]:
        """Find existing direct conversation between two users"""

        # Muat relasi participants juga yaa sayang
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
        # Get user's last read message from conversation_settings
        settings_result = await self.db.execute(
            select(ConversationSettings).where(and_(
                ConversationSettings.conversation_id == conversation_id,
                ConversationSettings.user_id == user_id
            ))
        )
        settings = settings_result.scalar_one_or_none()
        
        if not settings or not settings.last_read_message_id:
            # Count all messages in conversation if no last_read_message_id
            result = await self.db.execute(
                select(func.count(Message.id))
                .where(and_(
                    Message.conversation_id == conversation_id,
                    Message.is_deleted == False
                ))
            )
            return result.scalar() or 0
        
        # Find the sent_at timestamp of the last read message
        last_read_message_time_result = await self.db.execute(
            select(Message.sent_at).where(Message.id == settings.last_read_message_id)
        )
        last_read_time = last_read_message_time_result.scalar_one_or_none()
        
        if not last_read_time:
            # If last read message not found, count all
            result = await self.db.execute(
                select(func.count(Message.id))
                .where(and_(
                    Message.conversation_id == conversation_id,
                    Message.is_deleted == False
                ))
            )
            return result.scalar() or 0
        
        # Count messages sent after the last read message
        result = await self.db.execute(
            select(func.count(Message.id))
            .where(and_(
                Message.conversation_id == conversation_id,
                Message.sent_at > last_read_time,
                Message.is_deleted == False
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