import json
from typing import AsyncGenerator
from elevenlabs.client import ElevenLabs
from app.core.config import settings
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class AudioFeedbackManager:
    def __init__(self, client: ElevenLabs):
        self.client = client
        self._cache = {}  # Simple cache for frequently used phrases
        logger.info("Initialized AudioFeedbackManager")

    async def generate_feedback(self, text: str, voice_id: str, voice_settings: dict) -> bytes:
        try:
            logger.info(f"Generating audio feedback for text of length {len(text)} with voice_id: {voice_id}")
            # Check cache first
            cache_key = f"{text}:{voice_id}:{json.dumps(voice_settings)}"
            if cache_key in self._cache:
                logger.info("Found audio in cache")
                return self._cache[cache_key]

            logger.info(f"Generating new audio from ElevenLabs API with voice_id: {voice_id}")
            # Generate new audio
            try:
                # Extract voice settings with defaults
                stability = voice_settings.get('stability', 0.5)
                similarity_boost = voice_settings.get('similarity_boost', 0.75)
                
                # Get the generator from ElevenLabs
                audio_generator = self.client.text_to_speech.convert(
                    text=text,
                    voice_id="IAZxNqwaUCKERlavhDxB",
                    model_id="eleven_multilingual_v2",
                    output_format="mp3_44100_128",
                    voice_settings={
                        "stability": stability,
                        "similarity_boost": similarity_boost
                    }
                )
                
                # Convert generator to bytes
                audio = b''.join(chunk for chunk in audio_generator)
                logger.info(f"Successfully generated audio from ElevenLabs, size: {len(audio)} bytes")
            except Exception as e:
                logger.error(f"ElevenLabs API error: {str(e)}")
                raise

            # Cache the result
            if len(self._cache) > settings.AUDIO_CACHE_SIZE:
                logger.info("Cache full, clearing...")
                self._cache.clear()
            
            self._cache[cache_key] = audio
            logger.info(f"Cached new audio, size: {len(audio)} bytes")

            return audio
        except Exception as e:
            logger.error(f"Error generating audio feedback: {str(e)}")
            raise  # Re-raise the exception to handle it in the calling code

    def clear_cache(self):
        logger.info("Clearing audio cache")
        self._cache.clear() 