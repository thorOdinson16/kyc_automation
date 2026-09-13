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

    async def encrypt_file(
        self, file_path: str, output_dir: str | None = None
    ) -> Tuple[str, str]:
        """Encrypt a file with AES-256-GCM.

        Returns ``(encrypted_path, nonce_b64)``. The stored layout is
        ``nonce || ciphertext || tag``. When ``output_dir`` is given the
        encrypted artifact is written there (as ``<basename>.enc``) instead of
        alongside the plaintext; the plaintext is always removed.
        """
        with open(file_path, "rb") as handle:
            data = handle.read()

        nonce = os.urandom(_NONCE_SIZE)
        ciphertext = self._aead.encrypt(nonce, data, None)

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            encrypted_path = os.path.join(
                output_dir, os.path.basename(file_path) + ".enc"
            )
        else:
            encrypted_path = file_path + ".enc"

        with open(encrypted_path, "wb") as handle:
            handle.write(nonce + ciphertext)

        os.remove(file_path)

        return encrypted_path, base64.b64encode(nonce).decode()

    @staticmethod
    def remove_temp_file(path: str | None) -> None:
        """Best-effort delete of a decrypted plaintext temp file."""
        if not path:
            return
        try:
            os.remove(path)
        except OSError:
            pass

    async def decrypt_file(self, encrypted_path: str, suffix: str = ".jpg") -> str:
        """Decrypt a file and return the path to a temporary plaintext copy."""
        with open(encrypted_path, "rb") as handle:
            blob = handle.read()

        nonce, ciphertext = blob[:_NONCE_SIZE], blob[_NONCE_SIZE:]
        plaintext = self._aead.decrypt(nonce, ciphertext, None)

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
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
