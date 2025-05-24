from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from ..models.message import MessageStatus

class MessageBase(BaseModel):
    content: Optional[str] = Field(None, description="Message content")
    message_type: str = Field("text", description="Message type: text, image, file, audio, system")
    reply_to_message_id: Optional[str] = Field(None, description="ID of message being replied to")

class MessageCreate(MessageBase):
    conversation_id: str = Field(..., description="Conversation ID")

class MessageUpdate(BaseModel):
    content: str = Field(..., description="Updated message content")

class MessageReactionCreate(BaseModel):
    emoji: str = Field(..., max_length=10, description="Emoji reaction")

class MessageReactionResponse(BaseModel):
    id: str
    user_id: str
    username: str
    emoji: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class AttachmentResponse(BaseModel):
    id: str
    file_url: str
    file_type: str
    mime_type: Optional[str]
    filename: Optional[str]
    file_size: Optional[int]
    thumbnail_url: Optional[str]
    duration: Optional[int]
    uploaded_at: datetime
    
    class Config:
        from_attributes = True

class MessageResponse(MessageBase):
    id: str
    conversation_id: str
    sender_id: str
    sender_username: str
    sender_avatar: Optional[str]
    status: MessageStatus
    is_deleted: bool
    is_edited: bool
    sent_at: datetime
    edited_at: Optional[datetime]
    deleted_at: Optional[datetime]
    reply_to: Optional['MessageResponse'] = None
    attachments: List[AttachmentResponse] = []
    reactions: List[MessageReactionResponse] = []
    read_by_count: int = 0
    
    class Config:
        from_attributes = True

class MessageReadReceiptUpdate(BaseModel):
    message_ids: List[str] = Field(..., description="List of message IDs to mark as read")

class MessagesResponse(BaseModel):
    messages: List[MessageResponse]
    total: int
    page: int
    per_page: int
    has_more: bool