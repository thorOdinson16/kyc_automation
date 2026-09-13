import asyncio
import tempfile
from typing import Tuple

import numpy as np
import torch
from facenet_pytorch import InceptionResnetV1, MTCNN
from PIL import Image


class FaceService:
    """One-to-one face verification using FaceNet (InceptionResnetV1) + MTCNN."""

    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._detector = None
        self._model = None
        self.similarity_threshold = 0.6

    @property
    def detector(self):
        if self._detector is None:
            self._detector = MTCNN(keep_all=False, device=self.device)
        return self._detector

    @property
    def model(self):
        if self._model is None:
            self._model = InceptionResnetV1(pretrained="vggface2").eval().to(self.device)
        return self._model

    async def _ensure_filepath(self, src) -> str:
        if isinstance(src, str):
            return src

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(src.read())
        tmp.flush()
        tmp.close()
        return tmp.name

    def _embedding_sync(self, image_path: str) -> np.ndarray:
        image = Image.open(image_path).convert("RGB")
        face = self.detector(image)

        if face is None:
            raise ValueError("No face detected")

        face = face.unsqueeze(0).to(self.device)
        with torch.no_grad():
            embedding = self.model(face).cpu().numpy()[0]
        return embedding

    async def extract_face_embedding(self, image_path) -> np.ndarray:
        path = await self._ensure_filepath(image_path)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._embedding_sync, path)

    async def verify_faces(self, selfie_path, id_photo_path) -> dict:
        selfie_embedding = await self.extract_face_embedding(selfie_path)
        id_embedding = await self.extract_face_embedding(id_photo_path)

        similarity = float(
            np.dot(selfie_embedding, id_embedding)
            / (np.linalg.norm(selfie_embedding) * np.linalg.norm(id_embedding) + 1e-9)
        )

        return {
            "is_match": similarity >= self.similarity_threshold,
            "similarity": similarity,
            "selfie_embedding": selfie_embedding,
            "id_embedding": id_embedding,
        }


face_service = FaceService()
