from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limit import login_rate_limiter
from app.core.security import oauth2_scheme, security
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter()


async def _enforce_login_rate_limit(request: Request, email: str) -> None:
    """Limit by client IP and by IP+email to blunt both spraying and guessing."""
    if not settings.RATE_LIMIT_ENABLED:
        return

    client_ip = request.client.host if request.client else "unknown"
    for key in (
        f"login:ip:{client_ip}",
        f"login:ip:{client_ip}:{email.lower()}",
    ):
        allowed, retry_after = await login_rate_limiter.check(
            key,
            settings.LOGIN_RATE_LIMIT,
            settings.LOGIN_RATE_WINDOW_SECONDS,
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a reviewer/admin/applicant and return a JWT."""
    await _enforce_login_rate_limit(request, payload.email)

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    role = user.role.value if user.role else "applicant"
    token = security.create_access_token({"sub": str(user.user_id), "role": role})
    return TokenResponse(access_token=token, role=role)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = security.decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return payload


def require_role(*roles: str):
    async def check(user: dict = Depends(get_current_user)) -> dict:
        if roles and user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return check
