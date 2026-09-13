import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"   
os.environ["KMP_WARNINGS"] = "0"

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from app.config import settings
from app.core.logging_config import configure_logging
from app.api.v1 import applications, documents, verification, audit, auth

configure_logging()
logger = logging.getLogger("app.request")

app = FastAPI(
    title="AI-Powered KYC System",
    description="Backend API for automated KYC onboarding",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security Middleware
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Attach a request id and emit one structured timing log per request."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = request_id
    start = time.perf_counter()

    response = await call_next(request)

    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


# Include routers
app.include_router(applications.router, prefix=f"{settings.API_V1_PREFIX}/applications", tags=["Applications"])
app.include_router(documents.router, prefix=f"{settings.API_V1_PREFIX}/documents", tags=["Documents"])
app.include_router(verification.router, prefix=f"{settings.API_V1_PREFIX}/verification", tags=["Verification"])
app.include_router(audit.router, prefix=f"{settings.API_V1_PREFIX}/audit", tags=["Audit"])
app.include_router(auth.router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["Auth"])

@app.get("/")
async def root():
    return {"message": "AI-Powered KYC API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
