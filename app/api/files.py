import mimetypes
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import os
from pathlib import Path
import uuid
from datetime import datetime
from app.database import get_db
from app.services.file_service import FileService
from app.core.security import get_current_user 
from app.models.user import User
from app.schemas.file import FileUploadResponse, AttachmentResponse 
from app.config import settings

router = APIRouter(prefix="/files")

# Dependency for FileService to inject the database session
async def get_file_service(db: AsyncSession = Depends(get_db)) -> FileService:
    return FileService(db)

@router.post("/avatar", response_model=FileUploadResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service) # Inject FileService
):
    """Upload user avatar"""
    return await file_service.upload_avatar(file, current_user.id)

@router.post("/upload-group-avatar", response_model=FileUploadResponse)
async def upload_group_avatar_endpoint(
    file: UploadFile = File(...),
    file_service: FileService = Depends(get_file_service)
):
    
    return await file_service.upload_group_avatar(file)


@router.post("/attachments/{message_id}", response_model=AttachmentResponse)
async def upload_attachment(
    message_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service) # Inject FileService
):
    """Upload message attachment"""
    attachment = await file_service.upload_attachment(file, message_id)
    
    # Return the full AttachmentResponse schema
    return attachment # Karena AttachmentResponse menggunakan Config(from_attributes=True)

@router.delete("/attachments/{attachment_id}")
async def delete_attachment(
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service) # Inject FileService
):
    """Delete attachment"""
    await file_service.delete_attachment(attachment_id, current_user.id)
    return {"message": "Attachment deleted successfully"}

@router.get("/uploads/{file_path:path}")
async def serve_file(file_path: str):
    """Serve uploaded files"""
    full_path = Path(settings.UPLOAD_DIR) / file_path
    
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # Security check: ensure file is within upload directory to prevent directory traversal
    try:
        full_path.resolve().relative_to(Path(settings.UPLOAD_DIR).resolve())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied (path outside allowed directory)"
        )
    
    # Determine media type for FileResponse
    # You might want to use python-magic here for more robust type detection
    # but mimetypes.guess_type is often sufficient for serving.
    mime_type, _ = mimetypes.guess_type(str(full_path))
    if mime_type is None:
        mime_type = 'application/octet-stream' # Default if type can't be guessed

    return FileResponse(
        path=str(full_path),
        filename=full_path.name,
        media_type=mime_type # Use guessed MIME type
    )