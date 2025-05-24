from fastapi import APIRouter, Depends, HTTPException, status, Query, Request # Import Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import json # Tambahkan import json untuk serialisasi

# Import Pusher
from pusher import Pusher

from app.core.security import get_current_active_user
from app.database import get_db
from app.models.user import User
from app.services.message_service import MessageService
# Import skema yang baru diubah
from app.schemas.message import (
    MessageCreate, MessageReactionResponse, MessageUpdate, MessageReactionCreate,
    MessageResponse, MessagesResponse, MessageReadReceiptUpdate, RealTimeMessage
)
from app.config import settings # Import pengaturan Anda
from app.models.conversation import Participant # Untuk validasi otorisasi Pusher
from sqlalchemy import select # Untuk query DB


router = APIRouter()

# Inisialisasi Pusher client (di luar endpoint untuk inisialisasi tunggal)
pusher_client = Pusher(
    app_id=settings.PUSHER_APP_ID,
    key=settings.PUSHER_APP_KEY,
    secret=settings.PUSHER_APP_SECRET,
    cluster=settings.PUSHER_APP_CLUSTER,
    ssl=True
)

async def get_current_user_id(current_user: User = Depends(get_current_active_user)):
    return current_user.id

@router.post("/", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message_endpoint(
    message_data: MessageCreate,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Create a new message in a conversation and broadcast it via Pusher."""
    service = MessageService(db)
    # create_message harus mengembalikan MessageResponse lengkap atau objek model
    new_message_response = await service.create_message(message_data, current_user_id)

    # Siapkan data untuk Pusher (menggunakan skema RealTimeMessage Anda)
    # new_message_response adalah MessageResponse, jadi kita bisa langsung menggunakannya.
    pusher_message_data = RealTimeMessage(
        id=str(new_message_response.id),
        client_message_id=new_message_response.client_message_id,
        conversation_id=str(new_message_response.conversation_id),
        sender_id=str(new_message_response.sender_id),
        sender_username=new_message_response.sender_username,
        sender_avatar=new_message_response.sender_avatar,
        content=new_message_response.content,
        message_type=new_message_response.message_type,
        sent_at=new_message_response.sent_at,
        is_edited=new_message_response.is_edited,
        is_deleted=new_message_response.is_deleted,
        reply_to_message_id=str(new_message_response.reply_to_message_id) if new_message_response.reply_to_message_id else None,
        status=new_message_response.status.value # Mengambil nilai string dari Enum
    ).model_dump() # Menggunakan .model_dump() untuk Pydantic v2+

    # Trigger event Pusher ke private channel
    channel_name = f"private-chat-{new_message_response.conversation_id}"
    event_name = "new-message" # Nama event yang akan didengar klien

    try:
        pusher_client.trigger(
            channel_name,
            event_name,
            pusher_message_data
        )
        # Log jika berhasil trigger
        print(f"Pusher event '{event_name}' triggered for channel '{channel_name}'")
    except Exception as e:
        # Log error jika Pusher gagal
        print(f"Failed to trigger Pusher event: {e}")
        # Pertimbangkan apakah ini harus menghentikan respons API atau hanya log
        # Untuk kasus pesan, mungkin lebih baik log dan tetap kembalikan pesan
        pass # Biarkan API respons berlanjut

    return new_message_response # Kembalikan MessageResponse seperti biasa


@router.get("/{message_id}", response_model=MessageResponse)
async def get_message_endpoint(
    message_id: str,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get a single message by ID."""
    service = MessageService(db)
    return await service.get_message(message_id, current_user_id)

@router.get("/conversation/{conversation_id}", response_model=MessagesResponse)
async def get_messages_in_conversation_endpoint(
    conversation_id: str,
    current_user_id: str = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    before_message_id: Optional[str] = Query(None, description="Optional: ID of message to fetch messages older than"),
    db: AsyncSession = Depends(get_db)
):
    """Get a list of messages for a specific conversation with pagination."""
    service = MessageService(db)
    return await service.get_messages_in_conversation(conversation_id, current_user_id, page, per_page, before_message_id)

@router.put("/{message_id}", response_model=MessageResponse)
async def update_message_endpoint(
    message_id: str,
    message_data: MessageUpdate,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Update a message (sender only)."""
    service = MessageService(db)
    return await service.update_message(message_id, message_data, current_user_id)

@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message_endpoint(
    message_id: str,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Soft delete a message (sender or conversation admin/moderator)."""
    service = MessageService(db)
    await service.delete_message(message_id, current_user_id)
    return {"message": "Message marked as deleted successfully"}

@router.post("/{message_id}/reactions", response_model=MessageReactionResponse, status_code=status.HTTP_201_CREATED)
async def add_message_reaction_endpoint(
    message_id: str,
    reaction_data: MessageReactionCreate,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Add a reaction to a message."""
    service = MessageService(db)
    return await service.add_message_reaction(message_id, reaction_data, current_user_id)

@router.delete("/{message_id}/reactions", status_code=status.HTTP_204_NO_CONTENT)
async def remove_message_reaction_endpoint(
    message_id: str,
    emoji: str = Query(..., description="Emoji to remove"),
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Remove a reaction from a message."""
    service = MessageService(db)
    await service.remove_message_reaction(message_id, current_user_id, emoji)
    return {"message": "Reaction removed successfully"}

@router.post("/conversation/{conversation_id}/read-receipts", status_code=status.HTTP_204_NO_CONTENT)
async def mark_messages_as_read_endpoint(
    conversation_id: str,
    read_receipt_data: MessageReadReceiptUpdate,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Mark multiple messages in a conversation as read by the current user."""
    service = MessageService(db)
    await service.mark_messages_as_read(conversation_id, current_user_id, read_receipt_data.message_ids)
    return {"message": "Messages marked as read successfully"}


# Tambahkan Endpoint Otorisasi Pusher
@router.post("/pusher/auth", summary="Pusher Authorization Endpoint")
async def pusher_auth(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Endpoint untuk mengotorisasi Pusher private atau presence channels.
    Klien Pusher akan memanggil endpoint ini dengan socket_id dan channel_name.
    Server akan memverifikasi apakah current_user berhak bergabung dengan channel tersebut.
    """
    form_data = await request.form()
    socket_id = form_data.get('socket_id')
    channel_name = form_data.get('channel_name')

    if not socket_id or not channel_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing socket_id or channel_name"
        )

    # Validasi format channel name
    # Asumsikan format: private-chat-CONVERSATION_ID atau presence-chat-CONVERSATION_ID
    if not channel_name.startswith("private-chat-") and not channel_name.startswith("presence-chat-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid channel name format for authorization"
        )

    conversation_id = channel_name.replace("private-chat-", "").replace("presence-chat-", "")

    # Verifikasi apakah current_user adalah partisipan dari conversation_id ini
    result = await db.execute(
        select(Participant)
        .where(
            (Participant.user_id == current_user.id) &
            (Participant.conversation_id == conversation_id)
        )
    )
    participant = result.scalar_one_or_none()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not authorized to access this channel"
        )

    # Jika otorisasi berhasil, kembalikan respons otorisasi Pusher
    if channel_name.startswith("presence-"):
        presence_data = {
            'user_id': str(current_user.id),
            'user_info': {
                'username': current_user.username,
                'profile_picture': current_user.profile_picture or "" # Pastikan tidak None
            }
        }
        auth_response = pusher_client.authenticate(
            channel=channel_name,
            socket_id=socket_id,
            data=presence_data
        )
    else: # Private channel
        auth_response = pusher_client.authenticate(
            channel=channel_name,
            socket_id=socket_id
        )

    return json.loads(auth_response)