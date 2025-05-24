from sqlalchemy import Column, ForeignKey, String, Boolean, DateTime, Enum as SQLEnum, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database import Base
import enum
import uuid

class UserRole(str, enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"
    MODERATOR = "MODERATOR"

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.USER)
    is_online = Column(Boolean, default=False, index=True)
    last_active = Column(DateTime(timezone=True), server_default=func.now())
    profile_picture = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    created_conversations = relationship("Conversation", back_populates="creator")
    participants = relationship("Participant", back_populates="user")
    sent_messages = relationship("Message", back_populates="sender")
    reactions = relationship("MessageReaction", back_populates="user")
    read_receipts = relationship("MessageReadReceipt", back_populates="user")
    device_tokens = relationship("DeviceToken", back_populates="user")
    settings = relationship("UserSettings", back_populates="user", uselist=False)
    conversation_settings = relationship("ConversationSettings", back_populates="user")
    blocked_users = relationship("BlockedUser", foreign_keys="BlockedUser.blocker_id", back_populates="blocker")
    blocked_by_users = relationship("BlockedUser", foreign_keys="BlockedUser.blocked_id", back_populates="blocked")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))  # ✅ FIXED: auto-generate UUID
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    jti = Column(String, unique=True, nullable=False, index=True)  # JWT ID
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="refresh_tokens")

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)  # Token reset yang dikirim via email
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)  # Untuk menandai token sudah digunakan/dicabut

    # Relasi balik ke User
    user = relationship("User", back_populates="password_reset_tokens")

