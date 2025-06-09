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