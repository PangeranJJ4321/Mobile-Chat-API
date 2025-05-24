import magic
from typing import Dict, List, Optional
from pathlib import Path

class FileValidator:
    """Utility class for file validation"""
    
    # MIME_TYPE_MAPPING ini harus disesuaikan dengan `FileType` enum Anda.
    # Saya akan mengasumsikan FileType Anda adalah IMAGE, VIDEO, AUDIO, DOCUMENT
    ALLOWED_EXTENSIONS = {
        'image': {'.jpg', '.jpeg', '.png', '.gif', '.webp'},
        'video': {'.mp4', '.webm', '.mov', '.avi'},
        'audio': {'.mp3', '.wav', '.ogg', '.m4a'},
        'document': {'.pdf', '.txt', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}
    }
    
    MIME_TYPE_TO_CATEGORY = { # Mengganti MIME_TYPE_MAPPING agar lebih jelas
        'image/jpeg': 'image',
        'image/png': 'image', 
        'image/gif': 'image',
        'image/webp': 'image',
        'video/mp4': 'video',
        'video/webm': 'video',
        'video/quicktime': 'video',
        'video/x-msvideo': 'video',
        'audio/mpeg': 'audio', # for .mp3
        'audio/wav': 'audio',
        'audio/ogg': 'audio',
        'audio/mp4': 'audio', # for .m4a
        'application/pdf': 'document',
        'text/plain': 'document',
        'application/msword': 'document',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'document',
        'application/vnd.ms-excel': 'document',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'document',
        'application/vnd.ms-powerpoint': 'document',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'document'
    }
    
    @classmethod
    def validate_extension(cls, filename: str, allowed_categories: List[str]) -> bool:
        """Validate file extension against allowed categories."""
        extension = Path(filename).suffix.lower()
        
        for category in allowed_categories:
            if extension in cls.ALLOWED_EXTENSIONS.get(category, set()):
                return True
        return False
    
    @classmethod
    def get_file_category(cls, mime_type: str) -> Optional[str]:
        """Get file category (e.g., 'image', 'video') from MIME type"""
        return cls.MIME_TYPE_TO_CATEGORY.get(mime_type)
    
    @classmethod
    def is_safe_filename(cls, filename: str) -> bool:
        """Check if filename is safe to prevent directory traversal attacks."""
        dangerous_chars = {'..', '/', '\\', ':', '*', '?', '"', '<', '>', '|'}
        return not any(char in filename for char in dangerous_chars) and \
               ".." not in Path(filename).parts # Check for path traversal segments