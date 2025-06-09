from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import json # Tambah import ini
from datetime import datetime # Tambah import ini untuk serialize_for_json
from decimal import Decimal # Tambah import ini untuk serialize_for_json

from app.core.security import get_current_active_user
from app.database import get_db
from app.services.conversation_service import ConversationService
from app.schemas.conversation import (
    ConversationCreate, ConversationUpdate, ConversationResponse,
    ConversationListResponse, ParticipantAdd, ParticipantMuteUpdate, ParticipantUpdate
)
from app.models.conversation import ParticipantRole, Participant # Tambah Participant
from app.models.user import User
from app.config import settings # Tambah import ini untuk kredensial Pusher
from pusher import Pusher # Tambah import ini

router = APIRouter()

# Inisialisasi Pusher Client (seperti di messages.py)
pusher_client = Pusher(
    app_id=settings.PUSHER_APP_ID,
    key=settings.PUSHER_APP_KEY,
    secret=settings.PUSHER_APP_SECRET,
    cluster=settings.PUSHER_APP_CLUSTER,
    ssl=True
)

# Fungsi serialize_for_json (salin dari messages.py)
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

# Helper untuk memicu event Pusher ke semua partisipan
async def _trigger_conversation_update_to_participants(
    db: AsyncSession,
    conversation_service: ConversationService,
    conversation_id: str,
    event_name: str = "conversation-updated",
    # Tambahan parameter untuk memfilter user_id yang akan menerima event
    specific_user_ids: Optional[List[str]] = None,
    exclude_user_id: Optional[str] = None
):
    """
    Fetches the latest ConversationListResponse for each participant
    and triggers a Pusher event to their private user channel.
    """
    if specific_user_ids:
        participant_user_ids_to_trigger = specific_user_ids
    else:
        # Ambil semua partisipan dari percakapan ini
        all_participants_result = await db.execute(
            select(Participant.user_id)
            .where(Participant.conversation_id == conversation_id)
        )
        participant_user_ids_to_trigger = all_participants_result.scalars().all()

    for user_id in participant_user_ids_to_trigger:
        if exclude_user_id and str(user_id) == exclude_user_id:
            continue

        try:
            updated_conv_data = await conversation_service.get_user_conversation_list_response(
                conversation_id=conversation_id,
                user_id=str(user_id)
            )
            
            if updated_conv_data:
                pusher_payload = updated_conv_data.model_dump()
                pusher_payload = serialize_for_json(pusher_payload)

                channel_name = f"private-user-{user_id}"
                
                pusher_client.trigger(
                    channel_name,
                    event_name,
                    pusher_payload
                )
                print(f"Pusher event '{event_name}' triggered for user '{user_id}' on channel '{channel_name}' for conversation '{conversation_id}'")
            else:
                print(f"Could not fetch updated conversation data for user '{user_id}' and conversation '{conversation_id}'. This might happen if user is removed.")

        except json.JSONEncodeError as json_error:
            print(f"JSON serialization error for conversation update: {json_error}")
            print(f"Problematic data: {updated_conv_data}")
        except Exception as e:
            print(f"Failed to trigger Pusher conversation update event for user {user_id}: {e}")


