from pydantic import EmailStr
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    ALEMBIC_DATABASE_URL: str
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # JWT
    SECRET_KEY: str = "your-super-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30 * 3600
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # File Upload
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    UPLOAD_DIR: str = "uploads"
    FFMPEG_PATH: str
    FFPROBE_PATH: str

    
    # AWS S3 (Optional)
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_BUCKET_NAME: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    
    # CORS
    ALLOWED_ORIGINS: list = ["http://localhost:5173", "http://localhost:8080"]
    
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Mailtrap/SMTP Settings for Email
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: EmailStr
    MAIL_PORT: int
    MAIL_SERVER: str
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False
    USE_CREDENTIALS: bool = True
    VALIDATE_CERTS: bool = True

    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int
    BASE_FRONTEND_URL: str 
    
    
    BASE_URL: str 

    # Pengaturan Pusher baru
    PUSHER_APP_ID: str
    PUSHER_APP_KEY: str
    PUSHER_APP_SECRET: str
    PUSHER_APP_CLUSTER: str
    
    class Config:
        env_file = ".env"

settings = Settings()