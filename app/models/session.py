from typing import List, Optional, Dict, Any
from datetime import datetime
from app.core.config import settings

class UserSession:
    def __init__(self, user_id: str):
        self.user_id: str = user_id
        self.exercise_type: Optional[str] = None
        self.start_time: datetime = datetime.now()
        self.feedback_history: List[dict] = []
        self.is_active: bool = True
        self.last_activity: datetime = datetime.now()
        self.voice_id: str = settings.DEFAULT_VOICE_ID
        self.voice_settings: Dict[str, Any] = settings.DEFAULT_VOICE_SETTINGS.copy()
        self.audio_enabled: bool = True
        self.last_feedback_time: Optional[datetime] = None
        self.is_processing = False  # Flag to control feedback generation 