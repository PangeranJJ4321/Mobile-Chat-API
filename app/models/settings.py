from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database import Base

class UserSettings(Base):
    __tablename__ = "user_settings"
    
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    notification_enabled = Column(Boolean, default=True)
    sound_enabled = Column(Boolean, default=True)
    vibration_enabled = Column(Boolean, default=True)
    theme = Column(String(20), default="light")  # 'light', 'dark', 'auto'
    language = Column(String(10), default="en")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="settings")

class ConversationSettings(Base):
    __tablename__ = "conversation_settings"
    
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), primary_key=True)
    is_muted = Column(Boolean, default=False)
    is_pinned = Column(Boolean, default=False)
    custom_name = Column(String(100))  # User can set custom name for conversation
    last_read_message_id = Column(String, ForeignKey("messages.id"))
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="conversation_settings")
    conversation = relationship("Conversation", back_populates="conversation_settings")