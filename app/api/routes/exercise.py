from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from app.services.vision import VisionService
import base64
import logging

logger = logging.getLogger(__name__)

class ExerciseAnalysisRequest(BaseModel):
    image: str  # Base64 encoded image
    user_id: Optional[str] = None

class ExerciseRouter:
    def __init__(self, vision_service: VisionService):
        self.router = APIRouter(prefix="/exercise", tags=["exercise"])
        self.vision_service = vision_service
        
        # Register routes
        self.router.add_api_route(
            "/analyze",
            self.analyze_exercise,
            methods=["POST"],
            response_model=dict,
            summary="Analyze exercise form from image",
            description="Analyzes exercise form from a base64 encoded image and returns feedback"
        )
    
    async def analyze_exercise(self, request: ExerciseAnalysisRequest):
        """
        Analyze exercise form from an image and provide feedback.
        
        Args:
            request: ExerciseAnalysisRequest containing the base64 encoded image and optional parameters
            
        Returns:
            dict: Contains the feedback from the analysis
        """
        try:
            # Validate base64 image
            try:
                image_data = base64.b64decode(request.image)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid base64 image encoding"
                )
            
            # Analyze the frame
            feedback = await self.vision_service.analyze_frame(
                frame_data=image_data,
                exercise_type=None,
                user_id=request.user_id
            )
            
            if feedback is None:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to analyze exercise form"
                )
            
            return {
                "feedback": feedback,
                "user_id": request.user_id
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in analyze_exercise: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {str(e)}"
            ) 