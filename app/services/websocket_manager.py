# app/services/websocket_manager.py
from typing import Dict, List, Optional
from fastapi import WebSocket, WebSocketDisconnect
import json
import logging

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        # Dictionary untuk menyimpan koneksi WebSocket per conversation_id
        # { "conversation_id": [websocket1, websocket2, ...] }
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, conversation_id: str, user_id: str):
        await websocket.accept()
        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = []
        self.active_connections[conversation_id].append(websocket)
        logger.info(f"WebSocket connected: user {user_id} to conversation {conversation_id}. Total connections: {len(self.active_connections[conversation_id])}")

    def disconnect(self, websocket: WebSocket, conversation_id: str, user_id: str):
        if conversation_id in self.active_connections:
            try:
                self.active_connections[conversation_id].remove(websocket)
                if not self.active_connections[conversation_id]:
                    del self.active_connections[conversation_id] # Hapus conversation jika tidak ada koneksi lagi
                logger.info(f"WebSocket disconnected: user {user_id} from conversation {conversation_id}. Remaining: {len(self.active_connections.get(conversation_id, []))}")
            except ValueError:
                logger.warning(f"WebSocket not found in active_connections during disconnect for user {user_id} in conversation {conversation_id}.")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send a message to a single WebSocket connection."""
        try:
            await websocket.send_text(message)
        except WebSocketDisconnect:
            logger.warning("Attempted to send to a disconnected WebSocket.")
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")

    async def broadcast_message(self, message: str, conversation_id: str, exclude_websocket: Optional[WebSocket] = None):
        """Broadcast a message to all connected clients in a specific conversation."""
        if conversation_id in self.active_connections:
            disconnected_websockets = []
            for connection in self.active_connections[conversation_id]:
                if connection == exclude_websocket:
                    continue # Skip the sender if specified

                try:
                    await connection.send_text(message)
                except WebSocketDisconnect:
                    logger.warning(f"Detected disconnected WebSocket during broadcast in conversation {conversation_id}. Will remove.")
                    disconnected_websockets.append(connection)
                except Exception as e:
                    logger.error(f"Error broadcasting message to {connection.client.host}: {e}")

            # Clean up disconnected websockets
            for ws in disconnected_websockets:
                if ws in self.active_connections[conversation_id]: # Check again to prevent issues with concurrent modification
                    self.active_connections[conversation_id].remove(ws)
            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]
        else:
            logger.info(f"No active connections for conversation {conversation_id} to broadcast message.")

# Buat instance global dari WebSocketManager
websocket_manager = WebSocketManager()