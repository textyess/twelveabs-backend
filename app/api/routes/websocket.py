from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime
import json
import logging
import traceback
import base64
import time

from app.managers.connection import ConnectionManager
from app.services.vision import VisionService

logger = logging.getLogger(__name__)

class WebSocketRouter:
    def __init__(self, manager: ConnectionManager, vision_service: VisionService):
        self.manager = manager
        self.vision_service = vision_service
        self.logger = logging.getLogger(__name__)

    async def handle_exercise_analysis(
        self,
        websocket: WebSocket,
        client_id: str,
        exercise_type: str = None,
        audio_enabled: bool = True
    ):
        try:
            logger.info(f"Attempting WebSocket connection for client_id: {client_id}")
            await websocket.accept()
            logger.info(f"WebSocket accepted for client_id: {client_id}")
            
            logger.info(f"Initializing connection in manager for client_id: {client_id}")
            await self.manager.connect(websocket, client_id)
            logger.info(f"Connection initialized in manager for client_id: {client_id}")

            if exercise_type:
                logger.info(f"Setting exercise type to {exercise_type} for client_id: {client_id}")
                self.manager.update_exercise_type(client_id, exercise_type)
            
            logger.info(f"Setting audio enabled to {audio_enabled} for client_id: {client_id}")
            self.manager.toggle_audio(client_id, audio_enabled)
            
            try:
                while True:
                    logger.info(f"Waiting for message from client_id: {client_id}")
                    message = await websocket.receive()
                    logger.info(f"Received message type: {message.get('type')} from client_id: {client_id}")
                    
                    try:
                        if message.get('type') == 'websocket.receive':
                            if 'text' in message:
                                # Handle text message (could be ping, control message, or base64 image)
                                try:
                                    data = json.loads(message['text'])
                                    if isinstance(data, dict):
                                        if data.get('type') == 'ping':
                                            logger.debug(f"Received ping from client_id: {client_id}")
                                            await websocket.send_text(json.dumps({'type': 'pong'}))
                                            continue
                                        elif data.get('type') in ['start_session', 'resume_session']:
                                            logger.info(f"Session activated for client_id: {client_id}")
                                            self.manager.update_session_active(client_id, True)
                                            continue
                                        elif data.get('type') in ['stop_session', 'pause_session']:
                                            logger.info(f"Session deactivated for client_id: {client_id}")
                                            self.manager.update_session_active(client_id, False)
                                            continue
                                except json.JSONDecodeError:
                                    # Not JSON, treat as base64 image data
                                    frame_data = message['text'].strip()
                            elif 'bytes' in message:
                                # Handle binary data
                                frame_data = base64.b64encode(message['bytes']).decode('utf-8')
                            else:
                                logger.error(f"Unsupported message format from client_id: {client_id}")
                                continue

                            # Validate base64 data
                            try:
                                base64.b64decode(frame_data[:100])
                                logger.info(f"Base64 validation successful for client_id: {client_id}")
                            except Exception as e:
                                logger.error(f"Invalid base64 data from client_id: {client_id}: {str(e)}")
                                await websocket.send_text(json.dumps({
                                    "type": "error",
                                    "data": "Invalid image data format"
                                }))
                                continue

                            # Get current exercise type and session status from session
                            session = self.manager.user_sessions[client_id]
                            current_exercise = session.exercise_type
                            
                            # Only analyze frames if session is active
                            if not session.is_active:
                                logger.info(f"Skipping frame analysis - session not active for client_id: {client_id}")
                                continue
                            
                            # Analyze the frame
                            logger.info(f"Processing frame for client_id: {client_id}, exercise_type: {current_exercise}")
                            feedback_text = await self.vision_service.analyze_frame(frame_data, current_exercise)
                            logger.info(f"Frame analysis completed for client_id: {client_id}, feedback: {feedback_text}")
                            
                            if not feedback_text or feedback_text.startswith("Error analyzing frame"):
                                logger.error(f"Invalid feedback text received for client_id: {client_id}")
                                continue
                            
                            # Only send feedback if session is still active
                            if not session.is_active:
                                logger.info(f"Skipping feedback sending - session not active for client_id: {client_id}")
                                continue
                            
                            # Prepare feedback data
                            feedback_data = {
                                "timestamp": datetime.now().isoformat(),
                                "feedback": feedback_text,
                                "exercise_type": current_exercise,
                                "audio_available": self.manager.can_generate_audio(client_id)
                            }
                            
                            # Store feedback in history
                            self.manager.add_feedback(client_id, feedback_data)
                            
                            # Update last activity
                            session.last_activity = datetime.now()
                            
                            # Send text feedback only if session is active
                            if session.is_active:
                                await self.manager.send_message(
                                    json.dumps(feedback_data),
                                    client_id,
                                    "text"
                                )
                            
                                # Handle audio feedback if enabled and session is active
                                if self.manager.can_generate_audio(client_id):
                                    logger.info(f"Generating audio feedback for client_id: {client_id}")
                                    try:
                                        audio_data = await self.manager.audio_manager.generate_feedback(
                                            feedback_text,
                                           "IAZxNqwaUCKERlavhDxB",
                                            session.voice_settings
                                        )
                                        if audio_data and session.is_active:
                                            logger.info(f"Sending audio chunk of size {len(audio_data)} bytes")
                                            await self.manager.send_audio(audio_data, client_id)
                                        else:
                                            logger.info("Skipping audio feedback - session not active or no audio data")
                                    except Exception as audio_e:
                                        logger.error(f"Error generating audio: {str(audio_e)}")
                                        if session.is_active:
                                            await websocket.send_text(json.dumps({
                                                "type": "error",
                                                "data": "Failed to generate audio feedback"
                                            }))
                    except Exception as img_e:
                        logger.error(f"Error processing image for client_id: {client_id}: {str(img_e)}")
                        logger.error(f"Image processing traceback: {traceback.format_exc()}")
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "data": f"Error processing image: {str(img_e)}"
                        }))
                        continue
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for client_id: {client_id}")
                self.manager.disconnect(client_id)
            except Exception as e:
                logger.error(f"Error in WebSocket connection for client_id: {client_id}: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                await self.manager.send_message(str(e), client_id, "error")
                self.manager.disconnect(client_id)
        except Exception as outer_e:
            logger.error(f"Error during WebSocket setup for client_id: {client_id}: {str(outer_e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            try:
                await websocket.close(code=1011, reason=str(outer_e))
            except:
                pass

    async def handle_video_stream(
        self,
        websocket: WebSocket,
        client_id: str,
        exercise_type: str = None,
        audio_enabled: bool = True
    ):
        """
        Handle video stream WebSocket connection.
        
        Args:
            websocket: The WebSocket connection
            client_id: Unique identifier for the client
            exercise_type: Type of exercise being performed
            audio_enabled: Whether to generate audio feedback
        """
        try:
            await websocket.accept()
            await self.manager.connect(websocket, client_id)
            self.logger.info(f"Started video stream for client {client_id}")

            try:
                while True:
                    try:
                        # Receive the message
                        message = await websocket.receive()
                        message_type = message.get('type', '')
                        
                        # Check for disconnect message first
                        if message_type == 'websocket.disconnect':
                            self.logger.info(f"Received disconnect message from client {client_id}")
                            break

                        self.logger.debug(f"Received message type: {message_type} from client {client_id}")

                        # Handle different message types
                        if message_type == 'websocket.receive':
                            if 'bytes' in message:
                                frame_data = message['bytes']
                                # Process the frame with vision service
                                self.logger.debug(f"Processing frame for client {client_id}, size: {len(frame_data)} bytes")
                                feedback = await self.vision_service.analyze_frame(
                                    frame_data,
                                    exercise_type=exercise_type,
                                    user_id=client_id
                                )
                                
                                if audio_enabled and feedback:
                                    # Generate audio feedback
                                    self.logger.debug(f"Generating audio feedback for client {client_id}")
                                    audio_data = await self.manager.audio_manager.generate_feedback(feedback)
                                    
                                    if audio_data and isinstance(audio_data, bytes):
                                        # Send audio back to client
                                        self.logger.debug(f"Sending audio feedback to client {client_id}, size: {len(audio_data)} bytes")
                                        try:
                                            await websocket.send_bytes(audio_data)
                                            self.logger.debug("Audio feedback sent successfully")
                                        except Exception as send_error:
                                            self.logger.error(f"Error sending audio feedback: {str(send_error)}")
                                    else:
                                        self.logger.warning(f"No valid audio data generated for client {client_id}")
                            else:
                                try:
                                    # Try to parse as JSON control message
                                    text_data = message.get('text', '{}')
                                    control_message = json.loads(text_data)
                                    if isinstance(control_message, dict):
                                        msg_type = control_message.get('type')
                                        if msg_type in ['start_session', 'stop_session', 'pause_session', 'resume_session']:
                                            self.logger.info(f"Received control message {msg_type} from client {client_id}")
                                            # Handle session state changes here if needed
                                except json.JSONDecodeError:
                                    self.logger.error(f"Received message without bytes from client {client_id}: {message}")
                        else:
                            self.logger.warning(f"Unexpected message type from client {client_id}: {message_type}")
                    
                    except WebSocketDisconnect:
                        self.logger.info(f"WebSocket disconnect detected for client {client_id}")
                        break
                    except Exception as frame_error:
                        self.logger.error(
                            f"Error processing frame for client {client_id}: {str(frame_error)}\n"
                            f"Error type: {type(frame_error).__name__}\n"
                            f"Traceback: {traceback.format_exc()}"
                        )
                        # Don't disconnect, try to continue with next frame
                        continue
                    
            finally:
                # Always clean up the connection
                self.logger.info(f"Cleaning up connection for client {client_id}")
                await self.manager.disconnect(websocket, client_id)
                
        except Exception as e:
            self.logger.error(
                f"Error setting up video stream for client {client_id}: {str(e)}\n"
                f"Error type: {type(e).__name__}\n"
                f"Traceback: {traceback.format_exc()}"
            )
            try:
                await websocket.close(code=1011)
            except:
                pass
            finally:
                await self.manager.disconnect(websocket, client_id)

    # ... rest of the existing code ... 