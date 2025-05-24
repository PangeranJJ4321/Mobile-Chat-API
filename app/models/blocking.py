from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database import Base

class BlockedUser(Base):
    __tablename__ = "blocked_users"
    
    blocker_id = Column(String, ForeignKey("users.id"), primary_key=True)
    blocked_id = Column(String, ForeignKey("users.id"), primary_key=True)
    blocked_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    blocker = relationship("User", foreign_keys=[blocker_id], back_populates="blocked_users")
    blocked = relationship("User", foreign_keys=[blocked_id], back_populates="blocked_by_users")
