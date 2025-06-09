from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_active_user
from app.database import get_db 
from app.schemas.user import UserUpdate, UserResponse, UserSettingsUpdate, UserSettingsResponse, BlockUserRequest 

# Import fungsi CRUD dari crud.py
from app.services.user_service import (
    get_all_users,
    get_user,
    update_user_profile,
    search_users,
    get_user_settings,
    update_user_settings,
    block_user,
    unblock_user,
    get_blocked_users,
    get_available_users_for_conversation
)
from app.models.user import User

router = APIRouter()

async def get_current_user_id(current_user: User = Depends(get_current_active_user)):
    return current_user.id

@router.get("/users", response_model=List[UserResponse], summary="Mendapatkan semua user")
async def get_users(db: AsyncSession = Depends(get_db)):
    db_users = await get_all_users(db)
    if not db_users:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tidak ada pengguna")
    return db_users

# Endpoint untuk mendapatkan profil pengguna
@router.get("/users/{user_id}", response_model=UserResponse, summary="Mendapatkan Profil Pengguna")
async def read_user(user_id: str, db: AsyncSession = Depends(get_db)):
    """
    Mengambil informasi profil pengguna berdasarkan ID pengguna.
    """
    db_user = await get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pengguna tidak ditemukan")
    return db_user

# Endpoint untuk memperbarui profil pengguna
@router.put("/users/{user_id}", response_model=UserResponse, summary="Memperbarui Profil Pengguna")
async def update_user(user_id: str, user_update: UserUpdate, db: AsyncSession = Depends(get_db)):
    """
    Memperbarui informasi profil pengguna yang diautentikasi.
    """
    db_user = await update_user_profile(db, user_id=user_id, user_update=user_update)
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pengguna tidak ditemukan")
    return db_user

# Endpoint untuk mencari pengguna
@router.get("/users/search/", response_model=List[UserResponse], summary="Mencari Pengguna")
async def search_users_endpoint(query: Optional[str] = Query(description="String pencarian untuk nama pengguna atau email"), db: AsyncSession = Depends(get_db)):
    """
    Mencari pengguna berdasarkan nama pengguna atau email.
    Jika query kosong atau tidak disediakan, daftar kosong akan dikembalikan.
    """
    if query: # Hanya lakukan pencarian jika ada query
        users = await search_users(db, search_query=query)
    else:
        users = [] # Kembalikan daftar kosong jika query tidak ada atau kosong
    
    return users

# Endpoint untuk mendapatkan pengaturan pengguna
@router.get("/users/{user_id}/settings", response_model=UserSettingsResponse, summary="Mendapatkan Pengaturan Pengguna")
async def read_user_settings(user_id: str, db: AsyncSession = Depends(get_db)):
    """
    Mengambil pengaturan pribadi pengguna.
    """
    db_settings = await get_user_settings(db, user_id=user_id)
    if db_settings is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pengaturan pengguna tidak ditemukan")
    return db_settings

# Endpoint untuk memperbarui pengaturan pengguna
@router.put("/users/{user_id}/settings", response_model=UserSettingsResponse, summary="Memperbarui Pengaturan Pengguna")
async def update_user_settings_endpoint(user_id: str, settings_update: UserSettingsUpdate, db: AsyncSession = Depends(get_db)):
    """
    Memperbarui pengaturan pribadi pengguna.
    """
    db_settings = await update_user_settings(db, user_id=user_id, settings_update=settings_update)
    if db_settings is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pengaturan pengguna tidak ditemukan")
    return db_settings

# Endpoint untuk memblokir pengguna
@router.post("/users/{user_id}/block", status_code=status.HTTP_200_OK, summary="Memblokir Pengguna")
async def block_user_endpoint(user_id: str, block_request: BlockUserRequest, db: AsyncSession = Depends(get_db)):
    """
    Memblokir pengguna lain.
    """
    try:
        await block_user(db, blocker_id=user_id, blocked_id=block_request.blocked_id)
        return {"message": f"Pengguna {block_request.blocked_id} berhasil diblokir oleh {user_id}"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Terjadi kesalahan saat memblokir pengguna")

# Endpoint untuk membuka blokir pengguna
@router.post("/users/{user_id}/unblock", status_code=status.HTTP_200_OK, summary="Membuka Blokir Pengguna")
async def unblock_user_endpoint(user_id: str, unblock_request: BlockUserRequest, db: AsyncSession = Depends(get_db)):
    """
    Membuka blokir pengguna yang sebelumnya diblokir.
    """
    try:
        await unblock_user(db, blocker_id=user_id, blocked_id=unblock_request.blocked_id)
        return {"message": f"Pengguna {unblock_request.blocked_id} berhasil dibuka blokirnya oleh {user_id}"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Terjadi kesalahan saat membuka blokir pengguna")

# Endpoint untuk mendapatkan daftar pengguna yang diblokir
@router.get("/users/{user_id}/blocked", response_model=List[UserResponse], summary="Mendapatkan Pengguna yang Diblokir")
async def get_blocked_users_endpoint(user_id: str, db: AsyncSession = Depends(get_db)):
    """
    Mengambil daftar pengguna yang diblokir oleh pengguna saat ini.
    """
    blocked_users = await get_blocked_users(db, blocker_id=user_id)
    return blocked_users

@router.get("/users/available-for-conversation/{conversation_id}", response_model=List[UserResponse])
async def get_available_users_for_conversation_endpoint(
    conversation_id: str,
    current_user_id: str = Depends(get_current_user_id),
    search_query: Optional[str] = Query(None, description="Search query for username/email"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db)  
):
    """
    Get available users for conversation
    """
    try:
        return await get_available_users_for_conversation(
            db=db,
            conversation_id=conversation_id,
            current_user_id=current_user_id,
            search_query=search_query,
            page=page,
            per_page=per_page
        )
    except Exception as e:
        print(f"Error in endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))