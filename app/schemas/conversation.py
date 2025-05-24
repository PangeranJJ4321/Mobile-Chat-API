from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from ..models.conversation import ParticipantRole

class ConversationBase(BaseModel):
    name: Optional[str] = Field(None, max_length=100, description="Conversation name (for group chats)")
    description: Optional[str] = Field(None, description="Group description")
    is_group: bool = Field(False, description="Whether this is a group conversation")
    avatar: Optional[str] = Field(None, description="Group avatar URL")

class ConversationCreate(ConversationBase):
    participant_ids: List[str] = Field(..., min_items=1, description="List of user IDs to add to conversation")

class ConversationUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    avatar: Optional[str] = None

class ParticipantBase(BaseModel):
    user_id: str
    role: ParticipantRole = ParticipantRole.MEMBER

class ParticipantAdd(BaseModel):
    user_ids: List[str] = Field(..., min_items=1, description="List of user IDs to add")

class ParticipantUpdate(BaseModel):
    role: ParticipantRole

class ParticipantResponse(BaseModel):
    user_id: str
    username: str
    role: ParticipantRole
    joined_at: datetime
    last_seen_at: Optional[datetime]
    is_muted: bool
    is_pinned: bool
    is_online: bool
    profile_picture: Optional[str]
    
    class Config:
        from_attributes = True

class ConversationResponse(ConversationBase):
    id: str
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime]
    last_message_at: Optional[datetime]
    participants: List[ParticipantResponse]
    unread_count: int = 0
    last_message: Optional[str] = None
    
    class Config:
        from_attributes = True

class ConversationListResponse(BaseModel):
    id: str
    name: Optional[str]
    is_group: bool
    avatar: Optional[str]
    created_at: datetime
    last_message_at: Optional[datetime]
    unread_count: int = 0
    last_message: Optional[str] = None
    last_message_sender: Optional[str] = None
    participants_count: int = 0
    is_muted: bool = False
    is_pinned: bool = False
    
    class Config:
        from_attributes = True