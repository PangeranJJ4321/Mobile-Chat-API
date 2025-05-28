from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_
import bcrypt
from typing import List, Optional

from app.models.user import User
from app.models.settings import UserSettings
from app.models.blocking import BlockedUser
from app.schemas.user import UserSettingsUpdate, UserUpdate


# Fungsi async untuk mendapatkan user berdasarkan ID
async def get_user(db: AsyncSession, user_id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalars().first()


# Fungsi async untuk mendapatkan user berdasarkan email
async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalars().first()


# Fungsi async untuk mendapatkan user berdasarkan username
async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalars().first()


# Fungsi async untuk update profile user
async def update_user_profile(db: AsyncSession, user_id: str, user_update: UserUpdate) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    db_user = result.scalars().first()
    if db_user:
        update_data = user_update.dict(exclude_unset=True)
        if "password" in update_data and update_data["password"] is not None:
            hashed_password = bcrypt.hashpw(update_data["password"].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            db_user.password_hash = hashed_password
            del update_data["password"]
        for key, value in update_data.items():
            setattr(db_user, key, value)
        await db.commit()
        await db.refresh(db_user)
    return db_user


# Fungsi async untuk pencarian user berdasarkan username/email
async def search_users(db: AsyncSession, search_query: str) -> List[User]:
    result = await db.execute(
        select(User).where(
            or_(
                User.username.ilike(f"%{search_query}%"),
                User.email.ilike(f"%{search_query}%")
            )
        )
    )
    return result.scalars().all()


# Fungsi async untuk dapat user settings
async def get_user_settings(db: AsyncSession, user_id: str) -> Optional[UserSettings]:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    return result.scalars().first()


# Fungsi async untuk buat user settings default
async def create_user_settings(db: AsyncSession, user_id: str) -> UserSettings:
    db_settings = UserSettings(user_id=user_id)
    db.add(db_settings)
    await db.commit()
    await db.refresh(db_settings)
    return db_settings


# Fungsi async untuk update user settings
async def update_user_settings(db: AsyncSession, user_id: str, settings_update: UserSettingsUpdate) -> Optional[UserSettings]:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    db_settings = result.scalars().first()
    if db_settings:
        update_data = settings_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_settings, key, value)
        await db.commit()
        await db.refresh(db_settings)
    return db_settings


# Fungsi async untuk blokir user
async def block_user(db: AsyncSession, blocker_id: str, blocked_id: str) -> BlockedUser:
    if blocker_id == blocked_id:
        raise ValueError("Pengguna tidak dapat memblokir diri sendiri.")

    result_blocker = await db.execute(select(User).where(User.id == blocker_id))
    blocker = result_blocker.scalars().first()
    if not blocker:
        raise ValueError(f"Pengguna dengan ID {blocker_id} tidak ditemukan.")

    result_blocked = await db.execute(select(User).where(User.id == blocked_id))
    blocked = result_blocked.scalars().first()
    if not blocked:
        raise ValueError(f"Pengguna dengan ID {blocked_id} tidak ditemukan.")

    result_exist = await db.execute(
        select(BlockedUser).where(
            BlockedUser.blocker_id == blocker_id,
            BlockedUser.blocked_id == blocked_id
        )
    )
    existing_block = result_exist.scalars().first()
    if existing_block:
        raise ValueError(f"Pengguna {blocked_id} sudah diblokir oleh {blocker_id}.")

    new_block = BlockedUser(blocker_id=blocker_id, blocked_id=blocked_id)
    db.add(new_block)
    await db.commit()
    await db.refresh(new_block)
    return new_block


# Fungsi async untuk unblock user
async def unblock_user(db: AsyncSession, blocker_id: str, blocked_id: str) -> bool:
    result = await db.execute(
        select(BlockedUser).where(
            BlockedUser.blocker_id == blocker_id,
            BlockedUser.blocked_id == blocked_id
        )
    )
    block_entry = result.scalars().first()
    if block_entry:
        await db.delete(block_entry)
        await db.commit()
        return True
    return False


# Fungsi async untuk daftar user yang diblokir
async def get_blocked_users(db: AsyncSession, blocker_id: str) -> List[User]:
    result_blocks = await db.execute(select(BlockedUser).where(BlockedUser.blocker_id == blocker_id))
    blocked_entries = result_blocks.scalars().all()
    blocked_user_ids = [entry.blocked_id for entry in blocked_entries]

    if not blocked_user_ids:
        return []

    result_users = await db.execute(select(User).where(User.id.in_(blocked_user_ids)))
    return result_users.scalars().all()
