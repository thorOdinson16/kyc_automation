from keras_facenet import FaceNet
from mtcnn import MTCNN
import numpy as np
import cv2
from PIL import Image
import asyncio
from typing import Tuple
import tempfile
import os


class FaceService:
    def __init__(self):
        self.detector = MTCNN()
        self.facenet = FaceNet()
        self.similarity_threshold = 0.6

    async def _ensure_filepath(self, src) -> str:
        """
        Accepts:
        - string file path  -> return as is
        - file-like object  -> save to temp file and return path

        This fixes pytest + ASGITransport issues.
        """
        if isinstance(src, str):
            return src  # already a valid path

        # src is a SpooledTemporaryFile or UploadFile.file
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(src.read())
        tmp.flush()
        return tmp.name

    async def extract_face_embedding(self, image_path) -> np.ndarray:
        loop = asyncio.get_event_loop()

        image_path = await self._ensure_filepath(image_path)

        img = await loop.run_in_executor(None, cv2.imread, image_path)
        if img is None:
            raise ValueError(f"Invalid image path: {image_path}")

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        detections = self.detector.detect_faces(img_rgb)
        if len(detections) == 0:
            raise ValueError("No face detected")

        x, y, w, h = detections[0]['box']
        face = img_rgb[y:y + h, x:x + w]

        # 🔥 FIX: resize using cv2 (FaceNet needs numpy array)
        face_np = cv2.resize(face, (160, 160))

        # 🔥 FIX: embeddings() must receive numpy arrays, NOT PIL
        embedding = await loop.run_in_executor(None, self.facenet.embeddings, [face_np])
        return embedding[0]

    async def verify_faces(self, selfie_path, id_photo_path) -> Tuple[bool, float]:
        emb1 = await self.extract_face_embedding(selfie_path)
        emb2 = await self.extract_face_embedding(id_photo_path)

        similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
        is_match = similarity >= self.similarity_threshold

        return is_match, float(similarity)


face_service = FaceService()