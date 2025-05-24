from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.security import get_current_active_user
from app.database import get_db
from app.services.conversation_service import ConversationService # Ini adalah service yang sudah kamu berikan
from app.schemas.conversation import (
    ConversationCreate, ConversationUpdate, ConversationResponse, 
    ConversationListResponse, ParticipantAdd, ParticipantUpdate
)
from app.models.conversation import ParticipantRole 
from app.models.user import User 

router = APIRouter()

# Dummy Dependency for current_user_id (Replace with actual authentication later)
async def get_current_user_id(current_user: User = Depends(get_current_active_user)):
    return current_user.id

@router.post("/", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation_endpoint(
    conversation_data: ConversationCreate,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Create a new conversation."""
    service = ConversationService(db)
    return await service.create_conversation(conversation_data, current_user_id)

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
    db: AsyncSession = Depends(get_db)
):
    """Get a list of conversations for the current user."""
    service = ConversationService(db)
    return await service.get_user_conversations(current_user_id, page, per_page)

@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation_endpoint(
    conversation_id: str,
    conversation_data: ConversationUpdate,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Update details of a conversation (admin/moderator only)."""
    service = ConversationService(db)
    return await service.update_conversation(conversation_id, conversation_data, current_user_id)

@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation_endpoint(
    conversation_id: str,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Delete a conversation (creator only)."""
    service = ConversationService(db)
    await service.delete_conversation(conversation_id, current_user_id)
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
    await service.remove_participant(conversation_id, participant_user_id, current_user_id)
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
    return {"message": "Participant role updated successfully"}

@router.post("/{conversation_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_conversation_endpoint(
    conversation_id: str,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Leave a conversation."""
    service = ConversationService(db)
    await service.leave_conversation(conversation_id, current_user_id)
    return {"message": "Successfully left conversation"}