import asyncio
from typing import Dict, List, Sequence, Union

import cv2
import mediapipe as mp
import numpy as np

from app.config import settings

LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]


class LivenessService:
    """Mediapipe-based liveness using blink and inter-frame motion cues."""

    def __init__(self):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.ear_threshold = settings.LIVENESS_EAR_THRESHOLD
        self.motion_threshold = settings.LIVENESS_MOTION_THRESHOLD

    def _eye_aspect_ratio(self, landmarks, indices) -> float:
        points = np.array([[landmarks[i].x, landmarks[i].y] for i in indices])
        vertical = np.linalg.norm(points[1] - points[5]) + np.linalg.norm(
            points[2] - points[4]
        )
        horizontal = np.linalg.norm(points[0] - points[3])
        return float(vertical / (2 * horizontal + 1e-9))

    def _count_blinks(self, ears: List[float]) -> int:
        """Count blinks using a baseline-relative drop in eye aspect ratio.

        A fixed threshold misses blinks for narrow-eyed faces; anchoring to the
        median EAR (with a small absolute floor) is far more reliable.
        """
        if not ears:
            return 0

        baseline = float(np.median(ears))
        threshold = max(self.ear_threshold, baseline * 0.85)

        blink_count = 0
        below_threshold = False
        for ear in ears:
            if ear < threshold and not below_threshold:
                blink_count += 1
                below_threshold = True
            elif ear >= threshold:
                below_threshold = False
        return blink_count

    def _analyse_sync(self, frame_paths: Sequence[str]) -> Dict:
        ears: List[float] = []
        motions: List[float] = []
        previous_points = None
        faces_detected = 0

        for path in frame_paths:
            image = cv2.imread(path)
            if image is None:
                continue

            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb)

            if not results.multi_face_landmarks:
                previous_points = None
                continue

            faces_detected += 1
            landmarks = results.multi_face_landmarks[0].landmark

            ear = (
                self._eye_aspect_ratio(landmarks, LEFT_EYE)
                + self._eye_aspect_ratio(landmarks, RIGHT_EYE)
            ) / 2
            ears.append(ear)

            points = np.array([[lm.x, lm.y] for lm in landmarks])
            if previous_points is not None:
                motions.append(
                    float(np.mean(np.linalg.norm(points - previous_points, axis=1)))
                )
            previous_points = points

        blink_count = self._count_blinks(ears)

        motion = float(np.mean(motions)) if motions else 0.0
        frames_processed = len(frame_paths)

        blink_score = min(blink_count / 1.0, 1.0)
        motion_score = min(motion / (self.motion_threshold * 3), 1.0)
        face_score = min(faces_detected / max(frames_processed, 1), 1.0)

        confidence = 0.5 * blink_score + 0.3 * motion_score + 0.2 * face_score
        is_live = faces_detected >= 2 and (
            blink_count >= 1 or motion > self.motion_threshold
        )

        return {
            "is_live": bool(is_live),
            "confidence": float(confidence),
            "blink_count": int(blink_count),
            "motion": float(motion),
            "faces_detected": int(faces_detected),
            "frames_processed": int(frames_processed),
            "method": "mediapipe",
        }

    async def detect_liveness(self, frames: Union[str, Sequence[str]]) -> Dict:
        if isinstance(frames, str):
            frame_paths = [frames]
        else:
            frame_paths = list(frames)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._analyse_sync, frame_paths)


liveness_service = LivenessService()
