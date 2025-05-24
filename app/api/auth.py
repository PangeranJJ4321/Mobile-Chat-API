from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict

from ..database import get_db
from ..schemas.auth import (
    UserRegister, UserLogin, Token, TokenRefresh, UserProfile,
    PasswordChange, PasswordReset, PasswordResetConfirm
)
from ..services.auth_service import AuthService
from ..core.security import get_current_user, get_current_active_user
from ..models.user import User

router = APIRouter()

@router.post("/register", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user"""
    auth_service = AuthService(db)
    return await auth_service.register_user(user_data)

@router.post("/login", response_model=Token)
async def login(
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """Login user and return JWT tokens"""
    auth_service = AuthService(db)
    return await auth_service.authenticate_user(login_data)

@router.post("/refresh", response_model=Token)
async def refresh_token(
    token_data: TokenRefresh,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token"""
    auth_service = AuthService(db)
    return await auth_service.refresh_token(token_data.refresh_token)

@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Logout current user"""
    auth_service = AuthService(db)
    await auth_service.logout_user(current_user.id)
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(current_user: User = Depends(get_current_active_user)):
    """Get current user profile"""
    return UserProfile(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role.value,
        is_online=current_user.is_online,
        last_active=current_user.last_active,
        profile_picture=current_user.profile_picture,
        created_at=current_user.created_at
    )

@router.put("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Change user password"""
    auth_service = AuthService(db)
    await auth_service.change_password(
        current_user.id,
        password_data.current_password,
        password_data.new_password
    )
    return {"message": "Password changed successfully"}

@router.post("/forgot-password")
async def forgot_password(
    password_reset: PasswordReset,
    background_tasks: BackgroundTasks, # Tambahkan ini
    db: AsyncSession = Depends(get_db)
):
    """Send password reset email"""
    auth_service = AuthService(db)
    return await auth_service.forgot_password(password_reset, background_tasks) 

@router.post("/reset-password")
async def reset_password(
    reset_data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db)
):
    """Reset password with token"""
    auth_service = AuthService(db)
    return await auth_service.reset_password(reset_data)


@router.get("/verify-token")
async def verify_token_endpoint(current_user: User = Depends(get_current_user)):
    """Verify if token is valid"""
    return {"valid": True, "user_id": current_user.id}

# ============================================================================
# app/core/dependencies.py - Auth Dependencies
# ============================================================================
from fastapi import Depends, HTTPException, status
from ..models.user import User, UserRole
from ..core.security import get_current_active_user

def require_admin(current_user: User = Depends(get_current_active_user)):
    """Require admin role"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

def require_moderator(current_user: User = Depends(get_current_active_user)):
    """Require moderator or admin role"""
    if current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Moderator access required"
        )
    return current_user