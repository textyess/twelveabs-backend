import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings:
    PROJECT_NAME: str = "Exercise Form Analysis Server"
    VERSION: str = "1.0.0"
    
    # API Keys
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY")
    
    # Voice Settings
    DEFAULT_VOICE_ID: str = "IAZxNqwaUCKERlavhDxB"  # Specified voice
    DEFAULT_VOICE_SETTINGS: dict = {
        "stability": 0.71,
        "similarity_boost": 0.75,
        "style": 0.0,
        "use_speaker_boost": True,
        "speaking_rate": 1.0
    }
    
    # Audio Streaming Settings
    AUDIO_CHUNK_SIZE: int = 1024 * 8  # 8KB chunks
    AUDIO_CACHE_SIZE: int = 100
    STREAM_THRESHOLD: int = 50  # Character length threshold
    RATE_LIMIT_INTERVAL: float = 1.0  # seconds
    
    # CORS Settings
    CORS_ORIGINS: list = ["*"]  # In production, replace with specific origins
    CORS_CREDENTIALS: bool = True
    CORS_METHODS: list = ["*"]
    CORS_HEADERS: list = ["*"]

settings = Settings() 