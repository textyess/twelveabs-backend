import base64
import cv2
import numpy as np
from openai import OpenAI
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class VisionService:
    def __init__(self):
        try:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {str(e)}")
            raise

    async def analyze_frame(self, frame_base64: str, exercise_type: str = None) -> str:
        try:
            logger.info("Starting frame analysis")
            # Decode base64 image
            img_data = base64.b64decode(frame_base64)
            nparr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            logger.info("Frame decoded successfully")
            
            # Encode frame as PNG for OpenAI API
            _, buffer = cv2.imencode('.png', frame)
            png_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Prepare prompt based on exercise type
            prompt = "You are a personal trainer. Give quick, direct feedback in 1-2 short sentences max."
            if exercise_type:
                prompt += f" Exercise: {exercise_type}."
            prompt += " Focus only on the most critical form correction needed right now."
            
            logger.info(f"Sending request to  GPT-4o-mini with exercise_type: {exercise_type}")
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
            logger.info(f"Received response from  GPT-4o-mini: {feedback}")
            
            return feedback
        except Exception as e:
            logger.error(f"Error analyzing frame: {str(e)}")
            return f"Error analyzing frame: {str(e)}" 