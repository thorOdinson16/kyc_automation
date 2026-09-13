import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta

from fastapi.security import OAuth2PasswordBearer
from jose import jwt

from app.config import settings

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 200_000


class SecurityService:
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES

    def hash_password(self, password: str) -> str:
        salt = os.urandom(16)
        derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
        return "$".join(
            [
                _ALGORITHM,
                str(_ITERATIONS),
                base64.b64encode(salt).decode(),
                base64.b64encode(derived).decode(),
            ]
        )

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        if not hashed_password:
            return False
        try:
            algorithm, iterations, salt_b64, hash_b64 = hashed_password.split("$")
            if algorithm != _ALGORITHM:
                return False
            salt = base64.b64decode(salt_b64)
            expected = base64.b64decode(hash_b64)
            derived = hashlib.pbkdf2_hmac(
                "sha256", plain_password.encode(), salt, int(iterations)
            )
            return hmac.compare_digest(derived, expected)
        except (ValueError, TypeError):
            return False

    def create_access_token(self, data: dict, expires_delta: timedelta = None) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + (
            expires_delta or timedelta(minutes=self.access_token_expire_minutes)
        )
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def decode_token(self, token: str):
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except Exception:
            return None


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")

security = SecurityService()
