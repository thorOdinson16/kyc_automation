from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import os
import base64
import tempfile
from typing import Tuple


class EncryptionService:
    def __init__(self, encryption_key: str):
        self.key = base64.urlsafe_b64decode(encryption_key.encode())

    async def encrypt_file(self, file_path: str) -> Tuple[str, str]:
        """Encrypt file using AES-256 and return encrypted path"""

        with open(file_path, 'rb') as f:
            data = f.read()

        iv = os.urandom(16)

        cipher = Cipher(
            algorithms.AES(self.key),
            modes.CBC(iv),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()

        padded_data = self._pad_data(data)
        encrypted_data = encryptor.update(padded_data) + encryptor.finalize()

        encrypted_path = file_path + ".enc"
        with open(encrypted_path, "wb") as f:
            f.write(iv + encrypted_data)

        os.remove(file_path)

        return encrypted_path, base64.b64encode(iv).decode()

    async def decrypt_file(self, encrypted_path: str) -> str:
        """
        DECRYPT + RETURN A REAL FILE PATH (string).
        This is required for cv2.imread, OCR, and tests.
        """

        with open(encrypted_path, "rb") as f:
            data = f.read()

        iv = data[:16]
        encrypted_data = data[16:]

        cipher = Cipher(
            algorithms.AES(self.key),
            modes.CBC(iv),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()

        decrypted = decryptor.update(encrypted_data) + decryptor.finalize()
        decrypted = self._unpad_data(decrypted)

        # Write to temp image file
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(decrypted)
        tmp.flush()

        return tmp.name  # REAL PATH (string)

    def encrypt_text(self, text: str) -> str:
        fernet = Fernet(base64.urlsafe_b64encode(self.key))
        return fernet.encrypt(text.encode()).decode()

    def decrypt_text(self, encrypted_text: str) -> str:
        fernet = Fernet(base64.urlsafe_b64encode(self.key))
        return fernet.decrypt(encrypted_text.encode()).decode()

    def _pad_data(self, data: bytes) -> bytes:
        padding_length = 16 - (len(data) % 16)
        return data + bytes([padding_length] * padding_length)

    def _unpad_data(self, data: bytes) -> bytes:
        padding_length = data[-1]
        return data[:-padding_length]


from app.config import settings
encryption_service = EncryptionService(settings.ENCRYPTION_KEY)