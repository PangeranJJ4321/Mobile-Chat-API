from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.attachment import FileType

class FileUploadResponse(BaseModel):
    id: str
    file_url: str
    file_type: FileType
    mime_type: str
    filename: str
    file_size: int
    thumbnail_url: Optional[str] = None
    duration: Optional[int] = None  
    uploaded_at: datetime

class ThumbnailResponse(BaseModel): 
    original_url: str
    thumbnail_url: str
    width: int
    height: int

class AttachmentResponse(BaseModel):
    id: str
    file_url: str
    file_type: FileType
    mime_type: Optional[str] = None
    filename: Optional[str] = None
    file_size: Optional[int] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[int] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True