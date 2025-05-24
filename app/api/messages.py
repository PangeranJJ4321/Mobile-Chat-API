# routers/messages.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.core.security import get_current_active_user
from app.database import get_db
from app.models.user import User
from app.services.message_service import MessageService 
from app.schemas.message import (
    MessageCreate, MessageReactionResponse, MessageUpdate, MessageReactionCreate, 
    MessageResponse, MessagesResponse, MessageReadReceiptUpdate
)

router = APIRouter()

async def get_current_user_id(current_user: User = Depends(get_current_active_user)):
    return current_user.id

@router.post("/", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message_endpoint(
    message_data: MessageCreate,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Create a new message in a conversation."""
    service = MessageService(db)
    return await service.create_message(message_data, current_user_id)

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