@router.post("/", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation_endpoint(
    conversation_data: ConversationCreate,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Create a new conversation."""
    service = ConversationService(db)
    new_conversation = await service.create_conversation(conversation_data, current_user_id)
    
    # Trigger Pusher event untuk semua partisipan percakapan baru
    # Panggil helper function
    await _trigger_conversation_update_to_participants(
        db=db,
        conversation_service=service,
        conversation_id=str(new_conversation.id)
    )

    return new_conversation

@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation_endpoint(
    conversation_id: str,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get details of a specific conversation."""
    service = ConversationService(db)
    return await service.get_conversation(conversation_id, current_user_id)

@router.get("/", response_model=List[ConversationListResponse])
async def get_user_conversations_endpoint(
    current_user_id: str = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search_query: Optional[str] = Query(None, description="Search query for conversation name or participant username"),
    is_group_filter: Optional[bool] = Query(None, description="Filter by conversation type (true for group, false for private)"),
    unread_only_filter: Optional[bool] = Query(None, description="Filter for conversations with unread messages"),
    db: AsyncSession = Depends(get_db)
):
    """Get a list of conversations for the current user with search and filters."""
    service = ConversationService(db)
    return await service.get_user_conversations(
        current_user_id,
        page,
        per_page,
        search_query,
        is_group_filter,
        unread_only_filter
    )

@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation_endpoint(
    conversation_id: str,
    conversation_data: ConversationUpdate,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Update details of a conversation (admin/moderator only)."""
    service = ConversationService(db)
    updated_conversation = await service.update_conversation(conversation_id, conversation_data, current_user_id)
    
    # Trigger Pusher event untuk semua partisipan percakapan yang diupdate
    await _trigger_conversation_update_to_participants(
        db=db,
        conversation_service=service,
        conversation_id=conversation_id
    )

    return updated_conversation

@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation_endpoint(
    conversation_id: str,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Delete a conversation (creator only)."""
    service = ConversationService(db)
    # Anda mungkin perlu mendapatkan daftar partisipan SEBELUM percakapan dihapus
    # agar dapat mengirim event Pusher ke mereka
    all_participants_result = await db.execute(
        select(Participant.user_id)
        .where(Participant.conversation_id == conversation_id)
    )
    participant_user_ids = all_participants_result.scalars().all()

    await service.delete_conversation(conversation_id, current_user_id)
    
    # Trigger Pusher event untuk semua partisipan yang terpengaruh (percakapan dihapus)
    # Anda bisa mengirim event yang berbeda, misalnya "conversation-deleted"
    # atau mengirim "conversation-updated" dengan payload kosong/ID untuk menunjukkan deletion.
    # Untuk kesederhanaan, kita bisa pemicu "conversation-updated" dengan status delete atau remove dari list.
    # Atau lebih baik lagi, pemicu event spesifik "conversation-deleted"
    event_name = "conversation-deleted" # Nama event baru untuk notifikasi delete
    for user_id in participant_user_ids:
        try:
            channel_name = f"private-user-{user_id}"
            pusher_client.trigger(
                channel_name,
                event_name,
                {"conversation_id": conversation_id, "deleted_by": current_user_id} # Payload minimal
            )
            print(f"Pusher event '{event_name}' triggered for user '{user_id}' on channel '{channel_name}' for conversation '{conversation_id}'")
        except Exception as e:
            print(f"Failed to trigger Pusher conversation deleted event for user {user_id}: {e}")

    return {"message": "Conversation deleted successfully"}

@router.post("/{conversation_id}/participants", status_code=status.HTTP_204_NO_CONTENT)
async def add_participants_endpoint(
    conversation_id: str,
    participant_data: ParticipantAdd,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Add participants to a conversation (admin/moderator only)."""
    service = ConversationService(db)
    await service.add_participants(conversation_id, participant_data, current_user_id)
    
    # Trigger Pusher event untuk semua partisipan (termasuk yang baru ditambahkan)
    await _trigger_conversation_update_to_participants(
        db=db,
        conversation_service=service,
        conversation_id=conversation_id
    )

    return {"message": "Participants added successfully"}

@router.delete("/{conversation_id}/participants/{participant_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_participant_endpoint(
    conversation_id: str,
    participant_user_id: str,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Remove a participant from a conversation (admin/moderator or self-leave)."""
    service = ConversationService(db)
    
    # Dapatkan ID partisipan yang akan dihapus sebelum dihapus
    # Ini penting karena setelah dihapus, kita tidak bisa lagi mencari di DB
    participants_before_removal_result = await db.execute(
        select(Participant.user_id)
        .where(Participant.conversation_id == conversation_id)
    )
    all_participant_ids_before_removal = participants_before_removal_result.scalars().all()

    await service.remove_participant(conversation_id, participant_user_id, current_user_id)
    
    # Trigger Pusher event ke partisipan yang dihapus/meninggalkan
    try:
        channel_name_removed = f"private-user-{participant_user_id}"
        pusher_client.trigger(
            channel_name_removed,
            "conversation-deleted", # Menggunakan event "conversation-deleted" karena secara fungsional hilang dari daftar.
            {"conversation_id": conversation_id, "removed_by": current_user_id}
        )
        print(f"Pusher event 'conversation-deleted' triggered for removed user '{participant_user_id}' on channel '{channel_name_removed}' for conversation '{conversation_id}'")
    except Exception as e:
        print(f"Failed to trigger Pusher 'conversation-deleted' event for user {participant_user_id}: {e}")

    # Trigger Pusher event untuk semua partisipan yang tersisa
    # Ambil ulang partisipan yang tersisa setelah user ini dihapus
    all_participants_result_after = await db.execute(
        select(Participant.user_id)
        .where(Participant.conversation_id == conversation_id)
    )
    remaining_participant_ids = all_participants_result_after.scalars().all()

    for user_id in remaining_participant_ids:
        # Kirim event update ke partisipan yang tersisa
        await _trigger_conversation_update_to_participants(
            db=db,
            conversation_service=service,
            conversation_id=conversation_id,
            specific_user_ids=[str(user_id)] # Hanya kirim ke user_id ini
        )
            
    return {"message": "Participant removed successfully"}

@router.put("/{conversation_id}/participants/{participant_user_id}/role", status_code=status.HTTP_204_NO_CONTENT)
async def update_participant_role_endpoint(
    conversation_id: str,
    participant_user_id: str,
    role_data: ParticipantUpdate,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Update a participant's role in a conversation (admin only)."""
    service = ConversationService(db)
    await service.update_participant_role(conversation_id, participant_user_id, role_data, current_user_id)
    
    # Trigger Pusher event untuk semua partisipan (termasuk yang role-nya berubah)
    await _trigger_conversation_update_to_participants(
        db=db,
        conversation_service=service,
        conversation_id=conversation_id
    )

    return {"message": "Participant role updated successfully"}

@router.post("/{conversation_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_conversation_endpoint(
    conversation_id: str,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Leave a conversation."""
    service = ConversationService(db)
    
    # Dapatkan semua partisipan sebelum user ini meninggalkan
    participants_before_leave_result = await db.execute(
        select(Participant.user_id)
        .where(Participant.conversation_id == conversation_id)
    )
    all_participant_ids_before_leave = participants_before_leave_result.scalars().all()

    await service.leave_conversation(conversation_id, current_user_id)
    
    # Kirim event ke user yang meninggalkan
    try:
        channel_name_left = f"private-user-{current_user_id}"
        pusher_client.trigger(
            channel_name_left,
            "conversation-deleted", # Event yang sama seperti saat user dihapus
            {"conversation_id": conversation_id, "left_by": current_user_id}
        )
        print(f"Pusher event 'conversation-deleted' triggered for user '{current_user_id}' on channel '{channel_name_left}' for conversation '{conversation_id}'")
    except Exception as e:
        print(f"Failed to trigger Pusher 'conversation-deleted' event for user {current_user_id}: {e}")

    # Trigger update untuk partisipan yang tersisa (jika jumlah partisipan berubah)
    # Ambil partisipan yang tersisa setelah user ini leave
    all_participants_result_after = await db.execute(
        select(Participant.user_id)
        .where(Participant.conversation_id == conversation_id)
    )
    remaining_participant_ids = all_participants_result_after.scalars().all()
    
    for user_id in remaining_participant_ids:
        await _trigger_conversation_update_to_participants(
            db=db,
            conversation_service=service,
            conversation_id=conversation_id,
            specific_user_ids=[str(user_id)] # Hanya kirim ke user_id ini
        )

    return {"message": "Successfully left conversation"}

@router.put("/{conversation_id}/participants/{participant_user_id}/mute", status_code=status.HTTP_204_NO_CONTENT)
async def update_participant_mute_status_endpoint(
    conversation_id: str,
    participant_user_id: str,
    mute_data: ParticipantMuteUpdate, 
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Update a participant's mute status in a conversation. (Participant only or Admin)"""
    service = ConversationService(db)
    await service.update_participant_mute_status(
        conversation_id, participant_user_id, mute_data, current_user_id
    )
    
    # Trigger Pusher event ke partisipan yang status mute-nya berubah
    # dan juga ke partisipan lain di percakapan jika Anda ingin mereka tahu (optional)
    
    # Ambil partisipan yang status mute-nya diubah
    # (Ini bisa jadi `participant_user_id` itu sendiri atau `current_user_id` jika dia mengubah status mute orang lain)
    # Anda bisa mendapatkan daftar partisipan yang terpengaruh dari service jika perlu,
    # atau langsung kirim ke participant_user_id.
    
    # Untuk kesederhanaan, kita akan trigger ke participant_user_id yang status mute-nya diubah.
    try:
        updated_conv_data = await service.get_user_conversation_list_response(
            conversation_id=conversation_id,
            user_id=participant_user_id
        )
        if updated_conv_data:
            pusher_payload = updated_conv_data.model_dump()
            pusher_payload = serialize_for_json(pusher_payload)
            channel_name = f"private-user-{participant_user_id}"
            pusher_client.trigger(
                channel_name,
                "conversation-updated",
                pusher_payload
            )
            print(f"Pusher event 'conversation-updated' triggered for muted user '{participant_user_id}' on channel '{channel_name}' for conversation '{conversation_id}'")
    except Exception as e:
        print(f"Failed to trigger Pusher mute status update event for user {participant_user_id}: {e}")

    return {"message": "Participant mute status updated successfully"}