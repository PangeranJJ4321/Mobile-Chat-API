from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Username must be 3-50 characters")
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters")

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds

class TokenRefresh(BaseModel):
    refresh_token: str

class UserProfile(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_online: bool
    last_active: Optional[datetime]
    profile_picture: Optional[str]
    created_at: datetime

class PasswordReset(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)

class RefreshTokenSchema(BaseModel):
    id: str
    user_id: str
    jti: str # JWT ID, unique identifier for the token
    expires_at: datetime
    created_at: datetime
    revoked_at: Optional[datetime] = None

    class Config:
        from_attributes = True