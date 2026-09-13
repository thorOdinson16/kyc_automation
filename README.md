# KYC Automation

An AI-powered **Know Your Customer (KYC)** onboarding platform that automates document
collection, identity verification, risk scoring, explainability and compliance auditing.

Upload an ID, an address proof, a utility bill and a short selfie liveness capture; the
pipeline extracts the data, verifies the person, scores the risk, explains the decision and
keeps a tamper-evident audit trail — in seconds.

- Backend: **FastAPI** (async) + **PostgreSQL/pgvector**
- Frontend: **React + Vite + TailwindCSS**
- AI: **EasyOCR**, **Tesseract**, **FaceNet**, **Mediapipe**, **BERT**, **XGBoost**, **SHAP**

---

## Table of contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Technology stack](#technology-stack)
4. [Document verification policy](#document-verification-policy)
5. [Security & compliance](#security--compliance)
6. [Prerequisites](#prerequisites)
7. [Setup](#setup)
8. [Run](#run)
9. [Testing](#testing)
10. [API reference](#api-reference)
11. [Project layout](#project-layout)
12. [Troubleshooting](#troubleshooting)

---

## Features

- **Multi-format uploads** — JPEG / PNG / WebP images **and PDFs** for the ID, address proof
  and utility bill. PDFs with a text layer are parsed directly; scanned PDFs are rasterized
  and OCR'd.
- **Dual OCR** — EasyOCR (GPU-accelerated when CUDA is available) with a Tesseract fallback.
  Text blocks are reconstructed into reading-order lines.
- **Face verification** — FaceNet (InceptionResnetV1) + MTCNN one-to-one selfie ↔ ID match.
- **Liveness** — Mediapipe blink + motion analysis over a short selfie frame sequence.
- **Entity extraction** — rule/label-first extraction (with a BERT NER fallback) for Name,
  Date of Birth, Address, ID number and PIN code.
- **Document verification** — confirms each upload really is the document its slot claims
  (Aadhaar/PAN/Passport/Voter/DL for ID; any name-matched bill; known address proofs) and
  auto-routes misplaced documents.
- **Risk scoring & decisioning** — XGBoost risk score with auto-approve / manual-review
  routing.
- **Explainability** — SHAP (TreeSHAP) feature contributions for every decision.
- **Immutable audit trail** — append-only `audit_logs` enforced by a PostgreSQL trigger.
- **RBAC** — JWT auth with applicant / reviewer / admin roles, **application-scoped
  tokens** for applicants, and IDOR-safe document access.
- **Hardened auth** — Redis-backed login rate limiting (IP and IP+email).
- **Idempotent, resumable pipeline** — one run per application via a Postgres
  advisory lock; completed stages are recorded in the audit log and skipped on retry.
- **Observability** — structured JSON logs and per-stage timings from the audit trail.
- **Live progress** — the Processing screen shows the real pipeline stage and elapsed time.

## Architecture

```
React (Vite)  ──REST──►  FastAPI
                            │
                            ├─► documents      (upload, MIME validation, PDF sanitize, encryption)
                            ├─► verification   (precheck, process, progress, results)
                            ├─► audit / auth   (trail, JWT login)
                            │
                            └─► core/pipeline  (orchestration)
                                   │
        ┌──────────────────────────┼────────────────────────────────────────┐
        ▼                          ▼                                        ▼
   OCR service            Face + Liveness services                Entity / Document
 (EasyOCR→Tesseract)   (FaceNet / Mediapipe)                  (rule + BERT, checks)
        │                          │                                        │
        └──────────────► Risk (XGBoost) ──► SHAP explainability ──► Decision
                                   │
                          PostgreSQL + pgvector (documents, embeddings,
                          risk scores, explainability, audit logs)
```

The pipeline is orchestrated in `backend/app/core/pipeline.py`:
`OCR → Face match → Liveness → Entities/Document checks → Risk → SHAP → Decision/audit`.

## Technology stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.10, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2 (async) |
| Database | PostgreSQL 14+ with `pgvector`; Alembic migrations |
| OCR | EasyOCR (GPU/CPU), Tesseract (fallback) |
| Vision | FaceNet (facenet-pytorch), MTCNN, Mediapipe FaceMesh |
| NLP | HuggingFace Transformers (BERT NER) |
| Risk | XGBoost + SHAP |
| PDF | PyMuPDF |
| Security | AES-256-GCM, PBKDF2 password hashing, JWT (python-jose), TLS 1.3 (optional) |
| Frontend | React 18, Vite 5, TailwindCSS, axios, react-router, react-hot-toast, react-webcam |

## Document verification policy

Each upload is checked against its slot **by content**, not just by format:

| Slot | Accepted | Rule |
| --- | --- | --- |
| **ID** | Aadhaar, PAN, Passport, Voter ID (EPIC), Driving Licence | Must be a recognised type (Aadhaar 12-digit is Verhoeff-checked) **and** yield a name |
| **Utility bill** | Any bill/invoice — electricity, water, gas, telecom, internet, subscription, property tax, or a generic receipt | Must look like a bill **and contain the applicant's name** (fuzzy match against the ID name). Address is optional |
| **Address proof** | Aadhaar, passport, voter ID, DL, utility bill, bank statement, rent/lease, property tax | Must be a known address document **or** carry a plausible address |

- Misplaced documents are detected after upload via `POST /verification/{id}/precheck` and can
  be moved with `PATCH /documents/{id}`; the pipeline also **auto-routes** by detected content.
- Any failed check is added to the application's mismatches and forces
  **`review_required`** — the system never auto-approves on a mismatch.

## Security & compliance

- **Encryption at rest** — AES-256-GCM (authenticated) for every uploaded file.
- **Encryption in transit** — optional TLS 1.3 via `python run.py --tls`.
- **Immutable audit** — `audit_logs` is append-only at the database level (trigger blocks
  `UPDATE`/`DELETE`).
- **PDF hardening** — uploads are validated (reject encrypted/corrupt/empty/over-page files)
  and sanitized (JavaScript, launch actions and embedded files stripped) before storage;
  downloads are served as attachments with `X-Content-Type-Options: nosniff`.
- **PII handling** — secrets come from `.env`; only a 32-byte base64 `ENCRYPTION_KEY` is used.
- **RBAC** — reviewer/admin actions (application list, decision override) require a JWT role.

### Threat model & security considerations

The controls above are deliberate responses to specific threats:

| Threat | Defense |
| --- | --- |
| **MIME spoofing** — uploading an executable/HTML payload labelled `image/jpeg` | The declared content type is ignored when magic bytes are present (`_detect_mime` in `documents.py`); files are then checked against an allowlist and rejected with 415. |
| **Malicious PDF** — embedded JavaScript, launch actions, embedded files, PDF bombs | Uploads are validated (reject encrypted/corrupt/empty/over-page-count) and sanitized (`pdf_service.validate_and_sanitize`) before storage; size is capped by `MAX_UPLOAD_SIZE`. |
| **XSS via downloaded documents** | Downloads use `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, and the frontend renders previews from authenticated blobs. |
| **Timing attacks on password verification** | PBKDF2-HMAC-SHA256 (200k iterations) with a constant-time `hmac.compare_digest` comparison. |
| **Credential stuffing / online password guessing** | Login is rate-limited by IP and IP+email (`app/core/rate_limit.py`), Redis-backed with a loud fail-open fallback. Returns 429 + `Retry-After`. |
| **IDOR** — reading or modifying another applicant's documents | Every document route resolves the owning `application_id` and allows only the application token holder or a reviewer/admin. Checks are tied to the application, not the bare document id. |
| **Token theft / privilege escalation** | Applicant tokens are scoped to a single `app_id` and carry no staff role; staff routes require an explicit role claim. |
| **PII exposure at rest / in transit** | AES-256-GCM authenticated encryption for stored files; optional TLS 1.3 (`python run.py --tls`). |
| **Audit tampering** | `audit_logs` is append-only enforced by a database trigger; pipeline resume state is derived from it, so "what happened" cannot be silently rewritten. |
| **Duplicate / replayed pipeline triggers** | A Postgres advisory lock (`app/core/pipeline_lock.py`) admits one run per application; completed runs are a no-op and stage outputs are idempotent. |
| **Cache outage taking down auth** | The rate limiter fails **open** (availability) but fails fast (~0.25s socket timeout, no exponential retries), logs the first failure at ERROR, then trips a circuit breaker for `REDIS_COOLDOWN_SECONDS` so the dead cache adds no per-request latency or log volume. |
| **Auth control silently no-op'ing** | Redis is opt-in via `REDIS_URL`; leave it empty to use the in-process limiter instead of a permanently-degraded Redis path. |

**Accepted residual risks / non-goals**

- The application token is stored in `localStorage` (XSS-reachable) and can be
  passed as a `?token=` query parameter for browser-initiated loads; tokens in
  URLs may leak via logs/caches/`Referer`. Prefer the `Authorization` header.
- The rate limiter fails open if Redis is unavailable (logged loudly).
- No MFA, device binding, or PII redaction beyond "never log OCR text/entities".

## Prerequisites

- Python **3.10+**
- PostgreSQL **14+** with **pgvector** (verified on PostgreSQL 18 + pgvector 0.8.6)
- **Tesseract OCR** + English language data (OCR fallback)
- Node.js **18+** (verified on 20)
- Optional: CUDA GPU for faster EasyOCR (verified on an RTX 5070)

## Setup

### 1. Backend environment

This project pins `numpy<2`, `protobuf<5` and `mediapipe==0.10.21`, which conflict with other
common packages. Keep it isolated in a virtual environment.

```bash
cd backend

# Reuse the system PyTorch (recommended where CUDA torch is already installed)
python -m venv --system-site-packages venv
venv\Scripts\activate                 # *nix: source venv/bin/activate
python -m pip install --upgrade pip
pip install --ignore-installed --no-deps ^
    numpy==1.26.4 protobuf==4.25.9 mediapipe==0.10.21 ^
    easyocr shap pytesseract facenet-pytorch==2.6.0
pip install -r requirements.txt
```

> `facenet-pytorch` is installed with `--no-deps` because its metadata pins `torch<2.3`;
> the code runs fine on newer torch. A fully isolated venv (without `--system-site-packages`)
> works too — it just downloads its own PyTorch.

### 2. PostgreSQL + pgvector

```sql
CREATE DATABASE kyc_db;
\c kyc_db
CREATE EXTENSION IF NOT EXISTS vector;
```

On Windows with the EDB PostgreSQL installer, build pgvector once in an **administrator**
"x64 Native Tools Command Prompt for VS":

```cmd
set "PGROOT=C:\Program Files\PostgreSQL\18"
git clone --branch v0.8.6 https://github.com/pgvector/pgvector.git %TEMP%\pgvector
cd /d %TEMP%\pgvector
nmake /F Makefile.win
nmake /F Makefile.win install
```

Run the database files as a normal command, then verify `SELECT extversion FROM pg_extension WHERE extname='vector';`.

On Linux/macOS install the packaged extension (e.g. `apt install postgresql-18-pgvector`).

### 3. Tesseract

```bash
# Windows (user-level)
scoop install tesseract
# then place eng.traineddata in the tessdata dir if not bundled, or set TESSERACT_CMD
```

### 4. Configuration

```bash
copy .env.example .env      # *nix: cp
```

Set at minimum:

| Variable | Description |
| --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@localhost:5432/kyc_db` |
| `DATABASE_URL_SYNC` | `postgresql://user:pass@localhost:5432/kyc_db` (Alembic) |
| `SECRET_KEY` | JWT signing secret |
| `ENCRYPTION_KEY` | base64 of 32 random bytes |
| `TESSERACT_CMD` | optional path to `tesseract.exe` |
| `OCR_USE_GPU` | `true` to use CUDA for EasyOCR when available |
| `LIVENESS_EAR_THRESHOLD` / `LIVENESS_MOTION_THRESHOLD` | liveness sensitivity |
| `PDF_MAX_PAGES` / `PDF_RENDER_DPI` | PDF processing limits |

Generate an encryption key:

```bash
python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

### 5. Migrate & seed

```bash
alembic upgrade head
python -m scripts.seed_users
```

## Run

```bash
# Backend (from backend/, venv active)
python run.py            # http://localhost:8000
python run.py --tls      # HTTPS with TLS 1.3 (set SSL_CERTFILE / SSL_KEYFILE)

# Frontend (from frontend/)
npm install
npm run dev              # http://localhost:5173
```

Seeded accounts:

| Role | Email | Password |
| --- | --- | --- |
| Reviewer | `reviewer@kyc.ai` | `review123` |
| Admin | `admin@kyc.ai` | `admin123` |
| Applicant | `applicant@kyc.ai` | `applicant123` |

Flow: **Landing → Onboard (user details) → Upload (4 docs + liveness) → Processing → Results**;
reviewers sign in via **Staff Login** and are routed to the Reviewer Panel.

## Testing

```bash
cd backend
set PYTEST=1
venv\Scripts\python -m pytest -s
```

The suite covers the full pipeline (with AI models stubbed for speed), document verification
classifiers, PDF handling/validation, liveness blink logic, RBAC and encryption. The
per-application pipeline lock is stress-tested under repeated concurrent triggers
(`backend/tests/test_pipeline_lock_stress.py`).

```bash
cd frontend
npm run build
```

## API reference

Base path: `/api/v1`. `Auth` legend:

- `—` public.
- `reviewer/admin` — staff JWT with that role (`Authorization: Bearer <token>`).
- `owner/staff` — either the applicant's **application token** (returned by
  `POST /applications/`, bound to that application) or a reviewer/admin JWT. Every
  document route is tied to its owning `application_id`; a token for one
  application cannot read or mutate another's documents.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/auth/login` | — | Obtain a JWT (`email`, `password`); rate-limited |
| POST | `/applications/` | — | Create a KYC application; returns an **application token** |
| GET | `/applications/` | reviewer/admin | List applications (`status_filter`) |
| GET | `/applications/{id}` | — | Get an application |
| GET | `/applications/{id}/status` | — | Poll status |
| POST | `/applications/{id}/override` | reviewer/admin | Override the decision |
| POST | `/documents/{id}/upload` | owner/staff | Upload a document (image/PDF) |
| POST | `/documents/{id}/upload/liveness` | owner/staff | Upload liveness frames (images) |
| GET | `/documents/{id}/view` | owner/staff | Download a stored document |
| PATCH | `/documents/{id}` | owner/staff | Reclassify a document's slot |
| GET | `/documents/application/{id}/list` | owner/staff | List an application's documents |
| POST | `/verification/{id}/precheck` | — | Classify uploads & suggest routing |
| POST | `/verification/{id}/process` | — | Run the KYC pipeline |
| GET | `/verification/{id}/progress` | — | Current stage / status / elapsed |
| GET | `/verification/{id}/results` | — | Extracted data, risk, SHAP, mismatches |
| GET | `/audit/{id}/trail` | — | Immutable audit trail |

Interactive docs: `http://localhost:8000/docs`.

## Project layout

```
backend/
  app/
    api/v1/          applications, documents, verification, audit, auth
    core/            pipeline orchestration, security
    models/          SQLAlchemy models (users, applications, documents, ...)
    schemas/         Pydantic request/response schemas
    services/        ocr, face, liveness, entity, risk, shap, pdf,
                     document_verification, encryption, audit, verhoeff
  alembic/versions/  database migrations
  tests/             pytest suite + image fixtures
  scripts/           seed_users
  run.py             uvicorn launcher (optional TLS 1.3)
frontend/
  src/components/    Landing, Login, Onboard, UploadDocs, CameraCapture,
                     Processing, Results, ReviewerPanel
  src/services/      axios API client
  src/utils/         client-side image quality checks
documents/           SRS.md, PROBLEM_STATEMENT.md, image.png
```

## Troubleshooting

- **OCR slow** — ensure `OCR_USE_GPU=true` and CUDA torch is installed; the first call
  initializes the GPU (a few seconds), subsequent pages are fast.
- **Tesseract not found** — install it and/or set `TESSERACT_CMD`; the pipeline logs when the
  fallback is unavailable.
- **`CREATE EXTENSION vector` fails** — install pgvector for your PostgreSQL version (see
  [Setup](#2-postgresql--pgvector)).
- **Database auth errors** — update `DATABASE_URL`/`DATABASE_URL_SYNC` in `backend/.env`.
- **Reset data** — truncate the transactional tables and reseed:
  ```sql
  TRUNCATE TABLE audit_logs, risk_scores, explainability, embeddings,
                  documents, kyc_applications RESTART IDENTITY CASCADE;
  DELETE FROM users WHERE email NOT IN ('applicant@kyc.ai','reviewer@kyc.ai','admin@kyc.ai');
  ```
  then `python -m scripts.seed_users`.
- **PII / secrets** — never commit `.env*`; `.gitignore` already excludes them.

See `backend/README.md` for backend-specific notes and `documents/SRS.md` for the full
requirements specification.
