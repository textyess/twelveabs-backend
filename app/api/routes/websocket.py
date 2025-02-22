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
        try:
            logger.info(f"Attempting video stream WebSocket connection for client_id: {client_id}")
            await websocket.accept()
            logger.info(f"WebSocket accepted for client_id: {client_id}")
            
            await self.manager.connect(websocket, client_id)
            
            if exercise_type:
                self.manager.update_exercise_type(client_id, exercise_type)
            
            self.manager.toggle_audio(client_id, audio_enabled)
            last_process_time = 0
            is_disconnected = False
            
            try:
                while not is_disconnected:
                    try:
                        message = await websocket.receive()
                    except WebSocketDisconnect:
                        logger.info(f"Video stream disconnected for client_id: {client_id}")
                        is_disconnected = True
                        break
                    
                    # Check if this is a control message
                    if message.get('type') == 'websocket.receive' and 'text' in message:
                        try:
                            control_data = json.loads(message['text'])
                            if isinstance(control_data, dict):
                                if control_data.get('type') == 'stop_session':
                                    logger.info(f"Received stop session request from client_id: {client_id}")
                                    session = self.manager.user_sessions.get(client_id)
                                    if session:
                                        session.is_active = False
                                    await websocket.send_text(json.dumps({
                                        "type": "session_stopped",
                                        "data": "Session stopped successfully"
                                    }))
                                    continue
                                elif control_data.get('type') == 'start_session':
                                    logger.info(f"Received start session request from client_id: {client_id}")
                                    session = self.manager.user_sessions.get(client_id)
                                    if session:
                                        session.is_active = True
                                    await websocket.send_text(json.dumps({
                                        "type": "session_started",
                                        "data": "Session started successfully"
                                    }))
                                    continue
                                elif control_data.get('type') == 'pause_session':
                                    logger.info(f"Received pause session request from client_id: {client_id}")
                                    session = self.manager.user_sessions.get(client_id)
                                    if session:
                                        session.is_active = False
                                    await websocket.send_text(json.dumps({
                                        "type": "session_paused",
                                        "data": "Session paused successfully"
                                    }))
                                    continue
                                elif control_data.get('type') == 'resume_session':
                                    logger.info(f"Received resume session request from client_id: {client_id}")
                                    session = self.manager.user_sessions.get(client_id)
                                    if session:
                                        session.is_active = True
                                    await websocket.send_text(json.dumps({
                                        "type": "session_resumed",
                                        "data": "Session resumed successfully"
                                    }))
                                    continue
                        except json.JSONDecodeError:
                            pass  # Not a JSON message, treat as frame data
                    
                    current_time = time.time() * 1000
                    session = self.manager.user_sessions.get(client_id)
                    
                    # Only process frames if session is active and enough time has passed
                    if session and session.is_active and current_time - last_process_time >= 1000:
                        if message.get('type') == 'websocket.receive':
                            try:
                                if isinstance(message.get('bytes'), bytes):
                                    frame_data = base64.b64encode(message.get('bytes')).decode('utf-8')
                                elif 'text' in message:
                                    frame_data = message.get('text', '')
                                else:
                                    logger.error(f"Unsupported message format from client_id: {client_id}")
                                    continue

                                current_exercise = session.exercise_type
                                
                                logger.info(f"Processing video frame for client_id: {client_id}")
                                feedback_text = await self.vision_service.analyze_frame(frame_data, current_exercise)
                                
                                if not session.is_active:
                                    logger.info(f"Session no longer active, skipping feedback for client_id: {client_id}")
                                    continue

                                if feedback_text and not feedback_text.startswith("Error analyzing frame"):
                                    feedback_data = {
                                        "timestamp": datetime.now().isoformat(),
                                        "feedback": feedback_text,
                                        "exercise_type": current_exercise,
                                        "audio_available": self.manager.can_generate_audio(client_id)
                                    }
                                    
                                    self.manager.add_feedback(client_id, feedback_data)
                                    session.last_activity = datetime.now()
                                    
                                    if session.is_active:
                                        try:
                                            await self.manager.send_message(
                                                json.dumps(feedback_data),
                                                client_id,
                                                "text"
                                            )
                                        
                                            if self.manager.can_generate_audio(client_id):
                                                try:
                                                    logger.info(f"Generating audio feedback for video frame")
                                                    audio_data = await self.manager.audio_manager.generate_feedback(
                                                        feedback_text,
                                                        session.voice_id,
                                                        session.voice_settings
                                                    )
                                                    if audio_data and session.is_active:
                                                        logger.info(f"Sending audio feedback of size {len(audio_data)} bytes")
                                                        await self.manager.send_audio(audio_data, client_id)
                                                    else:
                                                        logger.info("Skipping audio feedback - session not active or no audio data")
                                                except Exception as audio_e:
                                                    logger.error(f"Error generating audio for video frame: {str(audio_e)}")
                                                    if session.is_active:
                                                        await websocket.send_text(json.dumps({
                                                            "type": "error",
                                                            "data": "Failed to generate audio feedback"
                                                        }))
                                        except WebSocketDisconnect:
                                            logger.info(f"Client disconnected while sending feedback: {client_id}")
                                            is_disconnected = True
                                            break
                                
                                last_process_time = current_time
                                
                            except Exception as frame_e:
                                logger.error(f"Error processing video frame: {str(frame_e)}")
                                try:
                                    await websocket.send_text(json.dumps({
                                        "type": "error",
                                        "data": f"Error processing frame: {str(frame_e)}"
                                    }))
                                except WebSocketDisconnect:
                                    logger.info(f"Client disconnected while sending error: {client_id}")
                                    is_disconnected = True
                                    break
                
            except WebSocketDisconnect:
                logger.info(f"Video stream disconnected for client_id: {client_id}")
            finally:
                self.manager.disconnect(client_id)
                logger.info(f"Cleaned up session for client_id: {client_id}")
                
        except Exception as outer_e:
            logger.error(f"Error during video stream setup for client_id: {client_id}: {str(outer_e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            try:
                await websocket.close(code=1011, reason=str(outer_e))
            except:
                pass
            finally:
                self.manager.disconnect(client_id) 