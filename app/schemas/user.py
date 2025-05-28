from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from ..models.user import UserRole

# Pydantic model untuk memperbarui profil pengguna
class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6) # Kata sandi akan di-hash di CRUD
    profile_picture: Optional[str] = None
    is_online: Optional[bool] = None

# Pydantic model untuk respons pengguna (apa yang akan dikembalikan API)
class UserResponse(BaseModel):
    id: str
    username: str
    email: EmailStr
    profile_picture: Optional[str] = None
    role: UserRole
    is_online: bool
    last_active: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True # Mengaktifkan mode ORM untuk konversi otomatis dari model SQLAlchemy

# Pydantic model untuk memperbarui pengaturan pengguna
class UserSettingsUpdate(BaseModel):
    notification_enabled: Optional[bool] = None
    sound_enabled: Optional[bool] = None
    vibration_enabled: Optional[bool] = None
    theme: Optional[str] = None
    language: Optional[str] = None

# Pydantic model untuk respons pengaturan pengguna
class UserSettingsResponse(BaseModel):
    user_id: str
    notification_enabled: bool
    sound_enabled: bool
    vibration_enabled: bool
    theme: str
    language: str
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Pydantic model untuk permintaan blokir/buka blokir pengguna
class BlockUserRequest(BaseModel):
    blocked_id: str = Field(..., description="ID pengguna yang akan diblokir atau dibuka blokirnya")
