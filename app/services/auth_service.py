from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete # Import update dan delete
from fastapi import HTTPException, status, BackgroundTasks # Import BackgroundTasks
from datetime import datetime, timedelta, timezone # Import timedelta dan timezone
import uuid # Import uuid

from ..models.user import User, UserRole,RefreshToken, PasswordResetToken 
from ..models.settings import UserSettings
from ..core.security import get_password_hash, verify_password, create_access_token, create_refresh_token, verify_token, create_reset_token # Import create_reset_token
from ..core.email import send_email_async 
from ..schemas.auth import UserRegister, UserLogin, Token, UserProfile, TokenRefresh, PasswordChange, PasswordReset, PasswordResetConfirm
from ..config import settings

class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def register_user(self, user_data: UserRegister) -> UserProfile:
        """Register a new user"""
        # Check if user already exists
        result = await self.db.execute(
            select(User).where(
                (User.email == user_data.email) | (User.username == user_data.username)
            )
        )
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            if existing_user.email == user_data.email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already taken"
                )
        
        # Create new user
        user = User(
            id=str(uuid.uuid4()),
            username=user_data.username,
            email=user_data.email,
            password_hash=get_password_hash(user_data.password),
            role=UserRole.USER,
            is_online=True,
            last_active=datetime.now(timezone.utc) # Gunakan timezone-aware datetime
        )
        
        self.db.add(user)
        await self.db.flush()  # Dapatkan ID pengguna
        
        # Create default user settings
        user_settings = UserSettings(user_id=user.id)
        self.db.add(user_settings)
        
        await self.db.commit()
        await self.db.refresh(user)
        
        return UserProfile(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role.value,
            is_online=user.is_online,
            last_active=user.last_active,
            profile_picture=user.profile_picture,
            created_at=user.created_at
        )
    
    async def authenticate_user(self, login_data: UserLogin) -> Token:
        """Authenticate user and return tokens"""
        # Get user by email
        result = await self.db.execute(select(User).where(User.email == login_data.email))
        user = result.scalar_one_or_none()
        
        if not user or not verify_password(login_data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )
        
        # Update user online status
        user.is_online = True
        user.last_active = datetime.now(timezone.utc) # Gunakan timezone-aware datetime
        await self.db.commit()
        await self.db.refresh(user)
        
        # Create tokens
        # Generate a unique JWT ID (jti) for the refresh token
        refresh_token_jti = str(uuid.uuid4())
        
        access_token = create_access_token({"sub": user.id, "username": user.username})
        # Pastikan create_refresh_token menerima jti di payload
        refresh_token = create_refresh_token({"sub": user.id, "jti": refresh_token_jti}) 
        
        # Store the refresh token in the database
        db_refresh_token = RefreshToken(
            user_id=user.id,
            jti=refresh_token_jti,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES) # Gunakan setting untuk expire
        )
        self.db.add(db_refresh_token)
        await self.db.commit()
        await self.db.refresh(db_refresh_token) # Refresh untuk mendapatkan ID jika diperlukan
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
    
    async def refresh_token(self, refresh_token_str: str) -> Token:
        """Refresh access token using refresh token"""
        try:
            # Menggunakan verify_token yang sudah ada untuk decoding dan validasi
            payload = verify_token(refresh_token_str, "refresh") 
            user_id = payload.get("sub")
            jti = payload.get("jti") # Ambil jti dari payload
            if not user_id or not jti:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token payload")
        except HTTPException as e: # Tangkap HTTPException dari verify_token
            raise e # Lempar kembali HTTPException yang sudah ada
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired refresh token: {e}"
            )
        
        # Verify user still exists
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found for refresh token"
            )
        
        # Check if the refresh token exists in DB and is not revoked
        db_token_result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.jti == jti,
                RefreshToken.expires_at > datetime.now(timezone.utc), # Pastikan belum kedaluwarsa
                RefreshToken.revoked_at == None # Pastikan belum dicabut
            )
        )
        db_refresh_token = db_token_result.scalar_one_or_none()

        if not db_refresh_token:
            # Jika token tidak ditemukan atau sudah dicabut/kedaluwarsa,
            # cabut semua token refresh untuk pengguna ini untuk keamanan
            await self.db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at == None)
                .values(revoked_at=datetime.now(timezone.utc))
            )
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked refresh token. Please log in again."
            )
        
        # Mark the old refresh token as revoked (single-use refresh token strategy)
        db_refresh_token.revoked_at = datetime.now(timezone.utc)
        await self.db.commit()
        
        # Create new tokens
        new_refresh_token_jti = str(uuid.uuid4()) # Generate new jti for the new refresh token
        access_token = create_access_token({"sub": user.id, "username": user.username})
        new_refresh_token = create_refresh_token({"sub": user.id, "jti": new_refresh_token_jti})
        
        # Store the new refresh token in the database
        new_db_refresh_token = RefreshToken(
            user_id=user.id,
            jti=new_refresh_token_jti,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
        )
        self.db.add(new_db_refresh_token)
        await self.db.commit()
        
        return Token(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
    
    async def logout_user(self, user_id: str):
        """Logout user - set offline status and revoke all refresh tokens for this user."""
        # Update user's online status
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        
        if user:
            user.is_online = False
            user.last_active = datetime.now(timezone.utc) # Gunakan timezone-aware datetime
            await self.db.commit()
            await self.db.refresh(user)

        # Revoke all refresh tokens for this user
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at == None) # Hanya cabut yang belum dicabut
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self.db.commit()
        
    async def change_password(self, user_id: str, current_password: str, new_password: str):
        """Change user password and revoke all existing refresh tokens for security."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if not verify_password(current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )
        
        user.password_hash = get_password_hash(new_password)
        await self.db.commit()

        # Revoke all refresh tokens after password change for security
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at == None)
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self.db.commit()

    async def forgot_password(self, password_reset: PasswordReset, background_tasks: BackgroundTasks):
        """Send password reset email"""
        result = await self.db.execute(select(User).where(User.email == password_reset.email))
        user = result.scalar_one_or_none()
        
        if not user:
            # Mengembalikan pesan umum untuk mencegah enumerasi email
            return {"message": "If the email exists, a password reset link has been sent."}
        
        # Hasilkan token reset
        reset_token_str = create_reset_token() # Token string acak
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
        
        db_reset_token = PasswordResetToken(
            user_id=user.id,
            token=reset_token_str,
            expires_at=expires_at
        )
        self.db.add(db_reset_token)
        await self.db.commit()
        
        # Bangun URL reset (Anda perlu mengganti ini dengan URL frontend yang sebenarnya)
        reset_url = f"{settings.BASE_FRONTEND_URL}/reset-password?token={reset_token_str}"
        
        email_body = f"""
        Halo {user.username},

        Anda telah meminta untuk mereset kata sandi Anda.
        Silakan klik tautan berikut untuk mereset kata sandi Anda:
        {reset_url}

        Tautan ini akan kedaluwarsa dalam {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} menit.

        Jika Anda tidak meminta reset kata sandi, mohon abaikan email ini.

        Terima kasih,
        Tim Aplikasi Anda
        """
        
        background_tasks.add_task(
            send_email_async,
            subject="Permintaan Reset Kata Sandi Anda",
            recipients=[user.email],
            body=email_body
        )
        
        return {"message": "If the email exists, a password reset link has been sent."}

    async def reset_password(self, reset_data: PasswordResetConfirm):
        """Reset password with token and revoke all existing refresh tokens for security."""
        result = await self.db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token == reset_data.token,
                PasswordResetToken.expires_at > datetime.now(timezone.utc),
                PasswordResetToken.revoked_at == None 
            )
        )
        db_reset_token = result.scalar_one_or_none()

        if not db_reset_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )
        
        # Tandai token reset sebagai dicabut setelah digunakan
        db_reset_token.revoked_at = datetime.now(timezone.utc)
        
        # Dapatkan pengguna yang terkait dengan token
        user_result = await self.db.execute(select(User).where(User.id == db_reset_token.user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Perbarui kata sandi pengguna
        user.password_hash = get_password_hash(reset_data.new_password)
        await self.db.commit()
        await self.db.refresh(user) # Refresh user untuk mendapatkan data terbaru jika diperlukan

        # Cabut semua refresh token pengguna untuk keamanan
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at == None)
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self.db.commit()

        return {"message": "Password reset successfully"}