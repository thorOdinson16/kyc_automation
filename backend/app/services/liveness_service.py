import mediapipe as mp
import cv2
import numpy as np
from typing import Dict
import asyncio

class LivenessService:
    def __init__(self):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.blink_threshold = 0.2
        self.motion_threshold = 0.05
    
    async def detect_liveness(self, video_path: str) -> Dict:
        """Detect liveness using blink and motion detection"""
        loop = asyncio.get_event_loop()
        
        cap = cv2.VideoCapture(video_path)
        
        blink_count = 0
        motion_detected = False
        frames_processed = 0
        prev_landmarks = None
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            # Convert to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Process frame
            results = self.face_mesh.process(rgb_frame)
            
            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0]
                
                # Detect blinks
                ear = self._calculate_ear(landmarks)
                if ear < self.blink_threshold:
                    blink_count += 1
                
                # Detect motion
                if prev_landmarks is not None:
                    motion = self._calculate_motion(landmarks, prev_landmarks)
                    if motion > self.motion_threshold:
                        motion_detected = True
                
                prev_landmarks = landmarks
            
            frames_processed += 1
        
        cap.release()
        
        # Calculate confidence
        liveness_confidence = self._calculate_confidence(
            blink_count, motion_detected, frames_processed
        )
        
        return {
            'liveness_detected': liveness_confidence > 0.5,
            'confidence': liveness_confidence,
            'blink_count': blink_count,
            'motion_detected': motion_detected,
            'frames_processed': frames_processed
        }
    
    def _calculate_ear(self, landmarks) -> float:
        """Calculate Eye Aspect Ratio for blink detection"""
        # Simplified EAR calculation
        # Use specific landmark indices for eyes
        left_eye = [landmarks.landmark[i] for i in [33, 160, 158, 133, 153, 144]]
        
        # Calculate vertical distances
        vertical = np.linalg.norm(
            np.array([left_eye[1].y, left_eye[1].x]) - 
            np.array([left_eye[5].y, left_eye[5].x])
        )
        
        # Calculate horizontal distance
        horizontal = np.linalg.norm(
            np.array([left_eye[0].y, left_eye[0].x]) - 
            np.array([left_eye[3].y, left_eye[3].x])
        )
        
        ear = vertical / horizontal if horizontal > 0 else 0
        return ear
    
    def _calculate_motion(self, current, previous) -> float:
        """Calculate motion between frames"""
        current_points = np.array([[lm.x, lm.y] for lm in current.landmark])
        prev_points = np.array([[lm.x, lm.y] for lm in previous.landmark])
        
        motion = np.mean(np.linalg.norm(current_points - prev_points, axis=1))
        return motion
    
    def _calculate_confidence(self, blinks: int, motion: bool, frames: int) -> float:
        """Calculate overall liveness confidence"""
        blink_score = min(blinks / 3, 1.0) * 0.6  # Expect at least 3 blinks
        motion_score = 0.4 if motion else 0
        
        return blink_score + motion_score

liveness_service = LivenessService()