from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import json
from datetime import datetime
from decimal import Decimal

# Import Pusher
from pusher import Pusher

from app.core.security import get_current_active_user
from app.database import get_db
from app.models.user import User
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService
from app.schemas.message import (
    MessageCreate, MessageReactionResponse, MessageUpdate, MessageReactionCreate,
    MessageResponse, MessagesResponse, MessageReadReceiptUpdate, RealTimeMessage
)
from app.config import settings
from app.models.conversation import Participant
from sqlalchemy import select
from .conversations import _trigger_conversation_update_to_participants

router = APIRouter()

# Initialize Pusher client
pusher_client = Pusher(
    app_id=settings.PUSHER_APP_ID,
    key=settings.PUSHER_APP_KEY,
    secret=settings.PUSHER_APP_SECRET,
    cluster=settings.PUSHER_APP_CLUSTER,
    ssl=True
)

def serialize_for_json(obj):
    """Custom serializer to handle datetime and other non-JSON serializable objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return float(obj)
    elif hasattr(obj, '__dict__'):
        return {key: serialize_for_json(value) for key, value in obj.__dict__.items()}
    elif isinstance(obj, dict):
        return {key: serialize_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [serialize_for_json(item) for item in obj]
    else:
        return obj

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
    conversation_service = ConversationService(db)
    new_message_response = await service.create_message(message_data, current_user_id)

    # Method 1: Use Pydantic's model_dump with custom serialization
    try:
        # Create the RealTimeMessage object
        pusher_message = RealTimeMessage(
            id=str(new_message_response.id),
            client_message_id=new_message_response.client_message_id,
            conversation_id=str(new_message_response.conversation_id),
            sender_id=str(new_message_response.sender_id),
            sender_username=new_message_response.sender_username,
            sender_avatar=new_message_response.sender_avatar,
            content=new_message_response.content,
            message_type=new_message_response.message_type,
            sent_at=new_message_response.sent_at.isoformat() if new_message_response.sent_at else None,
            is_edited=new_message_response.is_edited,
            is_deleted=new_message_response.is_deleted,
            reply_to_message_id=str(new_message_response.reply_to_message_id) if new_message_response.reply_to_message_id else None,
            status=new_message_response.status.value,
            # Pastikan RealTimeMessage di schemas/message.py memiliki properti ini
            read_by_count=new_message_response.read_by_count
        )

        # Convert to dict and ensure all datetime objects are serialized
        pusher_message_data = pusher_message.model_dump()
        
        # Apply custom serialization to handle any remaining datetime objects
        pusher_message_data = serialize_for_json(pusher_message_data)

    except Exception as e:
        print(f"Error preparing message data: {e}")
        # Fallback: manually create the data dict
        pusher_message_data = {
            "id": str(new_message_response.id),
            "client_message_id": new_message_response.client_message_id,
            "conversation_id": str(new_message_response.conversation_id),
            "sender_id": str(new_message_response.sender_id),
            "sender_username": new_message_response.sender_username,
            "sender_avatar": new_message_response.sender_avatar,
            "content": new_message_response.content,
            "message_type": new_message_response.message_type,
            "sent_at": new_message_response.sent_at.isoformat() if new_message_response.sent_at else None,
            "is_edited": new_message_response.is_edited,
            "is_deleted": new_message_response.is_deleted,
            "reply_to_message_id": str(new_message_response.reply_to_message_id) if new_message_response.reply_to_message_id else None,
            "status": new_message_response.status.value if hasattr(new_message_response.status, 'value') else str(new_message_response.status),
            "read_by_count": new_message_response.read_by_count # Pastikan ini ada di MessageResponse
        }

    # Trigger Pusher event
    channel_name = f"private-chat-{new_message_response.conversation_id}"
    event_name = "new-message"

    try:
        # Test JSON serialization before sending to Pusher
        json.dumps(pusher_message_data)  # This will raise an exception if not serializable
        
        pusher_client.trigger(
            channel_name,
            event_name,
            pusher_message_data
        )
        print(f"Pusher event '{event_name}' triggered for channel '{channel_name}'")
    except json.JSONEncodeError as json_error:
        print(f"JSON serialization error: {json_error}")
        print(f"Problematic data: {pusher_message_data}")
    except Exception as e:
        print(f"Failed to trigger Pusher event: {e}")
        pass

    # agar daftar percakapan mereka diperbarui secara real-time.
    await _trigger_conversation_update_to_participants(
        db=db,
        conversation_service=conversation_service,
        conversation_id=str(new_message_response.conversation_id),
        exclude_user_id=current_user_id 
    )

    return new_message_response

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
    """
    Mark multiple messages in a conversation as read by the current user.
    Also, trigger Pusher events for sender(s) of the marked messages.
    """
    service = MessageService(db)
    conversation_service = ConversationService(db) 
    # Panggil service untuk menandai pesan sebagai terbaca dan dapatkan ID pesan pengirim
    # Service harus mengembalikan daftar pesan yang statusnya telah diperbarui
    updated_messages_for_sender = await service.mark_messages_as_read(conversation_id, current_user_id, read_receipt_data.message_ids)

    # Trigger Pusher event untuk setiap pesan yang statusnya berubah menjadi 'read'
    # dan yang pengirimnya bukan pengguna saat ini (yaitu, pesan yang diterima oleh `current_user_id`
    # tetapi dikirim oleh orang lain).
    channel_name = f"private-chat-{conversation_id}"
    event_name = "message-status-updated" # Nama event yang sudah dibind di Android

    for message_response in updated_messages_for_sender:
        # Hanya kirim update ke pengirim asli jika pesan itu bukan dari current_user_id sendiri
        # dan jika statusnya benar-benar diubah menjadi 'read'
        # (Logika ini sudah ada di message_service.py)
        # Atau, Anda bisa trigger ke semua partisipan jika itu pesan grup
        
        # Untuk private chat (A ke B, B baca, A tahu) atau group chat (X ke Y, Y baca, X tahu)
        # Event ini harus dikirim ke semua partisipan kecuali yang membaca
        # Atau hanya ke pengirim asli pesan jika Anda hanya ingin implementasi centang dua.
        
        # Untuk saat ini, kita akan trigger ke channel percakapan,
        # dan klien akan memfilter siapa pemilik pesan.
        
        # Penting: Pastikan message_response memiliki client_message_id
        # dan status yang sudah diperbarui dari service.
        pusher_payload = {
            "id": str(message_response.id),
            "client_message_id": message_response.client_message_id, # Penting untuk klien Android
            "status": message_response.status.value, # Status baru (harusnya MessageStatus.READ)
            "read_by_count": message_response.read_by_count # Jumlah pembaca (penting untuk grup)
        }

        try:
            pusher_client.trigger(
                channel_name, # Channel percakapan yang sama
                event_name,
                pusher_payload
            )
            print(f"Pusher event '{event_name}' triggered for channel '{channel_name}' for message ID {message_response.id} (status: {message_response.status.value})")
        except json.JSONEncodeError as json_error:
            print(f"JSON serialization error for status update: {json_error}")
            print(f"Problematic data: {pusher_payload}")
        except Exception as e:
            print(f"Failed to trigger Pusher status update event: {e}")

    # Tambahan: Trigger conversation-updated untuk user yang membaca (current_user_id)
    # Ini akan memastikan unread_count-nya diperbarui menjadi 0 di ConversationFragment
    await _trigger_conversation_update_to_participants(
        db=db,
        conversation_service=conversation_service,
        conversation_id=conversation_id,
        exclude_user_id=None # Tidak ada yang dikecualikan, kirim ke current_user_id
        # Atau lebih spesifik:
        # participant_user_ids=[current_user_id]
        # Jika Anda ingin hanya mengirim ke current_user_id, modifikasi _trigger_conversation_update_to_participants
        # untuk menerima daftar user_id spesifik.
    )

    # Tambahan: Trigger conversation-updated untuk pengirim dari pesan yang dibaca
    # Ini penting agar pengirim melihat status "read" di ConversationFragment-nya,
    # dan jika ini adalah group chat, agar read_by_count terupdate di ConversationFragment.
    # Kita perlu tahu siapa pengirim dari message_ids yang baru saja dibaca.
    # Asumsi `updated_messages_for_sender` sudah berisi pesan-pesan yang pengirimnya BUKAN `current_user_id`.
    sender_ids_to_notify = set()
    for msg_res in updated_messages_for_sender:
        sender_ids_to_notify.add(str(msg_res.sender_id))
    
    for sender_id in sender_ids_to_notify:
        await _trigger_conversation_update_to_participants(
            db=db,
            conversation_service=conversation_service,
            conversation_id=conversation_id,
            exclude_user_id=None # Kirim ke pengirim
            # Atau lebih spesifik:
            # participant_user_ids=[sender_id]
        )

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

    # Inisialisasi default
    auth_response = {}

    # Logika Validasi dan Otorisasi Berdasarkan Tipe Channel
    if channel_name.startswith("private-chat-") or channel_name.startswith("presence-chat-"):
        # Ini adalah channel percakapan (chat atau presence)
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
                detail="User not authorized to access this conversation channel"
            )
        
        # Jika lolos validasi, otorisasi Pusher
        if channel_name.startswith("presence-"):
            presence_data = {
                'user_id': str(current_user.id),
                'user_info': {
                    'username': current_user.username,
                    'profile_picture': current_user.profile_picture or ""
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

    elif channel_name.startswith("private-user-"):
        # Ini adalah channel privat khusus untuk pengguna
        target_user_id = channel_name.replace("private-user-", "")
        
        # Pastikan user yang otorisasi adalah user yang memiliki channel ini
        if target_user_id != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not authorized to access this private user channel"
            )
        
        # Jika lolos validasi, otorisasi Pusher
        auth_response = pusher_client.authenticate(
            channel=channel_name,
            socket_id=socket_id
        )

    else:
        # Jika channel name tidak cocok dengan format yang diizinkan sama sekali
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unrecognized channel type for authorization"
        )
    
    # Kembalikan respons otorisasi Pusher
    return auth_response