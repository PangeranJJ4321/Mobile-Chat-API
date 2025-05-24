from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database import Base
import enum
import uuid

class ParticipantRole(str, enum.Enum):
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    MODERATOR = "MODERATOR"

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    name = Column(String(100))  # Optional: for group chats
    description = Column(Text)  # Group description
    is_group = Column(Boolean, default=False, index=True)
    avatar = Column(String(500))  # Group avatar URL
    created_by = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_message_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    creator = relationship("User", back_populates="created_conversations")
    participants = relationship("Participant", back_populates="conversation", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    conversation_settings = relationship("ConversationSettings", back_populates="conversation")

class Participant(Base):
    __tablename__ = "participants"
    
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), primary_key=True)
    role = Column(SQLEnum(ParticipantRole), default=ParticipantRole.MEMBER)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    is_muted = Column(Boolean, default=False)
    is_pinned = Column(Boolean, default=False)
    
    # Relationships
    user = relationship("User", back_populates="participants")
    conversation = relationship("Conversation", back_populates="participants")