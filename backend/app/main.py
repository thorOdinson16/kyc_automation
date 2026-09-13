import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"   
os.environ["KMP_WARNINGS"] = "0"

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from app.config import settings
from app.api.v1 import applications, documents, verification, audit, auth

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