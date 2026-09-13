# AI-Powered KYC Backend

FastAPI backend for the AI-powered KYC onboarding pipeline: document upload,
dual OCR (EasyOCR + Tesseract), FaceNet verification, Mediapipe liveness,
BERT entity extraction, XGBoost risk scoring, SHAP explainability, and an
append-only audit log.

## Requirements

- Python 3.10+
- PostgreSQL 14+ with the `pgvector` extension
- Tesseract (optional; used only as an OCR fallback)

## Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Windows; use source venv/bin/activate on *nix
pip install -r requirements.txt
pip install --no-deps facenet-pytorch==2.6.0   # avoids the stale torch<2.3 pin
```

Create the database and enable pgvector:

```sql
CREATE DATABASE kyc_db;
\c kyc_db
CREATE EXTENSION IF NOT EXISTS vector;
```

Copy `.env.example` to `.env` and set `DATABASE_URL`, `SECRET_KEY`, and
`ENCRYPTION_KEY` (base64 of 32 random bytes).

Generate a valid encryption key:

```bash
python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Run migrations and seed accounts:

```bash
alembic upgrade head
python -m scripts.seed_users
```

## Run

```bash
python run.py           # HTTP on :8000
python run.py --tls     # HTTPS with TLS 1.3 (set SSL_CERTFILE / SSL_KEYFILE)
```

Seeded accounts: `reviewer@kyc.ai / review123`, `admin@kyc.ai / admin123`,
`applicant@kyc.ai / applicant123`.

## Test

```bash
set PYTEST=1
pytest -s
```

## API overview

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/applications/` | - | Create application |
| GET | `/api/v1/applications/` | reviewer/admin | List applications |
| POST | `/api/v1/applications/{id}/override` | reviewer/admin | Override decision |
| POST | `/api/v1/documents/{id}/upload` | - | Upload a document |
| POST | `/api/v1/documents/{id}/upload/liveness` | - | Upload liveness frames |
| POST | `/api/v1/verification/{id}/process` | - | Run the pipeline |
| GET | `/api/v1/verification/{id}/results` | - | Fetch results |
| GET | `/api/v1/audit/{id}/trail` | - | Fetch audit trail |
| POST | `/api/v1/auth/login` | - | Obtain a JWT |
