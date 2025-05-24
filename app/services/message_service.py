# services/message_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.orm import selectinload, joinedload
from fastapi import HTTPException, status
from typing import List, Optional
from datetime import datetime
import uuid

from app.models.message import Message, MessageReaction, MessageReadReceipt, MessageStatus
from app.models.attachment import Attachment, FileType
from app.models.conversation import Conversation, Participant, ParticipantRole
from app.models.user import User
from app.models.settings import ConversationSettings
from app.schemas.message import (
    MessageCreate, MessageUpdate, MessageReactionCreate, 
    MessageResponse, MessagesResponse, AttachmentResponse,
    MessageReadReceiptUpdate, MessageReactionResponse
)

from app.core.exceptions import (
    NotFoundException, ForbiddenException, BadRequestException
)

from app.schemas.conversation import ParticipantResponse # Untuk relasi di MessageResponse

class MessageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_message(self, message_data: MessageCreate, sender_id: str) -> MessageResponse:
        participant_check = await self.db.execute(
            select(Participant).where(
                (Participant.conversation_id == message_data.conversation_id) &
                (Participant.user_id == sender_id)
            )
        )
        participant = participant_check.scalar_one_or_none()
        if not participant:
            raise ForbiddenException("User is not a participant of this conversation.")

        new_message = Message(
            conversation_id=message_data.conversation_id,
            sender_id=sender_id,
            content=message_data.content,
            message_type=message_data.message_type,
            reply_to_message_id=message_data.reply_to_message_id,
            client_message_id=message_data.client_message_id, 
            sent_at=datetime.utcnow(),
            status=MessageStatus.SENT
        )
        self.db.add(new_message)
        await self.db.commit()
        await self.db.refresh(new_message)

        sender_user = await self.db.execute(
            select(User).where(User.id == sender_id)
        )
        sender_user = sender_user.scalar_one_or_none()
        if not sender_user:
            raise NotFoundException("Sender user not found.")

        response = MessageResponse(
            id=str(new_message.id),
            conversation_id=str(new_message.conversation_id),
            sender_id=str(new_message.sender_id),
            sender_username=sender_user.username,
            sender_avatar=sender_user.profile_picture,
            content=new_message.content,
            message_type=new_message.message_type,
            reply_to_message_id=str(new_message.reply_to_message_id) if new_message.reply_to_message_id else None,
            status=new_message.status,
            is_deleted=new_message.is_deleted,
            is_edited=new_message.is_edited,
            sent_at=new_message.sent_at,
            edited_at=new_message.edited_at,
            deleted_at=new_message.deleted_at,
            attachments=[] 
        )
        return response
    
    # Anda juga perlu memastikan method lain seperti get_message dan get_messages_in_conversation
    # memuat sender_username dan sender_avatar. Ini biasanya dilakukan dengan joinedload() pada query SQLAlchemy.
    async def get_message(self, message_id: str, user_id: str) -> MessageResponse:
        # ... (implementasi yang sudah ada)
        # Pastikan query memuat informasi pengirim dan balasan jika ada
        result = await self.db.execute(
            select(Message)
            .options(
                joinedload(Message.sender), # Muat relasi sender
                joinedload(Message.reply_to).joinedload(Message.sender), # Muat pengirim pesan balasan
                selectinload(Message.attachments),
                selectinload(Message.reactions)
            )
            .where(Message.id == message_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            raise NotFoundException("Message not found.")

        # Cek apakah user adalah partisipan dari percakapan
        participant_check = await self.db.execute(
            select(Participant)
            .where(
                (Participant.conversation_id == message.conversation_id) &
                (Participant.user_id == user_id)
            )
        )
        if not participant_check.scalar_one_or_none():
            raise ForbiddenException("User not authorized to view this message.")

        return MessageResponse.model_validate(message) # Akan mengisi data dari model
    
    async def get_messages_in_conversation(
        self, conversation_id: str, user_id: str, page: int = 1, per_page: int = 50, before_message_id: Optional[str] = None
    ) -> MessagesResponse:
        # ... (implementasi yang sudah ada)
        # Pastikan query memuat informasi pengirim dan balasan jika ada
        
        # Contoh sederhana query tanpa before_message_id (Anda bisa mengadaptasi logika yang ada)
        base_query = select(Message).options(
            joinedload(Message.sender),
            joinedload(Message.reply_to).joinedload(Message.sender),
            selectinload(Message.attachments),
            selectinload(Message.reactions)
        ).where(Message.conversation_id == conversation_id)

        # Anda perlu memuat juga informasi pengirim untuk reaksi
        
        # ... (Logika pagination dan filter before_message_id)

        offset = (page - 1) * per_page
        messages_result = await self.db.execute(
            base_query.order_by(Message.sent_at.desc()) # Urutkan dari terbaru ke terlama
            .offset(offset)
            .limit(per_page)
        )
        messages = messages_result.scalars().all()

        total_messages_result = await self.db.execute(
            select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
        )
        total_messages = total_messages_result.scalar_one()

        has_more = (offset + len(messages)) < total_messages

        return MessagesResponse(
            messages=[MessageResponse.model_validate(m) for m in messages],
            total=total_messages,
            page=page,
            per_page=per_page,
            has_more=has_more
        )
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def update_message(self, message_id: str, message_data: MessageUpdate, user_id: str) -> MessageResponse:
        """Update a message (sender only)"""
        result = await self.db.execute(select(Message).where(Message.id == message_id))
        message = result.scalar_one_or_none()

        if not message or message.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found or deleted"
            )
        
        if message.sender_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the sender can edit this message"
            )
        
        message.content = message_data.content
        message.is_edited = True
        message.edited_at = datetime.utcnow()
        await self.db.commit()
        return await self.get_message(message_id, user_id)

    async def delete_message(self, message_id: str, user_id: str):
        """Soft delete a message (sender or conversation admin/moderator)"""
        result = await self.db.execute(select(Message).where(Message.id == message_id))
        message = result.scalar_one_or_none()

        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found"
            )
        
        # Check if user is sender or admin/moderator of the conversation
        is_sender = message.sender_id == user_id
        is_admin_mod = False
        
        participant_check = await self.db.execute(
            select(Participant.role).where(
                and_(Participant.conversation_id == message.conversation_id, Participant.user_id == user_id)
            )
        )
        participant_role = participant_check.scalar_one_or_none()

        if participant_role in [ParticipantRole.ADMIN, ParticipantRole.MODERATOR]:
            is_admin_mod = True
        
        if not is_sender and not is_admin_mod:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the sender or conversation admin/moderator can delete this message"
            )
        
        message.is_deleted = True
        message.deleted_at = datetime.utcnow()
        await self.db.commit()

    async def add_message_reaction(self, message_id: str, reaction_data: MessageReactionCreate, user_id: str) -> MessageReactionResponse:
        """Add a reaction to a message"""
        # Check if message exists and user is participant
        message = await self.db.execute(
            select(Message).where(Message.id == message_id)
        )
        message_obj = message.scalar_one_or_none()

        if not message_obj or message_obj.is_deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found or deleted")
        
        participant_check = await self.db.execute(
            select(Participant).where(
                and_(Participant.conversation_id == message_obj.conversation_id, Participant.user_id == user_id)
            )
        )
        if not participant_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a participant of this conversation"
            )

        # Check for existing reaction by same user and emoji
        existing_reaction_result = await self.db.execute(
            select(MessageReaction).where(and_(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == user_id,
                MessageReaction.emoji == reaction_data.emoji
            ))
        )
        if existing_reaction_result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reaction already exists")
        
        reaction_id = str(uuid.uuid4())
        reaction = MessageReaction(
            id=reaction_id,
            message_id=message_id,
            user_id=user_id,
            emoji=reaction_data.emoji
        )
        self.db.add(reaction)
        await self.db.commit()
        await self.db.refresh(reaction) # Refresh to load default values like created_at

        # Eager load user for response
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user_obj = user_result.scalar_one_or_none()
        if not user_obj:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User not found after reaction creation")
        
        return MessageReactionResponse(
            id=reaction.id,
            user_id=reaction.user_id,
            username=user_obj.username,
            emoji=reaction.emoji,
            created_at=reaction.created_at
        )

    async def remove_message_reaction(self, message_id: str, user_id: str, emoji: str):
        """Remove a reaction from a message"""
        result = await self.db.execute(
            select(MessageReaction).where(and_(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == user_id,
                MessageReaction.emoji == emoji
            ))
        )
        reaction = result.scalar_one_or_none()

        if not reaction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reaction not found")
        
        await self.db.delete(reaction)
        await self.db.commit()

    async def mark_messages_as_read(self, conversation_id: str, user_id: str, message_ids: List[str]):
        """Mark specific messages in a conversation as read by a user"""
        if not message_ids:
            return # Nothing to do

        # Verify user is a participant
        participant_check = await self.db.execute(
            select(Participant).where(
                and_(Participant.conversation_id == conversation_id, Participant.user_id == user_id)
            )
        )
        if not participant_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a participant of this conversation"
            )

        # Get existing read receipts for these messages and user
        existing_receipts_result = await self.db.execute(
            select(MessageReadReceipt).where(and_(
                MessageReadReceipt.message_id.in_(message_ids),
                MessageReadReceipt.user_id == user_id
            ))
        )
        existing_receipts = {r.message_id for r in existing_receipts_result.scalars().all()}

        new_receipts_added = 0
        for msg_id in message_ids:
            if msg_id not in existing_receipts:
                # Optional: Validate if message_id actually belongs to the conversation for robustness
                message_exists_in_conv = await self.db.scalar(
                    select(Message.id).where(and_(
                        Message.id == msg_id,
                        Message.conversation_id == conversation_id
                    ))
                )
                if message_exists_in_conv:
                    receipt = MessageReadReceipt(message_id=msg_id, user_id=user_id)
                    self.db.add(receipt)
                    new_receipts_added += 1
        
        if new_receipts_added > 0:
            await self.db.commit()
        
        # Update last_read_message_id in conversation_settings
        # Find the latest message ID among the marked as read messages
        latest_message_id_to_mark_read = None
        if message_ids:
            latest_message_result = await self.db.execute(
                select(Message)
                .where(Message.id.in_(message_ids))
                .order_by(desc(Message.sent_at))
                .limit(1)
            )
            latest_message = latest_message_result.scalar_one_or_none()
            if latest_message:
                latest_message_id_to_mark_read = latest_message.id

        if latest_message_id_to_mark_read:
            settings_result = await self.db.execute(
                select(ConversationSettings).where(and_(
                    ConversationSettings.conversation_id == conversation_id,
                    ConversationSettings.user_id == user_id
                ))
            )
            settings = settings_result.scalar_one_or_none()

            if settings:
                settings.last_read_message_id = latest_message_id_to_mark_read
                settings.updated_at = datetime.utcnow()
                self.db.add(settings)
            else:
                # Create new conversation settings if not exists
                new_settings = ConversationSettings(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    last_read_message_id=latest_message_id_to_mark_read,
                    is_muted=False, # Default values
                    is_pinned=False
                )
                self.db.add(new_settings)
            await self.db.commit()
            
            
            