from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_
import bcrypt
from typing import List, Optional
from sqlalchemy import select, func, and_, or_, desc
from app.models.user import User
from app.models.settings import UserSettings
from app.models.blocking import BlockedUser
from app.schemas.user import UserSettingsUpdate, UserUpdate, UserResponse
from app.models.conversation import Conversation, Participant, ParticipantRole

# Fungsi async untuk mendapatkan user berdasarkan ID
async def get_user(db: AsyncSession, user_id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalars().first()

async def get_all_users(db: AsyncSession) -> List[User]:
    result = await db.execute(select(User))
    return result.scalars().all()

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

async def get_available_users_for_conversation(
    db: AsyncSession,
    conversation_id: str,
    current_user_id: str,
    search_query: Optional[str] = None,
    page: int = 1,
    per_page: int = 20
) -> List[UserResponse]:
    try:
        offset = (page - 1) * per_page

        # Subquery: ID user yang udah ikut di conversation
        participant_ids_subquery = select(Participant.user_id).where(
            Participant.conversation_id == conversation_id
        ).scalar_subquery()

        # Query: cari user yang belum ikut conversation dan bukan current user
        base_query = select(User).where(
            and_(
                User.id.notin_(participant_ids_subquery),
                User.id != current_user_id
            )
        )

        # Filter pencarian kalau search_query valid
        if search_query and isinstance(search_query, str) and search_query.strip():
            search_pattern = f"%{search_query.strip().lower()}%"
            base_query = base_query.where(
                or_(
                    func.lower(User.username).like(search_pattern),
                    func.lower(User.email).like(search_pattern)
                )
            )

        # Urut & paginate
        query = base_query.order_by(User.username).offset(offset).limit(per_page)

        # Debug: print query untuk debugging (hapus di production)
        print(f"Query SQL: {query}")
        print(f"conversation_id: {conversation_id}")
        print(f"current_user_id: {current_user_id}")
        print(f"search_query: '{search_query}'")

        # Eksekusi query dengan error handling
        result = await db.execute(query)
        users = result.scalars().all()

        return [UserResponse.model_validate(user) for user in users]
    
    except Exception as e:
        print(f"Error in get_available_users_for_conversation: {str(e)}")
        print(f"Error type: {type(e)}")
        raise e