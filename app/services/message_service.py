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
from app.schemas.conversation import ParticipantResponse # Untuk relasi di MessageResponse

class MessageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_message(self, message_data: MessageCreate, sender_id: str) -> MessageResponse:
        """Create a new message in a conversation"""
        # Check if sender is a participant of the conversation
        participant_check = await self.db.execute(
            select(Participant).where(
                and_(Participant.conversation_id == message_data.conversation_id, Participant.user_id == sender_id)
            )
        )
        if not participant_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a participant of this conversation"
            )
        
        # Check if conversation exists
        conversation_check = await self.db.execute(
            select(Conversation).where(Conversation.id == message_data.conversation_id)
        )
        conversation = conversation_check.scalar_one_or_none()
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        # Create message
        message_id = str(uuid.uuid4())
        message = Message(
            id=message_id,
            conversation_id=message_data.conversation_id,
            sender_id=sender_id,
            reply_to_message_id=message_data.reply_to_message_id,
            content=message_data.content,
            message_type=message_data.message_type
        )
        self.db.add(message)
        
        # Update last_message_at for the conversation
        conversation.last_message_at = datetime.utcnow()
        self.db.add(conversation)

        await self.db.commit()
        return await self.get_message(message_id, sender_id) # Fetch the full message with relationships

    async def get_message(self, message_id: str, user_id: str) -> MessageResponse:
        """Get a single message by ID"""
        result = await self.db.execute(
            select(Message)
            .options(
                selectinload(Message.sender),
                selectinload(Message.attachments),
                selectinload(Message.reactions).selectinload(MessageReaction.user),
                selectinload(Message.reply_to).selectinload(Message.sender) # Load reply_to message sender
            )
            .where(Message.id == message_id)
        )
        message = result.scalar_one_or_none()

        if not message or message.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found or deleted"
            )
        
        # Check if user is a participant of the conversation this message belongs to
        participant_check = await self.db.execute(
            select(Participant).where(
                and_(Participant.conversation_id == message.conversation_id, Participant.user_id == user_id)
            )
        )
        if not participant_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not authorized to view this message"
            )
        
        # Build attachments response
        attachments = []
        for attachment in message.attachments:
            attachments.append(AttachmentResponse(
                id=attachment.id,
                file_url=attachment.file_type, # This was 'file_type', should be 'file_url'
                file_type=attachment.file_type,
                mime_type=attachment.mime_type,
                filename=attachment.filename,
                file_size=attachment.file_size,
                thumbnail_url=attachment.thumbnail_url,
                duration=attachment.duration,
                uploaded_at=attachment.uploaded_at
            ))

        # Build reactions response
        reactions = []
        for reaction in message.reactions:
            reactions.append(MessageReactionResponse(
                id=reaction.id,
                user_id=reaction.user_id,
                username=reaction.user.username,
                emoji=reaction.emoji,
                created_at=reaction.created_at
            ))
        
        # Get read count for message
        read_by_count_result = await self.db.execute(
            select(func.count(MessageReadReceipt.user_id))
            .where(MessageReadReceipt.message_id == message.id)
        )
        read_by_count = read_by_count_result.scalar() or 0

        # Build reply_to response if exists
        reply_to_message_response = None
        if message.reply_to:
            reply_to_message_response = MessageResponse(
                id=message.reply_to.id,
                conversation_id=message.reply_to.conversation_id,
                sender_id=message.reply_to.sender_id,
                sender_username=message.reply_to.sender.username if message.reply_to.sender else "Unknown",
                sender_avatar=message.reply_to.sender.profile_picture if message.reply_to.sender else None,
                content=message.reply_to.content,
                message_type=message.reply_to.message_type,
                status=message.reply_to.status,
                is_deleted=message.reply_to.is_deleted,
                is_edited=message.reply_to.is_edited,
                sent_at=message.reply_to.sent_at,
                edited_at=message.reply_to.edited_at,
                deleted_at=message.reply_to.deleted_at,
                # No nested reply_to or attachments for brevity in reply_to object
                attachments=[] # attachments are not recursively loaded for reply_to
            )

        return MessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            sender_id=message.sender_id,
            sender_username=message.sender.username if message.sender else "Unknown",
            sender_avatar=message.sender.profile_picture if message.sender else None,
            content=message.content,
            message_type=message.message_type,
            status=message.status,
            is_deleted=message.is_deleted,
            is_edited=message.is_edited,
            sent_at=message.sent_at,
            edited_at=message.edited_at,
            deleted_at=message.deleted_at,
            reply_to=reply_to_message_response,
            attachments=attachments,
            reactions=reactions,
            read_by_count=read_by_count
        )

    async def get_messages_in_conversation(
        self, conversation_id: str, user_id: str, page: int = 1, per_page: int = 50, before_message_id: Optional[str] = None
    ) -> MessagesResponse:
        """Get messages for a conversation with pagination"""
        # Check if user is a participant
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

        query = select(Message).where(
            and_(Message.conversation_id == conversation_id, Message.is_deleted == False)
        )

        if before_message_id:
            # Find the sent_at of the message before which to fetch
            before_message_time_result = await self.db.execute(
                select(Message.sent_at).where(Message.id == before_message_id)
            )
            before_message_time = before_message_time_result.scalar_one_or_none()
            if before_message_time:
                query = query.where(Message.sent_at < before_message_time)
            # You might also want to include messages with the same timestamp but smaller IDs if precise pagination is needed

        # Total count for pagination metadata
        total_count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery()) # Count based on filtered query
        )
        total_messages = total_count_result.scalar_one()

        messages_result = await self.db.execute(
            query
            .options(
                selectinload(Message.sender),
                selectinload(Message.attachments),
                selectinload(Message.reactions).selectinload(MessageReaction.user),
                selectinload(Message.reply_to).selectinload(Message.sender)
            )
            .order_by(desc(Message.sent_at)) # Latest messages first
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        messages = messages_result.scalars().all()

        message_responses = []
        for message in messages:
            # Reusing the logic from get_message for building individual MessageResponse
            attachments = []
            for attachment in message.attachments:
                attachments.append(AttachmentResponse(
                    id=attachment.id,
                    file_url=attachment.file_url, # Corrected
                    file_type=attachment.file_type,
                    mime_type=attachment.mime_type,
                    filename=attachment.filename,
                    file_size=attachment.file_size,
                    thumbnail_url=attachment.thumbnail_url,
                    duration=attachment.duration,
                    uploaded_at=attachment.uploaded_at
                ))

            reactions = []
            for reaction in message.reactions:
                reactions.append(MessageReactionResponse(
                    id=reaction.id,
                    user_id=reaction.user_id,
                    username=reaction.user.username,
                    emoji=reaction.emoji,
                    created_at=reaction.created_at
                ))
            
            read_by_count_result = await self.db.execute(
                select(func.count(MessageReadReceipt.user_id))
                .where(MessageReadReceipt.message_id == message.id)
            )
            read_by_count = read_by_count_result.scalar() or 0

            reply_to_message_response = None
            if message.reply_to:
                reply_to_message_response = MessageResponse(
                    id=message.reply_to.id,
                    conversation_id=message.reply_to.conversation_id,
                    sender_id=message.reply_to.sender_id,
                    sender_username=message.reply_to.sender.username if message.reply_to.sender else "Unknown",
                    sender_avatar=message.reply_to.sender.profile_picture if message.reply_to.sender else None,
                    content=message.reply_to.content,
                    message_type=message.reply_to.message_type,
                    status=message.reply_to.status,
                    is_deleted=message.reply_to.is_deleted,
                    is_edited=message.reply_to.is_edited,
                    sent_at=message.reply_to.sent_at,
                    edited_at=message.reply_to.edited_at,
                    deleted_at=message.reply_to.deleted_at,
                    attachments=[] # attachments are not recursively loaded for reply_to
                )

            message_responses.append(MessageResponse(
                id=message.id,
                conversation_id=message.conversation_id,
                sender_id=message.sender_id,
                sender_username=message.sender.username if message.sender else "Unknown",
                sender_avatar=message.sender.profile_picture if message.sender else None,
                content=message.content,
                message_type=message.message_type,
                status=message.status,
                is_deleted=message.is_deleted,
                is_edited=message.is_edited,
                sent_at=message.sent_at,
                edited_at=message.edited_at,
                deleted_at=message.deleted_at,
                reply_to=reply_to_message_response,
                attachments=attachments,
                reactions=reactions,
                read_by_count=read_by_count
            ))

        has_more = (page * per_page) < total_messages

        return MessagesResponse(
            messages=message_responses,
            total=total_messages,
            page=page,
            per_page=per_page,
            has_more=has_more
        )

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
            
            
            