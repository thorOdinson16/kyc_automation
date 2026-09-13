# AI-Powered KYC Backend

FastAPI backend for the AI-powered KYC onboarding pipeline: document upload,
dual OCR (EasyOCR + Tesseract), FaceNet verification, Mediapipe liveness,
BERT entity extraction, XGBoost risk scoring, SHAP explainability, and an
append-only audit log.

Documents may be uploaded as images (JPEG/PNG/WebP) or PDFs. PDFs with a text
layer are parsed directly; scanned PDFs are rasterized (PyMuPDF) and OCR'd, and
an ID PDF's photo is rendered for face matching.

## Document verification

Each upload is checked against its slot:

- **ID** must be a recognized type - Aadhaar (12-digit, Verhoeff-checked), PAN,
  Passport, Voter ID (EPIC) or Driving Licence - with a readable name.
- **Utility bill** must look like a bill and contain the applicant's name. Any
  bill type is accepted (electricity, water, gas, telecom, internet,
  subscription, property tax, or a generic invoice with the name).
- **Address proof** must be a known address document (Aadhaar, passport, voter
  ID, DL, utility bill, bank statement, rent/lease, property tax) or contain an
  address.

Misplaced documents are detected after upload (`POST /verification/{id}/precheck`)
and can be moved between slots (`PATCH /documents/{id}`). The pipeline also
auto-routes by detected content and sends anything unverifiable to
`review_required` - it never auto-approves on a mismatch.

PDFs are validated on upload (reject encrypted, corrupt, empty or over-page
files) and sanitized (JavaScript, launch actions and embedded files stripped)
before storage; `/view` serves them as attachments with `nosniff`.

## Security

- `POST /applications/` returns an **application token** bound to that
  application. Document routes (`upload`, `upload/liveness`, `view`, `PATCH`,
  `list`) accept either that scoped token or a reviewer/admin JWT, and always
  verify the token against the owning `application_id` (no bare-document IDOR).
- `/auth/login` is rate-limited by IP and IP+email (429 + `Retry-After`). With
  `REDIS_URL` set the counter is Redis-backed and shared across workers; if Redis
  is unreachable the limiter fails fast (~0.25s) to the in-process window, logs
  once at ERROR, and trips a circuit breaker for `REDIS_COOLDOWN_SECONDS`.
  Leave `REDIS_URL` empty for in-process-only limiting.
- Passwords use PBKDF2-HMAC-SHA256 (200k) with a constant-time comparison.
- Files are AES-256-GCM encrypted at rest; the audit log is append-only.
- The pipeline is guarded by a per-application Postgres advisory lock and is
  resumable: completed stages are recorded in the audit log and skipped on retry.
- Structured JSON request/stage logs are emitted (`LOG_JSON`, stage timings in
  `/verification/{id}/progress` and `/results`). Never log OCR text or entities.

See the root `README.md` for the full threat model.

## Requirements

- Python 3.10+
- PostgreSQL 14+ with the `pgvector` extension
- Redis (optional; set `REDIS_URL` for cross-worker login rate limiting. If
  unset, limiting is in-process. If set but down, the limiter fails fast to the
  in-process window, logs once, and backs off via a circuit breaker.)
- Tesseract (used as the OCR fallback). On Windows: `scoop install tesseract`
  (or the UB Mannheim installer), plus the `eng.traineddata` language file.
  The path can be forced with `TESSERACT_CMD` in `.env`.

## Setup

This project depends on `numpy<2`, `protobuf<5` and a pinned Mediapipe version
that conflict with other common packages (e.g. `ultralytics`/`trackers` want
`numpy>=2` and `google-api-core` wants `protobuf>=5.29`). It therefore lives in
its own virtual environment so the system interpreter stays untouched.

### Reuse the system PyTorch build (recommended on this machine)

```bash
cd backend
python -m venv --system-site-packages venv
venv\Scripts\activate                       # *nix: source venv/bin/activate
python -m pip install --upgrade pip

# Project-specific pins (local copies shadow the system ones)
pip install --ignore-installed --no-deps ^
    numpy==1.26.4 protobuf==4.25.9 mediapipe==0.10.21 ^
    easyocr shap pytesseract facenet-pytorch==2.6.0

pip install -r requirements.txt
```

`facenet-pytorch` is installed with `--no-deps` because its metadata pins
`torch<2.3`/`torchvision<0.18`; the code itself works fine with the installed
`torch 2.10` / `torchvision 0.25`.

### Fully isolated alternative (downloads its own PyTorch)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install --no-deps facenet-pytorch==2.6.0
```


Create the database and enable pgvector:

```sql
CREATE DATABASE kyc_db;
\c kyc_db
CREATE EXTENSION IF NOT EXISTS vector;
```

### Installing pgvector

Most Linux/macOS packages ship prebuilt (e.g. `apt install postgresql-18-pgvector`).
On Windows with the EDB PostgreSQL 18 installer, build it once from source in an
**administrator** "x64 Native Tools Command Prompt for VS":

```cmd
set "PGROOT=C:\Program Files\PostgreSQL\18"
git clone --branch v0.8.6 https://github.com/pgvector/pgvector.git %TEMP%\pgvector
cd /d %TEMP%\pgvector
nmake /F Makefile.win
nmake /F Makefile.win install
```

Alternatives: the EDB **StackBuilder** (pgvector package) or Docker
`pgvector/pgvector:pg18`.

Verify:

```sql
SELECT extversion FROM pg_extension WHERE extname = 'vector';
```

Copy `.env.example` to `.env` and set `DATABASE_URL`, `SECRET_KEY`, and
`ENCRYPTION_KEY` (base64 of 32 random bytes). Generate a key with:

```bash
python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Then run migrations and seed:

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

Pytest uses the `.env.test` database and runs the KYC pipeline synchronously
(`RUN_SYNC`). The AI models are stubbed for speed; real services were verified
separately. The per-application pipeline lock is stress-tested under repeated
concurrent triggers in `tests/test_pipeline_lock_stress.py`.

```bash
set PYTEST=1
venv\Scripts\python -m pytest -s
```

## API overview

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/applications/` | - | Create application (returns app token) |
| GET | `/api/v1/applications/` | reviewer/admin | List applications |
| POST | `/api/v1/applications/{id}/override` | reviewer/admin | Override decision |
| POST | `/api/v1/documents/{id}/upload` | owner/staff | Upload a document |
| POST | `/api/v1/documents/{id}/upload/liveness` | owner/staff | Upload liveness frames |
| GET | `/api/v1/documents/{id}/view` | owner/staff | Download a document |
| PATCH | `/api/v1/documents/{id}` | owner/staff | Reclassify a document |
| GET | `/api/v1/documents/application/{id}/list` | owner/staff | List documents |
| POST | `/api/v1/verification/{id}/process` | - | Run/resume the pipeline |
| GET | `/api/v1/verification/{id}/results` | - | Fetch results |
| GET | `/api/v1/audit/{id}/trail` | - | Fetch audit trail |
| POST | `/api/v1/auth/login` | - | Obtain a JWT (rate-limited) |

`owner/staff` = the applicant's application token for this application, or a
reviewer/admin JWT.
