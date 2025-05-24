# app/schemas/websocket.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Definisi Pesan yang Dikirim Melalui WebSocket (dari klien ke server)
class WebSocketMessage(BaseModel):
    client_message_id: str # ID unik dari sisi klien untuk pelacakan
    conversation_id: str
    sender_id: str
    content: str
    message_type: str = "text" # 'text', 'image', 'file', 'audio', 'system'
    reply_to_message_id: Optional[str] = None
    # Anda bisa menambahkan is_typing, etc. di sini untuk event lain

# Definisi Pesan yang Diterima/Disiarkan dari Server (ke klien)
class RealTimeMessage(BaseModel):
    id: str # ID pesan dari database
    client_message_id: Optional[str] = None 
    conversation_id: str
    sender_id: str
    content: str
    message_type: str
    sent_at: datetime
    is_edited: bool = False
    is_deleted: bool = False
    reply_to_message_id: Optional[str] = None
    # attachment_url: Optional[str] = None # Jika Anda ingin langsung menyertakan lampiran sederhana
    # reactions: List[str] = [] # Contoh: daftar emoji
    # read_by: List[str] = [] # Daftar user_id yang sudah membaca
    
    # Untuk event lain, Anda bisa punya tipe pesan WebSocket yang berbeda
    # seperti:
    # class TypingEvent(BaseModel):
    #     conversation_id: str
    #     user_id: str
    #     is_typing: bool