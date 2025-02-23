from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from elevenlabs.client import ElevenLabs
import logging

from app.core.config import settings
from app.managers.audio import AudioFeedbackManager
from app.managers.connection import ConnectionManager
from app.services.vision import VisionService
from app.api.routes.websocket import WebSocketRouter
from app.api.routes.users import UserRouter
from app.api.routes.exercise import ExerciseRouter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_CREDENTIALS,
    allow_methods=settings.CORS_METHODS,
    allow_headers=settings.CORS_HEADERS,
)

# Initialize services and managers
eleven_client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
audio_manager = AudioFeedbackManager(eleven_client)
connection_manager = ConnectionManager(audio_manager)
vision_service = VisionService()

# Initialize routers
websocket_router = WebSocketRouter(connection_manager, vision_service)
user_router = UserRouter(connection_manager)
exercise_router = ExerciseRouter(vision_service)

# Add routes
app.include_router(user_router.router)
app.include_router(exercise_router.router)

@app.websocket("/ws/exercise-analysis/{client_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str,
    exercise_type: str = None,
    audio_enabled: bool = True
):
    await websocket_router.handle_exercise_analysis(
        websocket,
        client_id,
        exercise_type,
        audio_enabled
    )

@app.websocket("/ws/video-stream/{client_id}")
async def video_stream_endpoint(
    websocket: WebSocket,
    client_id: str,
    exercise_type: str = None,
    audio_enabled: bool = True
):
    await websocket_router.handle_video_stream(
        websocket,
        client_id,
        exercise_type,
        audio_enabled
    )

@app.get("/")
async def root():
    return {
        "message": f"{settings.PROJECT_NAME} is running",
        "version": settings.VERSION,
        "active_sessions": len(connection_manager.active_connections)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 