import json
from typing import Dict, Set
from datetime import datetime
from collections import defaultdict
from fastapi import WebSocket
from app.models.session import UserSession
from app.managers.audio import AudioFeedbackManager
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class UserSession:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.exercise_type = None
        self.audio_enabled = True
        self.voice_id = "IAZxNqwaUCKERlavhDxB"
        self.voice_settings = {}
        self.feedback_history = []
        self.last_activity = datetime.now()
        self.is_active = False

class ConnectionManager:
    def __init__(self, audio_manager: AudioFeedbackManager):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.user_sessions: Dict[str, UserSession] = {}
        self.audio_manager = audio_manager
        self.logger = logging.getLogger(__name__)

    async def connect(self, websocket: WebSocket, client_id: str):
        """
        Connect a new client and store their WebSocket connection.
        """
        if client_id not in self.active_connections:
            self.active_connections[client_id] = set()
        self.active_connections[client_id].add(websocket)
        
        # Create or update user session
        self.user_sessions[client_id] = UserSession(websocket)
        self.logger.info(f"Client {client_id} connected. Active connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket, client_id: str):
        """
        Disconnect a client and remove their WebSocket connection.
        """
        if client_id in self.active_connections:
            self.active_connections[client_id].discard(websocket)
            if not self.active_connections[client_id]:
                del self.active_connections[client_id]
                if client_id in self.user_sessions:
                    del self.user_sessions[client_id]
        self.logger.info(f"Client {client_id} disconnected. Active connections: {len(self.active_connections)}")

    async def send_message(self, message: str, client_id: str):
        """
        Send a text message to a specific client.
        """
        if client_id in self.active_connections:
            for connection in self.active_connections[client_id]:
                await connection.send_text(message)

    async def send_bytes(self, data: bytes, client_id: str):
        """
        Send binary data to a specific client.
        """
        if client_id in self.active_connections:
            for connection in self.active_connections[client_id]:
                await connection.send_bytes(data)

    def update_exercise_type(self, client_id: str, exercise_type: str):
        if client_id in self.user_sessions:
            self.user_sessions[client_id].exercise_type = exercise_type
            self.logger.info(f"Updated exercise type to {exercise_type} for client_id: {client_id}")

    def update_session_active(self, client_id: str, is_active: bool):
        if client_id in self.user_sessions:
            self.user_sessions[client_id].is_active = is_active
            self.logger.info(f"Updated session active status to {is_active} for client_id: {client_id}")

    def toggle_audio(self, client_id: str, enabled: bool):
        if client_id in self.user_sessions:
            self.user_sessions[client_id].audio_enabled = enabled
            self.logger.info(f"Updated audio enabled to {enabled} for client_id: {client_id}")

    def can_generate_audio(self, client_id: str) -> bool:
        return (
            client_id in self.user_sessions
            and self.user_sessions[client_id].audio_enabled
            and self.audio_manager is not None
        )

    def add_feedback(self, client_id: str, feedback: dict):
        if client_id in self.user_sessions:
            self.user_sessions[client_id].feedback_history.append(feedback)
            self.logger.info(f"Added feedback for client_id: {client_id}")

    async def send_audio(self, audio_data: bytes, client_id: str) -> None:
        """Send audio data to a specific client."""
        try:
            if client_id not in self.user_sessions:
                logger.error(f"Client {client_id} not found in user sessions")
                return

            session = self.user_sessions[client_id]
            if not session.is_active:
                logger.info(f"Skipping audio send - session not active for client_id: {client_id}")
                return

            if client_id not in self.active_connections:
                logger.error(f"Client {client_id} not found in active connections")
                return

            websocket = self.active_connections[client_id]
            await websocket.send_bytes(audio_data)
            logger.info(f"Audio data sent to client {client_id}")

        except Exception as e:
            logger.error(f"Error sending audio to client {client_id}: {str(e)}")
            raise

    def is_session_active(self, client_id: str) -> bool:
        return (
            client_id in self.user_sessions
            and self.user_sessions[client_id].is_active
        )