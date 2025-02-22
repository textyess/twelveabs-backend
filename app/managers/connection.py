import json
from typing import Dict
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
        self.is_active = False  # New field for session activity status

class ConnectionManager:
    def __init__(self, audio_manager=None):
        self.user_sessions: Dict[str, UserSession] = {}
        self.audio_manager = audio_manager
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        self.user_sessions[client_id] = UserSession(websocket)
        self.active_connections[client_id] = websocket
        logger.info(f"Created new session for client_id: {client_id}")

    def disconnect(self, client_id: str):
        if client_id in self.user_sessions:
            del self.user_sessions[client_id]
            if client_id in self.active_connections:
                del self.active_connections[client_id]
            logger.info(f"Removed session for client_id: {client_id}")

    def update_exercise_type(self, client_id: str, exercise_type: str):
        if client_id in self.user_sessions:
            self.user_sessions[client_id].exercise_type = exercise_type
            logger.info(f"Updated exercise type to {exercise_type} for client_id: {client_id}")

    def update_session_active(self, client_id: str, is_active: bool):
        if client_id in self.user_sessions:
            self.user_sessions[client_id].is_active = is_active
            logger.info(f"Updated session active status to {is_active} for client_id: {client_id}")

    def toggle_audio(self, client_id: str, enabled: bool):
        if client_id in self.user_sessions:
            self.user_sessions[client_id].audio_enabled = enabled
            logger.info(f"Updated audio enabled to {enabled} for client_id: {client_id}")

    def can_generate_audio(self, client_id: str) -> bool:
        return (
            client_id in self.user_sessions
            and self.user_sessions[client_id].audio_enabled
            and self.audio_manager is not None
        )

    def add_feedback(self, client_id: str, feedback: dict):
        if client_id in self.user_sessions:
            self.user_sessions[client_id].feedback_history.append(feedback)
            logger.info(f"Added feedback for client_id: {client_id}")

    async def send_message(self, message: str, client_id: str, message_type: str = "text") -> None:
        """Send a message to a specific client."""
        try:
            if client_id not in self.user_sessions:
                logger.error(f"Client {client_id} not found in user sessions")
                return

            session = self.user_sessions[client_id]
            if not session.is_active:
                logger.info(f"Skipping message send - session not active for client_id: {client_id}")
                return

            if client_id not in self.active_connections:
                logger.error(f"Client {client_id} not found in active connections")
                return

            websocket = self.active_connections[client_id]
            await websocket.send_text(message)
            logger.info(f"Message sent to client {client_id}")

        except Exception as e:
            logger.error(f"Error sending message to client {client_id}: {str(e)}")
            raise

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