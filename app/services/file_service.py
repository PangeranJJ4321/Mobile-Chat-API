import os
import uuid
import aiofiles
from typing import Optional, List, Dict, Any
from pathlib import Path
from PIL import Image, ImageOps # PIL.Image sudah ada di utils/image_processor, bisa dihapus di sini
import magic
import asyncio
import subprocess # Untuk FFmpeg/FFprobe
from datetime import datetime

from fastapi import UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.sql import func

from app.models.attachment import Attachment, FileType
from app.models.user import User
from app.models.message import Message 
from app.schemas.file import FileUploadResponse, AttachmentResponse 
from app.config import settings
from app.utils.file_validator import FileValidator # Import validator baru
from app.utils.image_processor import ImageProcessor # Import image processor baru

class FileService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.max_file_size = settings.MAX_FILE_SIZE
        self.ffmpeg_path = settings.FFMPEG_PATH
        self.ffprobe_path = settings.FFPROBE_PATH
        
        self._create_directories()
    
    def _create_directories(self):
        """Create necessary upload directories"""
        directories = [
            self.upload_dir,
            self.upload_dir / "avatars",
            self.upload_dir / "attachments" / "images",
            self.upload_dir / "attachments" / "videos", 
            self.upload_dir / "attachments" / "audio",
            self.upload_dir / "attachments" / "documents",
            self.upload_dir / "thumbnails"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    async def validate_file(self, file: UploadFile) -> Dict[str, Any]:
        """Validate uploaded file content and type using python-magic."""
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No filename provided"
            )
        
        if not FileValidator.is_safe_filename(file.filename):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename contains unsafe characters or paths"
            )

        # Read file content fully to check size and MIME type accurately
        file_content = await file.read()
        file_size = len(file_content)
        
        if file_size == 0:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty file uploaded"
            )
        
        if file_size > self.max_file_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds maximum allowed size of {self.max_file_size / (1024 * 1024):.0f} MB"
            )
        
        # Detect MIME type using python-magic for more accuracy
        mime_type = magic.from_buffer(file_content, mime=True)
        
        # Determine file type based on MIME category
        file_category = FileValidator.get_file_category(mime_type)
        if not file_category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file MIME type: {mime_type}"
            )
        
        # Map category to FileType enum
        file_type_map = {
            'image': FileType.IMAGE,
            'video': FileType.VIDEO,
            'audio': FileType.AUDIO,
            'document': FileType.DOCUMENT
        }
        file_type_enum = file_type_map.get(file_category)

        if not file_type_enum: # Fallback for unknown category
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type based on MIME category: {file_category}"
            )

        # Reset file pointer for subsequent reads (if any)
        await file.seek(0)
        
        return {
            "mime_type": mime_type,
            "file_type": file_type_enum,
            "file_size": file_size,
            "content": file_content, # Return content as it was read already
            "file_category": file_category
        }
    
    async def save_file(self, file_content: bytes, filename: str, subdirectory: str) -> str:
        """Save file to disk and return relative path from UPLOAD_DIR."""
        file_extension = Path(filename).suffix.lower()
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        
        # Create full path
        target_directory = self.upload_dir / subdirectory
        target_directory.mkdir(parents=True, exist_ok=True) # Ensure subdir exists
        file_path = target_directory / unique_filename
        
        # Save file asynchronously
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_content)
        
        # Return relative path for URL generation
        return str(Path(subdirectory) / unique_filename) # Return relative path string
    
    async def create_thumbnail(self, file_path_relative: str, file_type: FileType, file_content: bytes) -> Optional[str]:
        """Create thumbnail for images and videos."""
        full_file_path = self.upload_dir / file_path_relative
        
        if file_type == FileType.IMAGE:
            try:
                # Use ImageProcessor for image thumbnail creation
                thumbnail_data = await asyncio.get_event_loop().run_in_executor(
                    None, ImageProcessor.create_thumbnail, file_content, settings.THUMBNAIL_SIZE
                )
                thumbnail_filename = f"thumb_{uuid.uuid4()}.jpg"
                thumbnail_full_path = self.upload_dir / "thumbnails" / thumbnail_filename
                
                async with aiofiles.open(thumbnail_full_path, 'wb') as f:
                    await f.write(thumbnail_data)
                return str(Path("thumbnails") / thumbnail_filename)
            except Exception as e:
                print(f"Error creating image thumbnail for {file_path_relative}: {e}")
                return None
        elif file_type == FileType.VIDEO:
            return await self._create_video_thumbnail(file_path_relative)
        return None
    
    async def _create_video_thumbnail(self, file_path_relative: str) -> Optional[str]:
        """Create thumbnail for video using ffmpeg."""
        full_path = self.upload_dir / file_path_relative
        thumbnail_filename = f"thumb_{uuid.uuid4()}.jpg"
        thumbnail_path = self.upload_dir / "thumbnails" / thumbnail_filename
        
        # Ensure thumbnails directory exists
        (self.upload_dir / "thumbnails").mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path, '-i', str(full_path), '-ss', '00:00:01.000', # Seek to 1 second
            '-vframes', '1', '-s', f"{settings.THUMBNAIL_SIZE[0]}x{settings.THUMBNAIL_SIZE[1]}",
            str(thumbnail_path), '-y' # Overwrite if exists
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and thumbnail_path.exists():
                return str(Path("thumbnails") / thumbnail_filename)
            else:
                print(f"FFmpeg failed to create video thumbnail (return code {process.returncode}): {stderr.decode()}")
                return None
        except FileNotFoundError:
            print(f"FFmpeg not found at {self.ffmpeg_path}. Please ensure it's installed and in PATH or configured.")
            return None
        except Exception as e:
            print(f"Error creating video thumbnail: {e}")
            return None
    
    async def upload_avatar(self, file: UploadFile, user_id: str) -> FileUploadResponse:
        """Upload user avatar."""
        validation_result = await self.validate_file(file)
        
        if validation_result["file_type"] != FileType.IMAGE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Avatar must be an image file"
            )
        
        # Save file
        file_path_relative = await self.save_file(
            validation_result["content"],
            file.filename,
            "avatars"
        )
        
        # Create thumbnail
        thumbnail_path_relative = await self.create_thumbnail(
            file_path_relative, FileType.IMAGE, validation_result["content"]
        )
        
        # Fetch user
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Delete old avatar files if exists
        if user.profile_picture:
            old_relative_path = Path(user.profile_picture).relative_to("/uploads/")
            await self._delete_file_if_exists(str(old_relative_path))
            # Delete old thumbnail if it followed the pattern
            if user.profile_picture.startswith(f"{settings.BASE_URL}/uploads/avatars/"):
                old_thumb_name = "thumb_" + Path(old_relative_path).name.replace(Path(old_relative_path).suffix, ".jpg")
                await self._delete_file_if_exists(str(Path("thumbnails") / old_thumb_name))

        # Update user profile picture URL
        user.profile_picture = self.get_file_url(file_path_relative)
        user.updated_at = func.now() # Use func.now() for SQLAlchemy
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        
        return FileUploadResponse(
            id=str(uuid.uuid4()), # Avatar itself doesn't have a specific ID in attachments table
            file_url=self.get_file_url(file_path_relative),
            file_type=validation_result["file_type"],
            mime_type=validation_result["mime_type"],
            filename=file.filename,
            file_size=validation_result["file_size"],
            thumbnail_url=self.get_file_url(thumbnail_path_relative) if thumbnail_path_relative else None,
            uploaded_at=datetime.utcnow() # Use UTC for consistency
        )
    
    async def upload_attachment(self, file: UploadFile, message_id: str) -> Attachment:
        """Upload message attachment."""
        validation_result = await self.validate_file(file)
        
        # Determine subdirectory based on file type
        subdirectory_map = {
            FileType.IMAGE: "attachments/images",
            FileType.VIDEO: "attachments/videos",
            FileType.AUDIO: "attachments/audio",
            FileType.DOCUMENT: "attachments/documents"
        }
        subdirectory = subdirectory_map[validation_result["file_type"]]
        
        # Save file
        file_path_relative = await self.save_file(
            validation_result["content"],
            file.filename,
            subdirectory
        )
        
        # Create thumbnail for images and videos
        thumbnail_path_relative = await self.create_thumbnail(
            file_path_relative, 
            validation_result["file_type"],
            validation_result["content"] if validation_result["file_type"] == FileType.IMAGE else None
        )
        
        # Get duration for audio/video files
        duration = None
        if validation_result["file_type"] in [FileType.AUDIO, FileType.VIDEO]:
            duration = await self._get_media_duration(file_path_relative)
        
        # Create attachment record
        attachment = Attachment(
            id=str(uuid.uuid4()),
            message_id=message_id,
            file_url=self.get_file_url(file_path_relative),
            file_type=validation_result["file_type"],
            mime_type=validation_result["mime_type"],
            filename=file.filename,
            file_size=validation_result["file_size"],
            thumbnail_url=self.get_file_url(thumbnail_path_relative) if thumbnail_path_relative else None,
            duration=duration,
            uploaded_at=func.now() # Use func.now() for SQLAlchemy
        )
        
        self.db.add(attachment)
        await self.db.commit()
        await self.db.refresh(attachment)
        
        return attachment
    
    async def _get_media_duration(self, file_path_relative: str) -> Optional[int]:
        """Get duration of audio/video file in seconds using ffprobe."""
        full_path = self.upload_dir / file_path_relative
        
        cmd = [
            self.ffprobe_path, '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(full_path)
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                duration_str = stdout.decode().strip()
                return int(float(duration_str))
            else:
                print(f"FFprobe failed to get duration (return code {process.returncode}): {stderr.decode()}")
                return None
        except FileNotFoundError:
            print(f"FFprobe not found at {self.ffprobe_path}. Please ensure it's installed and in PATH or configured.")
            return None
        except Exception as e:
            print(f"Error getting media duration: {e}")
            return None
    
    async def delete_attachment(self, attachment_id: str, user_id: str):
        """Delete attachment record and its associated files from disk."""
        result = await self.db.execute(
            select(Attachment).where(Attachment.id == attachment_id)
        )
        attachment = result.scalar_one_or_none()
        
        if not attachment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment not found"
            )
        
        # Check if user owns the message associated with the attachment
        message_result = await self.db.execute(
            select(Message).where(Message.id == attachment.message_id)
        )
        message = message_result.scalar_one_or_none()
        
        if not message or message.sender_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this attachment"
            )
        
        # Extract relative paths from full URLs and delete files from disk
        file_path_relative = Path(attachment.file_url).relative_to(settings.BASE_URL + "/uploads/")
        await self._delete_file_if_exists(str(file_path_relative))

        if attachment.thumbnail_url:
            thumbnail_path_relative = Path(attachment.thumbnail_url).relative_to(settings.BASE_URL + "/uploads/")
            await self._delete_file_if_exists(str(thumbnail_path_relative))
        
        # Delete from database
        await self.db.delete(attachment)
        await self.db.commit()
    
    async def _delete_file_if_exists(self, file_path_relative: str):
        """Delete file from disk if it exists using its relative path."""
        try:
            full_path = self.upload_dir / file_path_relative
            if full_path.exists() and full_path.is_file():
                full_path.unlink()
        except Exception as e:
            print(f"Error deleting file {full_path}: {e}")
    
    def get_file_url(self, file_path_relative: str) -> str:
        """Generate full public URL for a file given its relative path from UPLOAD_DIR."""
        return f"{settings.BASE_URL}/uploads/{file_path_relative}"