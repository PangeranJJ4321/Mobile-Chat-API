from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from typing import List
from app.config import settings
from starlette.background import BackgroundTasks

conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=settings.USE_CREDENTIALS,
    VALIDATE_CERTS=settings.VALIDATE_CERTS
)

fm = FastMail(conf)

async def send_email_async(
    subject: str,
    recipients: List[str],
    body: str,
    subtype: str = "html"
):
    message = MessageSchema(
        subject=subject,
        recipients=recipients,
        body=body,
        subtype=subtype
    )
    fm = FastMail(conf)
    await fm.send_message(message)

