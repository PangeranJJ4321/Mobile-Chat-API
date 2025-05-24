from sqlalchemy import Column, String, DateTime, ForeignKey, Enum as SQLEnum, Integer
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database import Base
import enum
import uuid

class FileType(str, enum.Enum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    DOCUMENT = "DOCUMENT"
    AUDIO = "AUDIO"

class Attachment(Base):
    __tablename__ = "attachments"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    message_id = Column(String, ForeignKey("messages.id"), nullable=False, index=True)
    file_url = Column(String(500), nullable=False)
    file_type = Column(SQLEnum(FileType), index=True)
    mime_type = Column(String(100))
    filename = Column(String(255))
    file_size = Column(Integer)  # in bytes
    thumbnail_url = Column(String(500))  # For images/videos
    duration = Column(Integer)  # For audio/video files (in seconds)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    message = relationship("Message", back_populates="attachments")