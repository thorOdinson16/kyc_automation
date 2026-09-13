import base64
import os
import tempfile
from typing import Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.fernet import Fernet

from app.config import settings

_NONCE_SIZE = 12


class EncryptionService:
    """AES-256-GCM authenticated encryption for PII at rest."""

    def __init__(self, encryption_key: str):
        try:
            key = base64.urlsafe_b64decode(encryption_key.encode())
        except Exception as exc:  # pragma: no cover - configuration error
            raise ValueError("ENCRYPTION_KEY must be a valid base64 value") from exc

        if len(key) != 32:
            raise ValueError("ENCRYPTION_KEY must decode to 32 bytes (AES-256)")

        self.key = key
        self._aead = AESGCM(key)

    async def encrypt_file(self, file_path: str) -> Tuple[str, str]:
        """Encrypt a file with AES-256-GCM.

        Returns ``(encrypted_path, nonce_b64)``. The stored layout is
        ``nonce || ciphertext || tag``.
        """
        with open(file_path, "rb") as handle:
            data = handle.read()

        nonce = os.urandom(_NONCE_SIZE)
        ciphertext = self._aead.encrypt(nonce, data, None)

        encrypted_path = file_path + ".enc"
        with open(encrypted_path, "wb") as handle:
            handle.write(nonce + ciphertext)

        os.remove(file_path)

        return encrypted_path, base64.b64encode(nonce).decode()

    async def decrypt_file(self, encrypted_path: str) -> str:
        """Decrypt a file and return the path to a temporary plaintext copy."""
        with open(encrypted_path, "rb") as handle:
            blob = handle.read()

        nonce, ciphertext = blob[:_NONCE_SIZE], blob[_NONCE_SIZE:]
        plaintext = self._aead.decrypt(nonce, ciphertext, None)

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(plaintext)
        tmp.flush()
        tmp.close()

        return tmp.name

    def encrypt_text(self, text: str) -> str:
        fernet = Fernet(base64.urlsafe_b64encode(self.key))
        return fernet.encrypt(text.encode()).decode()

    def decrypt_text(self, encrypted_text: str) -> str:
        fernet = Fernet(base64.urlsafe_b64encode(self.key))
        return fernet.decrypt(encrypted_text.encode()).decode()


encryption_service = EncryptionService(settings.ENCRYPTION_KEY)
