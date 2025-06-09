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
            status=MessageStatus.SENT # Status awal pesan yang baru dikirim adalah SENT
        )
        self.db.add(new_message)
        await self.db.commit()
        await self.db.refresh(new_message)

        # MUAT RELASI UNTUK RESPONSE, TANPA read_receipts DI SINI
        # read_by_count akan diisi 0 secara default atau dari Pydantic jika tidak ada kolom.
        load_options = [
            joinedload(Message.sender),
            selectinload(Message.attachments),
            selectinload(Message.reactions)
            # selectinload(Message.read_receipts) TIDAK PERLU DI SINI, karena kita tidak menghitung read_by_count awal
        ]

        if new_message.reply_to_message_id:
            load_options.append(joinedload(Message.reply_to).joinedload(Message.sender))

        loaded_message_result = await self.db.execute(
            select(Message)
            .options(*load_options)
            .where(Message.id == new_message.id)
        )
        new_message = loaded_message_result.scalar_one()

        # Update last_read_message_id di ConversationSettings untuk pengirim
        # Logika ini terpisah dari status "dibaca oleh penerima"
        settings_result = await self.db.execute(
            select(ConversationSettings).where(
                and_(
                    ConversationSettings.conversation_id == new_message.conversation_id,
                    ConversationSettings.user_id == sender_id
                )
            )
        )
        settings = settings_result.scalar_one_or_none()

        if settings:
            # Hanya perbarui jika pesan yang baru dikirim lebih baru dari last_read_message_id sebelumnya
            last_read_message_obj = await self.db.scalar(
                select(Message).where(Message.id == settings.last_read_message_id)
            )
            if settings.last_read_message_id is None or (last_read_message_obj and new_message.sent_at > last_read_message_obj.sent_at):
                 settings.last_read_message_id = new_message.id
                 settings.updated_at = datetime.utcnow()
                 self.db.add(settings)
            elif not last_read_message_obj: # Jika ID ada tapi pesan tidak ditemukan
                 settings.last_read_message_id = new_message.id
                 settings.updated_at = datetime.utcnow()
                 self.db.add(settings)
        else:
            new_settings = ConversationSettings(
                user_id=sender_id,
                conversation_id=new_message.conversation_id,
                last_read_message_id=new_message.id,
                is_muted=False,
                is_pinned=False
            )
            self.db.add(new_settings)
        
        await self.db.commit() # Commit perubahan settings

        response = MessageResponse.model_validate(new_message)
        # Pastikan read_by_count adalah 0 secara eksplisit untuk pesan yang baru dikirim
        # (sebelum ada penerima yang membaca)
        response.read_by_count = 0
        return response

    async def get_message(self, message_id: str, user_id: str) -> MessageResponse:
        result = await self.db.execute(
            select(Message)
            .options(
                joinedload(Message.sender),
                joinedload(Message.reply_to).joinedload(Message.sender),
                selectinload(Message.attachments),
                selectinload(Message.reactions).joinedload(MessageReaction.user),
                selectinload(Message.read_receipts) # Load read receipts untuk penghitungan
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
        
        response = MessageResponse.model_validate(message)
        # Hitung read_by_count: jumlah receipt dari pengguna yang BUKAN pengirimnya
        response.read_by_count = sum(1 for rr in message.read_receipts if str(rr.user_id) != str(message.sender_id))
        
        return response

    async def get_messages_in_conversation(
        self, conversation_id: str, user_id: str, page: int = 1, per_page: int = 50, before_message_id: Optional[str] = None
    ) -> MessagesResponse:
        # Check if user is a participant of the conversation
        participant_check = await self.db.execute(
            select(Participant).where(
                (Participant.conversation_id == conversation_id) &
                (Participant.user_id == user_id)
            )
        )
        if not participant_check.scalar_one_or_none():
            raise ForbiddenException("User is not a participant of this conversation.")

        base_query = select(Message).options(
            joinedload(Message.sender),
            joinedload(Message.reply_to).joinedload(Message.sender),
            selectinload(Message.attachments),
            selectinload(Message.reactions).joinedload(MessageReaction.user),
            selectinload(Message.read_receipts) # PASTIKAN INI ADA untuk menghitung read_by_count
        ).where(Message.conversation_id == conversation_id)

        base_query = base_query.where(Message.is_deleted == False)

        if before_message_id:
            before_message_obj = await self.db.execute(
                select(Message.sent_at).where(Message.id == before_message_id)
            )
            before_sent_at = before_message_obj.scalar_one_or_none()

            if before_sent_at:
                base_query = base_query.where(Message.sent_at < before_sent_at)
            else:
                pass # Jika before_message_id tidak valid, tidak ada filter tambahan

        total_messages_query = select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
        total_messages_query = total_messages_query.where(Message.is_deleted == False)

        total_messages_result = await self.db.execute(total_messages_query)
        total_messages = total_messages_result.scalar_one()

        query = base_query.order_by(Message.sent_at.desc())

        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        messages_result = await self.db.execute(query)
        messages = messages_result.scalars().all()

        has_more = (offset + len(messages)) < total_messages

        message_responses = []
        for m in messages:
            msg_res = MessageResponse.model_validate(m)
            # Hitung read_by_count secara manual dari relasi yang dimuat
            # Filter read_receipts untuk user_id yang BUKAN pengirimnya sendiri
            msg_res.read_by_count = sum(1 for rr in m.read_receipts if str(rr.user_id) != str(m.sender_id))
            message_responses.append(msg_res)

        return MessagesResponse(
            messages=message_responses,
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
        result = await self.db.execute(select(Message).options(joinedload(Message.sender)).where(Message.id == message_id))
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
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return MessageResponse.model_validate(message)

    async def delete_message(self, message_id: str, user_id: str):
        """Soft delete a message (sender or conversation admin/moderator)"""
        result = await self.db.execute(select(Message).where(Message.id == message_id))
        message = result.scalar_one_or_none()

        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found"
            )
        
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
        self.db.add(message)
        await self.db.commit()

    async def add_message_reaction(self, message_id: str, reaction_data: MessageReactionCreate, user_id: str) -> MessageReactionResponse:
        """Add a reaction to a message"""
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
        await self.db.refresh(reaction)

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

    async def mark_messages_as_read(
        self,
        conversation_id: str,
        user_id: str,
        message_ids: List[str]
    ) -> List[MessageResponse]:
        """
        Tandai pesan-pesan dalam percakapan sebagai dibaca oleh user tertentu.
        Hanya akan update status jika penerima membaca pesan dan pengirimnya bukan dirinya sendiri.
        """
        if not message_ids:
            return []

        # ✅ Cek apakah user bagian dari percakapan
        participant = await self.db.execute(
            select(Participant).where(
                and_(
                    Participant.conversation_id == conversation_id,
                    Participant.user_id == user_id
                )
            )
        )
        if not participant.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a participant of this conversation"
            )

        # 🎯 Cek read receipts yang sudah ada
        existing_receipts_result = await self.db.execute(
            select(MessageReadReceipt).where(
                and_(
                    MessageReadReceipt.message_id.in_(message_ids),
                    MessageReadReceipt.user_id == user_id
                )
            )
        )
        existing_receipts = {
            r.message_id for r in existing_receipts_result.scalars().all()
        }

        messages_to_update = []
        new_receipts_count = 0

        # 📨 Tambah read receipts baru jika belum ada
        for msg_id in message_ids:
            if msg_id not in existing_receipts:
                message_exists = await self.db.scalar(
                    select(Message.id).where(
                        and_(
                            Message.id == msg_id,
                            Message.conversation_id == conversation_id
                        )
                    )
                )
                if message_exists:
                    self.db.add(MessageReadReceipt(
                        message_id=msg_id,
                        user_id=user_id,
                        read_at=datetime.utcnow()
                    ))
                    messages_to_update.append(msg_id)
                    new_receipts_count += 1

        updated_messages: List[MessageResponse] = []

        if new_receipts_count > 0:
            await self.db.commit()  # 💾 Commit receipts dulu

            # 🚀 Load pesan-pesan untuk update status
            load_options = [
                joinedload(Message.sender),
                selectinload(Message.attachments),
                selectinload(Message.reactions),
                selectinload(Message.read_receipts)
            ]
            result = await self.db.execute(
                select(Message)
                .options(*load_options)
                .where(Message.id.in_(messages_to_update))
            )

            for msg in result.scalars().all():
                read_by_count = sum(1 for rr in msg.read_receipts if str(rr.user_id) != str(msg.sender_id))

                # 💡 Ubah status jadi READ kalau minimal 1 orang selain pengirim sudah baca
                if read_by_count > 0 and msg.status != MessageStatus.READ:
                    msg.status = MessageStatus.READ
                    self.db.add(msg)

                msg.read_by_count = read_by_count

                # 🛎️ Kirim update ke pengirim aja
                if str(msg.sender_id) != str(user_id):
                    updated_messages.append(MessageResponse.model_validate(msg))

            await self.db.commit()  # 💾 Commit perubahan status

        # 🧠 Update ConversationSettings: untuk tracking pesan terakhir yang dibaca
        latest_message_id = None
        if message_ids:
            result = await self.db.execute(
                select(Message)
                .where(Message.id.in_(message_ids))
                .order_by(desc(Message.sent_at))
                .limit(1)
            )
            latest = result.scalar_one_or_none()
            if latest:
                latest_message_id = latest.id

        if latest_message_id:
            settings_result = await self.db.execute(
                select(ConversationSettings).where(
                    and_(
                        ConversationSettings.conversation_id == conversation_id,
                        ConversationSettings.user_id == user_id
                    )
                )
            )
            settings = settings_result.scalar_one_or_none()

            should_update = False
            current_last_read_time = None

            if settings and settings.last_read_message_id:
                old_msg = await self.db.scalar(
                    select(Message).where(Message.id == settings.last_read_message_id)
                )
                if old_msg:
                    current_last_read_time = old_msg.sent_at

            new_msg = await self.db.scalar(
                select(Message).where(Message.id == latest_message_id)
            )
            new_msg_time = new_msg.sent_at if new_msg else None

            if not settings or (new_msg_time and (not current_last_read_time or new_msg_time > current_last_read_time)):
                should_update = True

            if should_update:
                if settings:
                    settings.last_read_message_id = latest_message_id
                    settings.updated_at = datetime.utcnow()
                    self.db.add(settings)
                else:
                    self.db.add(ConversationSettings(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        last_read_message_id=latest_message_id,
                        is_muted=False,
                        is_pinned=False
                    ))
                await self.db.commit()

        return updated_messages
