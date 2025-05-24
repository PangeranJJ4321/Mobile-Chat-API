from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum, Text, Integer
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database import Base
import enum
import uuid

class MessageStatus(str, enum.Enum):
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    sender_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    reply_to_message_id = Column(String, ForeignKey("messages.id"), index=True)  # For message replies
    content = Column(Text)
    message_type = Column(String(20), default="text")  # 'text', 'image', 'file', 'audio', 'system'
    status = Column(SQLEnum(MessageStatus), default=MessageStatus.SENT)
    is_deleted = Column(Boolean, default=False)
    is_edited = Column(Boolean, default=False)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    edited_at = Column(DateTime(timezone=True))
    deleted_at = Column(DateTime(timezone=True))
    client_message_id = Column(String, index=True, nullable=True) 
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User", back_populates="sent_messages")
    reply_to = relationship("Message", remote_side=[id])
    attachments = relationship("Attachment", back_populates="message", cascade="all, delete-orphan")
    reactions = relationship("MessageReaction", back_populates="message", cascade="all, delete-orphan")
    read_receipts = relationship("MessageReadReceipt", back_populates="message", cascade="all, delete-orphan")

class MessageReaction(Base):
    __tablename__ = "message_reactions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String, ForeignKey("messages.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    emoji = Column(String(10), nullable=False)  # '👍', '❤️', '😂', etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    message = relationship("Message", back_populates="reactions")
    user = relationship("User", back_populates="reactions")
    
    # Unique constraint: one reaction per user per message per emoji
    __table_args__ = (
        {"schema": None},
    )

class MessageReadReceipt(Base):
    __tablename__ = "message_read_receipts"
    
    message_id = Column(String, ForeignKey("messages.id"), primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), primary_key=True, index=True)
    read_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    message = relationship("Message", back_populates="read_receipts")
    user = relationship("User", back_populates="read_receipts")