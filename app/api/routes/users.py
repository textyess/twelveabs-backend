from typing import Optional
from fastapi import APIRouter, HTTPException
from app.managers.connection import ConnectionManager

class UserRouter:
    def __init__(self, manager: ConnectionManager):
        self.manager = manager
        self.router = APIRouter()
        self.setup_routes()

    def setup_routes(self):
        @self.router.get("/users/{client_id}/session")
        async def get_session_info(client_id: str):
            session_info = self.manager.get_session_info(client_id)
            if not session_info:
                raise HTTPException(status_code=404, detail="Session not found")
            return session_info

        @self.router.get("/users/{client_id}/feedback")
        async def get_user_feedback(client_id: str, limit: int = 10):
            if client_id not in self.manager.feedback_history:
                raise HTTPException(status_code=404, detail="No feedback history found")
            return {
                "feedback_history": self.manager.feedback_history[client_id][-limit:]
            }

        @self.router.put("/users/{client_id}/exercise")
        async def update_exercise_type(client_id: str, exercise_type: str):
            if client_id not in self.manager.user_sessions:
                raise HTTPException(status_code=404, detail="User session not found")
            self.manager.update_exercise_type(client_id, exercise_type)
            return {"message": "Exercise type updated successfully"}

        @self.router.put("/users/{client_id}/audio")
        async def toggle_audio_feedback(client_id: str, enabled: bool):
            if client_id not in self.manager.user_sessions:
                raise HTTPException(status_code=404, detail="User session not found")
            self.manager.toggle_audio(client_id, enabled)
            return {"message": "Audio feedback settings updated successfully"}

        @self.router.put("/users/{client_id}/voice")
        async def update_voice_settings(
            client_id: str,
            voice_id: Optional[str] = None,
            stability: Optional[float] = None,
            similarity_boost: Optional[float] = None,
            style: Optional[float] = None,
            use_speaker_boost: Optional[bool] = None
        ):
            if client_id not in self.manager.user_sessions:
                raise HTTPException(status_code=404, detail="User session not found")
            
            settings = {}
            if stability is not None:
                settings["stability"] = stability
            if similarity_boost is not None:
                settings["similarity_boost"] = similarity_boost
            if style is not None:
                settings["style"] = style
            if use_speaker_boost is not None:
                settings["use_speaker_boost"] = use_speaker_boost
            
            self.manager.update_voice_settings(client_id, voice_id, settings if settings else None)
            return {"message": "Voice settings updated successfully"} 