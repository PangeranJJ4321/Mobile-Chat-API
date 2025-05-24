# app/api/routes/websocket.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select # Gunakan select dari sqlalchemy.future
from datetime import datetime
import json
import logging

from app.database import get_db
from app.core.security import verify_token, get_current_user 
from app.services.websocket_manager import websocket_manager
from app.models.message import Message, MessageStatus
from app.models.user import User
from app.models.conversation import Conversation, Participant
from app.schemas.websocket import WebSocketMessage, RealTimeMessage

router = APIRouter(prefix="/ws", tags=["websocket"])
logger = logging.getLogger(__name__)

@router.websocket("/{conversation_id}/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    conversation_id: str,
    user_id: str,
    # Token JWT yang dikirim dari klien sebagai query parameter
    # Kita akan memverifikasi token ini secara manual di sini untuk koneksi WebSocket
    token: str 
):
    db: AsyncSession = None # Deklarasi awal
    try:
        # Dapatkan sesi DB
        async for session in get_db():
            db = session
            break # Ambil satu sesi dan keluar

        # --- Validasi Token dan User ID di Sini ---
        try:
            # Panggil fungsi verify_token dari security.py Anda
            payload = verify_token(token, "access") # Pastikan ini adalah access token
            decoded_user_id = payload.get("sub")

            if decoded_user_id is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
            
            if decoded_user_id != user_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token user_id does not match path user_id")
            
            # Opsional: Dapatkan objek User dari DB untuk validasi lebih lanjut jika diperlukan
            # result = await db.execute(select(User).where(User.id == decoded_user_id))
            # current_user = result.scalar_one_or_none()
            # if not current_user:
            #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        except HTTPException as e:
            logger.error(f"WebSocket authentication failed for user {user_id}: {e.detail}")
            # Kode penutupan WebSocket disesuaikan untuk error autentikasi
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=f"Authentication failed: {e.detail}")
            return
        except Exception as e:
            logger.error(f"Unexpected error during WebSocket token validation for user {user_id}: {e}", exc_info=True)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed: Internal server error")
            return
        # --- Akhir Validasi Token ---

        # Verifikasi bahwa user_id adalah partisipan dari conversation_id
        participant_check = await db.execute(
            select(Participant)
            .where(
                (Participant.user_id == user_id) &
                (Participant.conversation_id == conversation_id)
            )
        )
        participant = participant_check.scalar_one_or_none()

        if not participant:
            logger.warning(f"User {user_id} attempted to connect to unauthorized conversation {conversation_id}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Not authorized for this conversation")
            return
        
        # Tambahkan koneksi ke manager
        await websocket_manager.connect(websocket, conversation_id, user_id)
        logger.info(f"WebSocket connection established for user {user_id} in conversation {conversation_id}")

        while True:
            try:
                data = await websocket.receive_text()
                logger.info(f"Received message from {user_id} in {conversation_id}: {data}")

                try:
                    message_data = json.loads(data)
                    client_message = WebSocketMessage(**message_data)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received from {user_id}: {data}")
                    await websocket_manager.send_personal_message(json.dumps({"error": "Invalid JSON format"}), websocket)
                    continue
                except Exception as e:
                    logger.error(f"Error parsing WebSocket message from {user_id}: {e}, Data: {data}")
                    await websocket_manager.send_personal_message(json.dumps({"error": f"Invalid message format: {e}"}), websocket)
                    continue

                if client_message.sender_id != user_id:
                    logger.warning(f"Sender ID mismatch: Expected {user_id}, Got {client_message.sender_id} from {websocket.client}")
                    await websocket_manager.send_personal_message(json.dumps({"error": "Sender ID mismatch"}), websocket)
                    continue

                # Simpan pesan ke database
                new_message = Message(
                    conversation_id=client_message.conversation_id,
                    sender_id=client_message.sender_id,
                    content=client_message.content,
                    message_type=client_message.message_type,
                    reply_to_message_id=client_message.reply_to_message_id,
                    client_message_id=client_message.client_message_id,
                    sent_at=datetime.utcnow(), 
                    status=MessageStatus.SENT 
                )
                db.add(new_message)
                await db.commit()
                await db.refresh(new_message)

                realtime_message = RealTimeMessage(
                    id=str(new_message.id),
                    client_message_id=new_message.client_message_id,
                    conversation_id=str(new_message.conversation_id),
                    sender_id=str(new_message.sender_id),
                    content=new_message.content,
                    message_type=new_message.message_type,
                    sent_at=new_message.sent_at,
                    is_edited=new_message.is_edited,
                    is_deleted=new_message.is_deleted,
                    reply_to_message_id=new_message.reply_to_message_id
                )

                await websocket_manager.broadcast_message(
                    realtime_message.model_dump_json(),
                    conversation_id,
                )
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected gracefully for user {user_id} in conversation {conversation_id}")
                break
            except Exception as e:
                logger.error(f"Unhandled error in WebSocket endpoint for user {user_id}: {e}", exc_info=True)
                await websocket_manager.send_personal_message(json.dumps({"error": "An unexpected server error occurred."}), websocket)
                break

    finally:
        websocket_manager.disconnect(websocket, conversation_id, user_id)
        if db:
            await db.close()