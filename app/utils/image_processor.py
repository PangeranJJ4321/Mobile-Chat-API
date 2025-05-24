from PIL import Image, ImageOps, ExifTags
from typing import Tuple, Optional
import io
import os 

class ImageProcessor:
    """Utility class for image processing"""
    
    @staticmethod
    def create_thumbnail(
        image_data: bytes, 
        size: Tuple[int, int] = (300, 300),
        quality: int = 85
    ) -> bytes:
        """Create thumbnail from image data, returning bytes."""
        with Image.open(io.BytesIO(image_data)) as img:
            # Handle EXIF orientation
            img = ImageOps.exif_transpose(img)
            
            # Convert to RGB if necessary (handle transparency)
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P': # Palette mode can convert to RGBA first for better transparency handling
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Create thumbnail
            img.thumbnail(size, Image.Resampling.LANCZOS)
            
            # Save to bytes
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=quality, optimize=True)
            return output.getvalue()
    
    @staticmethod
    def get_image_dimensions(image_data: bytes) -> Tuple[int, int]:
        """Get image dimensions from image data."""
        with Image.open(io.BytesIO(image_data)) as img:
            return img.size
    
    @staticmethod
    def compress_image(
        image_data: bytes, 
        max_size_bytes: int = 1024 * 1024,  # 1MB
        quality: int = 85
    ) -> bytes:
        """Compress image if its byte size exceeds max_size_bytes."""
        if len(image_data) <= max_size_bytes:
            return image_data
        
        with Image.open(io.BytesIO(image_data)) as img:
            # Handle EXIF orientation
            img = ImageOps.exif_transpose(img)
            
            # Convert to RGB
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=quality, optimize=True) # Awal kompresi
            
            # Loop untuk kompresi lebih lanjut jika ukuran masih terlalu besar
            current_quality = quality
            while len(output.getvalue()) > max_size_bytes and current_quality > 10: # Jangan kompres terlalu rendah
                current_quality -= 5 # Kurangi kualitas
                output = io.BytesIO()
                img.save(output, format='JPEG', quality=current_quality, optimize=True)
            
            return output.getvalue()