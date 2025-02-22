import base64
import cv2
import numpy as np
from openai import OpenAI
from app.core.config import settings
import logging
import traceback
import io
from PIL import Image
from typing import Optional

logger = logging.getLogger(__name__)

class VisionService:
    def __init__(self):
        try:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
            self.feedback_history = {}  # Dict to store feedback history per user
            self.max_history_length = 3  # Keep last 3 feedback messages for context
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            raise

    def _add_to_history(self, user_id: str, feedback: str):
        """Add feedback to user's history."""
        if user_id not in self.feedback_history:
            self.feedback_history[user_id] = []
        
        self.feedback_history[user_id].append(feedback)
        # Keep only the last N messages
        if len(self.feedback_history[user_id]) > self.max_history_length:
            self.feedback_history[user_id] = self.feedback_history[user_id][-self.max_history_length:]

    def _get_history_context(self, user_id: str) -> str:
        """Get formatted history context for the prompt."""
        if user_id not in self.feedback_history or not self.feedback_history[user_id]:
            return ""
        
        history = self.feedback_history[user_id]
        context = "\nPrevious feedback:\n"
        for i, msg in enumerate(history, 1):
            context += f"{i}. {msg}\n"
        return context

    async def analyze_frame(self, frame_data: bytes, exercise_type: str = None, user_id: str = None) -> Optional[str]:
        """
        Analyze a frame and return feedback text using GPT-4o-mini vision model.
        
        Args:
            frame_data: Raw bytes of the image
            exercise_type: Optional type of exercise being performed
            user_id: Optional user ID for tracking feedback history
            
        Returns:
            Optional[str]: Feedback text or None if analysis fails
        """
        try:
            logger.info("Starting frame analysis with GPT-4o-mini")
            
            # Convert bytes to base64 for OpenAI API
            png_base64 = base64.b64encode(frame_data).decode('utf-8')
            
            # Prepare prompt based on exercise type and history
            prompt = "You are a personal trainer. Give quick, direct feedback in 1 short sentence max. (this is a MUST rule)"
            if exercise_type:
                prompt += f" Exercise: {exercise_type}."
            prompt += " Focus only on the most critical form correction needed right now. be concise and to the point. Be also very motivating, you need to motivate the user to workout correctly."
            
            # Add history context if available
            if user_id:
                history_context = self._get_history_context(user_id)
                if history_context:
                    prompt += f"\n{history_context}\nBased on this history, provide new feedback that builds upon previous corrections:"
                    
            prompt += "Be also very motivating, you need to motivate the user to workout correctly."
            
            logger.info(f"Sending request to GPT-4o-mini with exercise_type: {exercise_type}")
            
            # Call GPT-4o-mini
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{png_base64}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=100
            )
            
            feedback = response.choices[0].message.content
            logger.info(f"Received response from GPT-4o-mini Vision: {feedback}")
            
            # Store feedback in history if user_id is provided
            if user_id:
                self._add_to_history(user_id, feedback)
            
            return feedback
            
        except Exception as e:
            logger.error(f"Error analyzing frame: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    async def analyze_frame_base64(self, frame_base64: str, exercise_type: str = None) -> str:
        try:
            logger.info("Starting frame analysis")
            # Decode base64 image
            img_data = base64.b64decode(frame_base64)
            nparr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                logger.error("Failed to decode frame")
                return "Error: Failed to decode frame"
                
            logger.info("Frame decoded successfully")
            
            # Encode frame as PNG for OpenAI API
            _, buffer = cv2.imencode('.png', frame)
            png_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Prepare prompt based on exercise type
            prompt = "You are a personal trainer. Give quick, direct feedback in 1-2 short sentences max."
            if exercise_type:
                prompt += f" Exercise: {exercise_type}."
            prompt += " Focus only on the most critical form correction needed right now."
            
            logger.info(f"Sending request to GPT-4o-mini with exercise_type: {exercise_type}")
            # Call GPT-4o-mini
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Updated to the latest model version
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{png_base64}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=100
            )
            
            feedback = response.choices[0].message.content
            logger.info(f"Received response from GPT-4o-mini Vision: {feedback}")
            
            return feedback
        except Exception as e:
            logger.error(f"Error analyzing frame: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return f"Error analyzing frame: {str(e)}" 