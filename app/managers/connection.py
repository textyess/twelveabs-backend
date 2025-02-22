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

class ConnectionManager:
    def __init__(self, audio_manager: AudioFeedbackManager):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_sessions: Dict[str, UserSession] = {}
        self.feedback_history: Dict[str, list] = defaultdict(list)
        self.audio_manager = audio_manager
        self.rate_limit_interval = settings.RATE_LIMIT_INTERVAL
        self.stream_threshold = settings.STREAM_THRESHOLD

    async def connect(self, websocket: WebSocket, client_id: str):
        logger.info(f"Registering connection for client_id: {client_id}")
        self.active_connections[client_id] = websocket
        if client_id not in self.user_sessions:
            self.user_sessions[client_id] = UserSession(client_id)
            logger.info(f"Created new session for client_id: {client_id}")
        logger.info(f"Connection registered for client_id: {client_id}")

    def disconnect(self, client_id: str):
        logger.info(f"Disconnecting client_id: {client_id}")
        self.active_connections.pop(client_id, None)
        if client_id in self.user_sessions:
            self.user_sessions[client_id].is_active = False
        logger.info(f"Client disconnected: {client_id}")

    async def send_message(self, message: str, client_id: str, message_type: str = "text"):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_text(
                json.dumps({
                    "type": message_type,
                    "data": message
                })
            )

    async def send_audio_stream(self, text: str, client_id: str):
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            session = self.user_sessions[client_id]

            logger.info(f"Starting audio stream for client_id: {client_id}")
            # Send stream start message
            await self.send_message(
                json.dumps({"stream_id": datetime.now().isoformat()}),
                client_id,
                "stream_start"
            )

            chunk_count = 0
            total_bytes = 0
            # Stream audio chunks
            async for chunk in self.audio_manager.generate_feedback_stream(
                text,
                session.voice_id,
                session.voice_settings
            ):
                if chunk:  # Only send non-empty chunks
                    chunk_size = len(chunk)
                    total_bytes += chunk_size
                    chunk_count += 1
                    logger.debug(f"Sending audio chunk {chunk_count} of size {chunk_size} bytes to client_id: {client_id}")
                    await websocket.send_bytes(chunk)

            logger.info(f"Audio stream complete for client_id: {client_id}. Sent {chunk_count} chunks, total {total_bytes} bytes")
            # Send stream end message
            await self.send_message(
                json.dumps({"status": "completed"}),
                client_id,
                "stream_end"
            )

    async def send_audio(self, audio_data: bytes, client_id: str):
        if client_id in self.active_connections:
            logger.info(f"Sending single audio chunk of size {len(audio_data)} bytes to client_id: {client_id}")
            await self.active_connections[client_id].send_bytes(audio_data)

    def update_exercise_type(self, client_id: str, exercise_type: str):
        if client_id in self.user_sessions:
            self.user_sessions[client_id].exercise_type = exercise_type

    def update_voice_settings(self, client_id: str, voice_id: str = None, settings: dict = None):
        if client_id in self.user_sessions:
            if voice_id:
                self.user_sessions[client_id].voice_id = voice_id
            if settings:
                self.user_sessions[client_id].voice_settings.update(settings)

    def toggle_audio(self, client_id: str, enabled: bool):
        if client_id in self.user_sessions:
            self.user_sessions[client_id].audio_enabled = enabled

    def add_feedback(self, client_id: str, feedback: dict):
        if client_id in self.user_sessions:
            self.user_sessions[client_id].feedback_history.append(feedback)
            self.feedback_history[client_id].append(feedback)

    def get_session_info(self, client_id: str) -> dict:
        if client_id not in self.user_sessions:
            return None
        session = self.user_sessions[client_id]
        return {
            "user_id": session.user_id,
            "exercise_type": session.exercise_type,
            "start_time": session.start_time.isoformat(),
            "is_active": session.is_active,
            "last_activity": session.last_activity.isoformat(),
            "feedback_count": len(session.feedback_history),
            "voice_id": session.voice_id,
            "voice_settings": session.voice_settings,
            "audio_enabled": session.audio_enabled
        }

    def can_generate_audio(self, client_id: str) -> bool:
        if client_id not in self.user_sessions:
            return False
        
        session = self.user_sessions[client_id]
        if not session.audio_enabled:
            return False

        now = datetime.now()
        if session.last_feedback_time is None:
            session.last_feedback_time = now
            return True

        time_diff = (now - session.last_feedback_time).total_seconds()
        if time_diff >= self.rate_limit_interval:
            session.last_feedback_time = now
            return True
        
        return False 