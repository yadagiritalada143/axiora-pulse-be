# Axiora Pulse — Backend API

> **Core AI Orchestration Engine** — Converts founder ideas into structured validation journeys using MCP, Skills, and Agentic Workflows.

Built with **FastAPI** · **PostgreSQL** · **SQLAlchemy (async)** · **Alembic** · **Multi-provider LLM support**

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Running the Server](#running-the-server)
- [Database Migrations](#database-migrations)
- [API Reference](#api-reference)
  - [Auth](#auth-endpoints)
  - [Workspaces](#workspace-endpoints)
  - [Surveys](#survey-endpoints)
  - [Questionnaire](#questionnaire-endpoints)
  - [Interactive Questionnaire Admin](#interactive-questionnaire-admin-endpoints)
  - [Admin](#admin-endpoints)
  - [Profile](#profile-endpoints)
  - [Orchestration](#orchestration-endpoints)
  - [Health & Root](#health--root)
- [LLM Providers](#llm-providers)
- [Skills System](#skills-system)
- [Testing & Quality](#testing--quality)
- [Rate Limiting](#rate-limiting)
- [Security](#security)

---

## Overview

Axiora Pulse is an AI-powered platform that helps founders validate business ideas through structured mentor conversations, market research, and automated agent workflows. This repository contains the FastAPI backend that powers:

- **AI Mentor Chat** — Guided idea-validation conversations inside workspaces
- **Agentic Orchestration** — Multi-agent idea validation and market research pipelines
- **Interactive Questionnaire** — Admin-managed questionnaire templates and user answer submission
- **JWT Authentication** — Secure register/login with OTP-based MFA, plus branded transactional emails (welcome, password-reset confirmation) sent asynchronously via a background job dispatcher
- **Workspace Management** — Persistent workspaces scoped to each user, including soft-delete/restore and file/image/PDF/doc/link attachments (stored in S3)
- **Surveys** — Create, publish, and collect public responses to workspace-scoped surveys, with CSV export
- **Admin** — Restricted endpoints for user listing and questionnaire management (`role=admin`)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI ≥ 0.115 |
| ASGI Server | Uvicorn |
| Database | PostgreSQL (via asyncpg) |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Auth | python-jose JWT (HS256) |
| LLM Providers | OpenAI, Anthropic, HuggingFace, Azure OpenAI |
| Rate Limiting | SlowAPI |
| Validation | Pydantic v2 |
| Email | SMTP (OTP dispatch + branded transactional emails via a background job dispatcher) |
| Storage | AWS S3 (`boto3`) — workspace attachments and generated report assets |
| File Processing | `pdfplumber`, `PyMuPDF`, `python-docx`, `beautifulsoup4` (attachment parsing); `reportlab` (PDF report generation) |

---

## Project Structure

```
backend/
├── main.py                     # FastAPI app entry point, middleware, routers
├── alembic/
│   └── versions/               # Database migration scripts
├── deploy/
│   ├── README.md               # Dev environment runbook
│   ├── docker-compose.yml      # Local/dev container wiring
│   ├── Caddyfile               # Caddy reverse proxy configuration
│   └── setup.sh                # Box bootstrap script
├── tests/
│   ├── conftest.py             # Async DB/client fixtures and overrides
│   ├── test_auth.py            # Auth, OTP, reset, and dependency coverage
│   ├── test_admin.py           # Admin route coverage
│   ├── test_profile.py         # /api/auth/me, /api/users/me coverage
│   ├── test_email_templates.py # Transactional email template rendering
│   ├── test_background_jobs.py # Email job dispatcher (retry/backoff) coverage
│   ├── test_surveys.py         # Survey CRUD, public submission, export
│   ├── test_questionnaire.py   # Questionnaire validation and admin routes
│   ├── test_workspaces.py      # Workspace CRUD and ownership coverage
│   ├── test_workspace_subresources.py # Chat, state, reset, report export
│   ├── test_workspace_attachments.py  # Attachment upload/list/delete
│   ├── test_attachment_processing.py  # PDF/DOCX/link/image parsing
│   ├── test_orchestration.py   # Agentic orchestration endpoint
│   ├── test_base_agent.py, test_idea_validation_agent.py,
│   │   test_market_research_agent.py, test_survey_intelligence_agent.py # Per-agent unit tests
│   └── test_database_constraints.py # Schema and integrity checks
├── test_admin_script.py        # Manual admin login smoke test
├── test_llm_connectivity.py, test_llm_streaming.py,
│   test_mcp_servers.py, test_full_pipeline_up_to_survey_agent.py,
│   test_survey_agent_validation.py   # Manual/dev smoke-test scripts (not part of the pytest suite)
├── alembic.ini                 # Alembic configuration
├── requirements.txt
└── app/
    ├── api/
    │   ├── profile.py          # Unversioned /api/auth/me, /api/users/me
    │   └── v1/
    │       ├── auth.py         # Auth endpoints (register, login, OTP, password, refresh, logout)
    │       ├── admin.py        # Admin-only endpoints (role=admin), e.g. user listing
    │       ├── workspace.py    # Workspace CRUD + AI Mentor sub-resources + attachments
    │       ├── surveys.py      # Survey CRUD, public submission, and export
    │       ├── questionnaire.py # Public questionnaire routes
    │       ├── interactive_questionnaire.py # Admin questionnaire routes
    │       ├── orchestration.py # Agentic orchestration endpoint
    │       ├── mentor.py       # Deprecated stub; workspace routes replaced these
    │       ├── analytics.py    # Reserved for Phase 2 (unmounted stub)
    │       ├── agents.py       # Reserved for Phase 2 (unmounted stub)
    │       └── reports.py      # Deprecated stub; workspace routes replaced these
    ├── core/
    │   ├── dependencies.py     # get_current_user JWT dependency
    │   ├── security.py         # Token creation, password hashing, OTP utils
    │   ├── limiter.py          # SlowAPI rate limiter setup
    │   ├── logging.py          # Structured logging configuration
    │   └── config.py           # Deprecated stub, kept for compatibility
    ├── db/
    │   ├── database.py         # Async DB engine, session factory, migration runner
    │   └── models.py           # SQLAlchemy ORM models (User, Workspace, questionnaire tables)
    ├── models/
    │   ├── auth_models.py      # Pydantic request/response models for auth
    │   ├── admin_models.py     # Admin request/response models
    │   ├── questionnaire_models.py # Questionnaire request/response models
    │   ├── workspace_models.py # Pydantic request/response models for workspaces
    │   ├── survey_models.py    # Survey request/response models
    │   ├── orchestration_models.py
    │   ├── agent_models.py
    │   └── skill_models.py
    ├── services/
    │   ├── auth_service.py     # Registration, OTP verification, login logic
    │   ├── admin_service.py    # Admin user-listing logic
    │   ├── questionnaire_service.py # Questionnaire CRUD and answer persistence
    │   ├── workspace_service.py # Workspace CRUD and mentor session logic
    │   ├── workspace_attachment_service.py # Attachment upload/list/delete orchestration
    │   ├── attachment_processor.py # PDF/DOCX/link/image content extraction
    │   ├── s3_storage_service.py # AWS S3 storage backend (falls back to local disk without AWS creds)
    │   ├── survey_service.py   # Survey CRUD, public link generation, response export
    │   ├── mentor_service.py   # AI Mentor conversation engine
    │   ├── report_service.py   # PDF/Doc report generation
    │   ├── email_service.py    # SMTP email delivery (OTP + transactional emails)
    │   ├── email_templates.py  # Shared HTML layout/components for transactional emails
    │   └── otp_dispatcher.py   # OTP routing (email / SMS)
    ├── templates/               # Static email assets (logo images)
    ├── agents/                 # AI agent implementations
    ├── orchestration/          # Multi-agent workflow orchestrator
    ├── skills/                 # Skill YAML definitions + registry
    ├── llm/                    # LLM provider abstraction layer
    ├── mcp/                    # Model Context Protocol integration (mcp_host.py, tool_registry.py, tools/)
    ├── guardrails/             # Input/output safety guards
    └── workers/
        └── background_jobs.py  # Fire-and-forget async email job dispatcher with retry/backoff
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- A virtual environment tool (`venv` or `conda`)

### Installation

```bash
# 1. Clone the repository
git clone <repo-url>
cd backend

# 2. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

```

---

## Environment Variables

Create a `.env` file in the `backend/` directory. **Never commit this file.**

Below is a reference of all supported variables with descriptions:

### Application

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `Axiora Pulse AI Engine` | Display name shown in logs and API docs |
| `APP_VERSION` | `1.0.0` | Application version |
| `DEBUG` | `true` | Enables Swagger UI (`/docs`), verbose logs, and permissive CORS. Set to `false` in production. |

### Database

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | Async PostgreSQL connection string. Format: `postgresql+asyncpg://user:password@host:port/dbname` |

### Security & JWT

| Variable | Required | Description |
|---|---|---|
| `JWT_SECRET_KEY` | ✅ | Secret key used to sign JWT tokens. **Must be changed in production.** |
| `JWT_ALGORITHM` | ✅ | JWT signing algorithm (e.g. `HS256`) — no code default, must be set or auth will fail to start |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ✅ | Access token lifetime in minutes — no code default, must be set |
| `OTP_EXPIRE_MINUTES` | `10` (email service only) | OTP lifetime in minutes. Displayed in OTP emails via a default of `10`; the security-layer OTP expiry calculation itself has no default and must be set. |

> Refresh-token lifetime is currently hardcoded to 7 days in `app/core/security.py` — there is no `REFRESH_TOKEN_EXPIRE_DAYS` environment variable read anywhere in the code.

### LLM Providers

| Variable | Required | Description |
|---|---|---|
| `DEFAULT_PROVIDER` | `huggingface` | Active LLM provider: `openai`, `anthropic`, `huggingface`, or `azure_openai` |
| `DEFAULT_MODEL` | `meta-llama/Llama-3.1-8B-Instruct` | Fallback model if no provider-specific model is set |
| `HF_TOKEN` | If using HuggingFace | HuggingFace API token |
| `HF_MODEL` | — | HuggingFace model ID (e.g. `meta-llama/Llama-3.1-8B-Instruct`) |
| `HF_BASE_URL` | — | HuggingFace router base URL |
| `HF_TIMEOUT` | `120` | HuggingFace request timeout in seconds |
| `HF_MAX_RETRIES` | `2` | HuggingFace retry count |
| `OPENAI_API_KEY` | If using OpenAI | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model to use |
| `OPENAI_BASE_URL` | — | Optional OpenAI-compatible base URL |
| `OPENAI_TIMEOUT` | `60` | OpenAI request timeout in seconds |
| `OPENAI_MAX_RETRIES` | `2` | OpenAI retry count |
| `ANTHROPIC_API_KEY` | If using Anthropic | Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-3-5-sonnet-20241022` | Anthropic model to use |
| `AZURE_OPENAI_API_KEY` | If using Azure | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | If using Azure | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_MODEL` | `gpt-4o` | Azure deployment name |

### Email (OTP Dispatch)

| Variable | Required | Description |
|---|---|---|
| `SMTP_HOST` | ✅ | SMTP server hostname |
| `SMTP_PORT` | ✅ | SMTP server port (usually `587` for TLS) |
| `SMTP_USER` | ✅ | SMTP login username (sender email) |
| `SMTP_PASSWORD` | ✅ | SMTP login password or app password |
| `SMTP_FROM_EMAIL` | — | Envelope sender address used in outgoing mail |
| `SMTP_FROM_NAME` | `Axiora Pulse` | Display name for outgoing emails |
| `SUPPORT_EMAIL` | `no.reply@axiorapulse.com` | Support contact address shown in transactional emails (e.g. "didn't request this?" notices) |
| `DASHBOARD_LOGIN_URL` | `https://qa.axiorapulse.com/login` | Frontend login/dashboard URL linked from the "Go to Dashboard" button in the welcome email |
| `EMAIL_LOGO_LIGHT_URL` | Cloudinary-hosted default | Hosted URL of the light-background Axiora Pulse logo used in transactional emails |
| `EMAIL_LOGO_DARK_URL` | Cloudinary-hosted default | Hosted URL of the dark-background Axiora Pulse logo, swapped in for dark-mode-aware email clients |
| `EMAIL_TIMEZONE` | `Asia/Kolkata` | IANA timezone used to render timestamps (e.g. password-changed time) shown in transactional emails |

### Storage (S3 — Workspace Attachments & Report Assets)

| Variable | Required | Description |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | If using S3 | AWS access key. Without AWS credentials configured, `s3_storage_service` falls back to writing files locally under `uploads/` (used automatically in local/dev/test environments). |
| `AWS_SECRET_ACCESS_KEY` | If using S3 | AWS secret key |
| `AWS_REGION` | `us-east-1` | AWS region for the attachments bucket |
| `AWS_S3_BUCKET_NAME` | `axiora-pulse-attachments` | Bucket used for workspace attachment uploads |
| `S3_ENDPOINT_URL` | — | Optional custom S3-compatible endpoint (e.g. MinIO, LocalStack) |
| `AWS_ASSETS_BUCKET_NAME` | `axiora-assets` | Bucket used for generated report assets |
| `AWS_ASSETS_REGION` | `ap-south-1` | Region for the assets bucket |

### PDF Report Rendering

| Variable | Required | Description |
|---|---|---|
| `AXIORA_REPORT_BANNER_FONT_REGULAR` | — | Path to the regular-weight font used in generated PDF report banners |
| `AXIORA_REPORT_BANNER_FONT_BOLD` | — | Path to the bold-weight font used in generated PDF report banners |
| `AXIORA_REPORT_BANNER_VENTURE_FONT_REGULAR` | — | Regular-weight font for the venture-report banner variant |
| `AXIORA_REPORT_BANNER_VENTURE_FONT_BOLD` | — | Bold-weight font for the venture-report banner variant |
| `AXIORA_REPORT_TEMPLATE_PATH` | — | Override path to the PDF report template |

> Font-path defaults in `app/services/report_service.py` assume a Windows font directory (`WINDIR`, i.e. `C:\Windows\Fonts`). On non-Windows deploy targets, set these explicitly.

### CORS

| Variable | Default | Description |
|---|---|---|
| `ALLOWED_ORIGINS` | `*` (in DEBUG) | Comma-separated list of allowed frontend origins. Example: `https://app.axiorapulse.com,https://staging.axiorapulse.com` |

---

## Running the Server

```bash
# Development (with hot reload)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```


| URL | Description |
|---|---|
| `http://localhost:8000/` | Root — lists available routes |
| `http://localhost:8000/docs` | Swagger UI (DEBUG mode only) |
| `http://localhost:8000/redoc` | ReDoc (DEBUG mode only) |
| `http://localhost:8000/health` | Health check |

---

## Database Migrations

Migrations run automatically on server startup via `alembic upgrade head`.

To manage migrations manually:

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration (after editing ORM models)
alembic revision --autogenerate -m "describe your change"

# Roll back one migration
alembic downgrade -1

# View current revision
alembic current
```

---

## API Reference

Most endpoints are prefixed with `/api/v1`. The exception is the Profile router (`app/api/profile.py`), which is mounted unversioned under `/api` to match the existing SPA contract — see [Profile Endpoints](#profile-endpoints). Authentication uses **JWT Bearer tokens**.

### Auth Endpoints

| Method | Route | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | ❌ | Create a new account. Sends a 6-digit OTP to the provided email. |
| `POST` | `/api/v1/auth/verifyOTP` | ❌ | Verify the registration OTP. Returns `access_token` + `refresh_token`. On success, also fires a welcome email in the background. |
| `POST` | `/api/v1/auth/resendOTP` | ❌ | Resend a new registration OTP (invalidates the previous one). |
| `POST` | `/api/v1/auth/login` | ❌ | Validate credentials and dispatch a login OTP. |
| `POST` | `/api/v1/auth/verify-login` | ❌ | Verify the login OTP. Returns `access_token` + `refresh_token`. |
| `POST` | `/api/v1/auth/admin/login` | ❌ | Admin-specific login (validates `role="admin"`). |
| `POST` | `/api/v1/auth/refresh` | ❌ | Rotate a valid refresh token for a new access/refresh token pair. |
| `POST` | `/api/v1/auth/logout` | ✅ | Revoke all active refresh sessions for the authenticated user. |
| `POST` | `/api/v1/auth/forgot-password/request` | ❌ | Request a password reset OTP. |
| `POST` | `/api/v1/auth/forgot-password/verify` | ❌ | Verify the reset OTP. Returns a short-lived `reset_token`. |
| `POST` | `/api/v1/auth/forgot-password/reset` | ❌ | Set a new password using the `reset_token`. On success, fires a password-changed confirmation email in the background. |
| `POST` | `/api/v1/auth/change-password` | ✅ | Change password for the authenticated user. Revokes all existing sessions and fires a password-changed confirmation email in the background. |

Registration and password-change confirmation emails are dispatched asynchronously via `app/workers/background_jobs.py` — delivery is retried on transient failure and never blocks or fails the API request. See `app/services/email_templates.py` / `email_service.py` for the templates.

#### Token Response Shape (register & login)
```json
{
  "status": "success",
  "message": "...",
  "access_token": "<JWT>",
  "refresh_token": "<JWT>",
  "token_type": "bearer",
  "expires_in_minutes": 60
}
```

---

### Workspace Endpoints

All workspace routes require a valid **JWT Bearer token**.

| Method | Route | Description |
|---|---|---|
| `POST` | `/api/v1/workspaces` | Create a new workspace (returns `201 Created`) |
| `GET` | `/api/v1/workspaces` | List all workspaces for the current user |
| `GET` | `/api/v1/workspaces/user/{user_id}` | List all workspaces for a given user |
| `GET` | `/api/v1/workspaces/{workspace_id}` | Get a single workspace by ID |
| `PUT` | `/api/v1/workspaces/{workspace_id}` | Update workspace `name` and/or `description` |
| `DELETE` | `/api/v1/workspaces/{workspace_id}` | Soft-delete a workspace (returns `204 No Content`) |
| `DELETE` | `/api/v1/workspaces/{workspace_id}/permanent` | Permanently (hard) delete a workspace |
| `PATCH` | `/api/v1/workspaces/{workspace_id}/restore` | Restore a soft-deleted workspace |
| `POST` | `/api/v1/workspaces/{workspace_id}/chat` | Send a message to the AI Mentor inside a workspace |
| `GET` | `/api/v1/workspaces/{workspace_id}/state` | Get full dialogue history and validation state |
| `POST` | `/api/v1/workspaces/{workspace_id}/reset` | Reset mentor conversation for a workspace |
| `PUT` | `/api/v1/workspaces/{workspace_id}/survey/questions` | Override the survey questions generated for a workspace |
| `GET` | `/api/v1/workspaces/{workspace_id}/reports/{agent_name}` | Download a PDF/Doc agent report |
| `POST` | `/api/v1/workspaces/{workspace_id}/reports/export` | Export an agent report via POST body |
| `POST` | `/api/v1/workspaces/{workspace_id}/attachments` | Upload a file/image/PDF/doc/link attachment (returns `201 Created`) |
| `GET` | `/api/v1/workspaces/{workspace_id}/attachments` | List attachments for a workspace |
| `GET` | `/api/v1/workspaces/{workspace_id}/attachments/{attachment_id}` | Get a single attachment |
| `DELETE` | `/api/v1/workspaces/{workspace_id}/attachments/{attachment_id}` | Delete an attachment |

These workspace sub-resources replace the deprecated `/api/v1/mentor/*` and `/api/v1/reports/*` routes. Attachments are stored via `app/services/s3_storage_service.py` (S3, falling back to local disk under `uploads/` when AWS credentials are not configured) and parsed via `app/services/attachment_processor.py`.

#### Create Workspace Request
```json
{
  "name": "My Startup Idea",          // Required, 1–100 characters
  "description": "Optional context"   // Optional
}
```

#### Workspace Response
```json
{
  "id": 1,
  "user_id": 42,
  "name": "My Startup Idea",
  "description": "Optional context",
  "state": "GATHERING_INFO",
  "created_at": "2026-07-27T06:00:00Z",
  "updated_at": "2026-07-27T06:00:00Z"
}
```

---

### Survey Endpoints

All routes except the two `public` routes require a valid **JWT Bearer token**.

| Method | Route | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/surveys` | ✅ | Create a survey |
| `GET` | `/api/v1/surveys` | ✅ | List surveys for the current user |
| `GET` | `/api/v1/surveys/workspace/{workspace_id}` | ✅ | List surveys for a workspace |
| `GET` | `/api/v1/surveys/{survey_id}` | ✅ | Get a single survey |
| `PUT` | `/api/v1/surveys/{survey_id}` | ✅ | Update a survey |
| `DELETE` | `/api/v1/surveys/{survey_id}` | ✅ | Delete a survey (returns `204 No Content`) |
| `GET` | `/api/v1/surveys/{survey_id}/export` | ✅ | Export survey responses (CSV) |
| `GET` | `/api/v1/surveys/{survey_id}/responses` | ✅ | List raw survey responses |
| `GET` | `/api/v1/surveys/public/{token}` | ❌ | Public survey view, for respondents |
| `POST` | `/api/v1/surveys/public/{token}/submit` | ❌ | Public survey submission (returns `201 Created`) |

Public survey links are built from `PUBLIC_APP_URL` (see [Environment Variables](#environment-variables)).

The two public routes are keyed by `Survey.public_token` — an opaque, randomly generated identifier (`uuid.uuid4().hex`, unique-indexed) — rather than the internal sequential `survey_id` used everywhere else in this table. This is deliberate: those two routes are unauthenticated by design (external respondents have no account), so keying them off a sequential integer would let anyone enumerate `/public/1`, `/public/2`, ... and view or submit responses to surveys never shared with them. The owner-facing routes above stay on the internal `id` since they're already protected by JWT auth + ownership checks.

---

### Questionnaire Endpoints

All questionnaire routes require a valid **JWT Bearer token**.

| Method | Route | Description |
|---|---|---|
| `GET` | `/api/v1/questionnaire/questions` | List active questionnaire questions in ID order |
| `POST` | `/api/v1/questionnaire/submit-answers` | Submit or update questionnaire answers for the current user |

#### Questionnaire behavior
- Required questions must be present in the submission payload.
- Choice questions only accept values that exist in the question's answer list.
- Single-choice questions accept only one selected answer.
- Submitted answer strings are trimmed and empty values are discarded.
- Existing answers are updated instead of duplicated for the same user/question pair.

---

### Interactive Questionnaire Admin Endpoints

All admin questionnaire routes require a valid **JWT Bearer token** with `role=admin`.

| Method | Route | Description |
|---|---|---|
| `POST` | `/api/v1/admin/questionnaire/create-question` | Create an interactive questionnaire question |
| `GET` | `/api/v1/admin/questionnaire/questions` | List all questionnaire questions |
| `POST` | `/api/v1/admin/questionnaire/submit-answers` | Submit questionnaire answers through the admin namespace |
| `DELETE` | `/api/v1/admin/questionnaire/delete-question/{question_id}` | Delete a questionnaire question |

#### Admin questionnaire behavior
- Choice-based questions require at least two answer options.
- Admin create/delete operations are restricted to users with `role="admin"`.
- The admin routes reuse the same validation and answer persistence rules as the public questionnaire routes.

---

### Admin Endpoints

Requires a valid **JWT Bearer token** with `role=admin`. Distinct from the [Interactive Questionnaire Admin](#interactive-questionnaire-admin-endpoints) router — both happen to share the `/api/v1/admin/*` prefix but live in separate files (`app/api/v1/admin.py` vs. `app/api/v1/interactive_questionnaire.py`).

| Method | Route | Description |
|---|---|---|
| `GET` | `/api/v1/admin/users` | List all registered users |

---

### Profile Endpoints

Mounted **unversioned** under `/api` (not `/api/v1`) to match the existing SPA contract. Requires a valid **JWT Bearer token**.

| Method | Route | Description |
|---|---|---|
| `GET` | `/api/auth/me` | Get the current authenticated user's profile |
| `PATCH` | `/api/users/me` | Update the current authenticated user's profile |

---

### Orchestration Endpoints

| Method | Route | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/orchestration/run` | ✅ | Run the full idea-validation agent pipeline for a workspace |

---

### Health & Root

| Method | Route | Description |
|---|---|---|
| `GET` | `/` | Root — welcome message and available routes |
| `GET` | `/health` | Server health, active LLM provider, and loaded skills |

---

## LLM Providers

The backend supports four LLM providers. Set `DEFAULT_PROVIDER` in your `.env` to switch:

| Provider | `DEFAULT_PROVIDER` value | Key Variable |
|---|---|---|
| HuggingFace Inference API | `huggingface` | `HF_TOKEN` |
| OpenAI | `openai` | `OPENAI_API_KEY` |
| Anthropic Claude | `anthropic` | `ANTHROPIC_API_KEY` |
| Azure OpenAI | `azure_openai` | `AZURE_OPENAI_MODEL` |

Azure OpenAI is currently a Phase 2+ stub in the codebase. The provider class exists, but the implementation raises `NotImplementedError`, so the usable providers today are HuggingFace, OpenAI, and Anthropic.

---

## Skills System

Skills are YAML-defined instruction sets loaded at startup into the skill registry. They provide the AI Mentor and agents with domain-specific capabilities.

| Skill File | Purpose |
|---|---|
| `ai_mentor_core_skill.md` | Core mentor conversation and idea extraction |
| `ai_idea_validation_mentor_skill.md` | Deep idea validation guidance |
| `idea_validation_skill.md` | Structured idea validation framework |
| `market_research_skill.md` | Market sizing and competitive analysis |
| `financial_readiness_skill.md` | Financial viability assessment |
| `gtm_strategy_skill.md` | Go-to-market strategy guidance |
| `survey_intelligence_skill.md` | Survey design and analysis |

Skills are loaded from `app/skills/` and registered automatically on startup.

---

## Testing & Quality

The repository includes an async test suite under `tests/` (17 files, 300+ tests):

- `tests/test_auth.py` covers registration, OTP verification, login, forgot-password, password changes, admin login, current-user dependency behavior, and transactional-email job dispatch.
- `tests/test_email_templates.py` covers transactional email template rendering (registration welcome, password-reset confirmation).
- `tests/test_background_jobs.py` covers the async email job dispatcher — success, retry/backoff, permanent failure, unknown job types.
- `tests/test_admin.py` covers admin-only user-listing routes.
- `tests/test_profile.py` covers the unversioned `/api/auth/me` and `/api/users/me` routes.
- `tests/test_workspaces.py` covers workspace CRUD and ownership enforcement.
- `tests/test_workspace_subresources.py` covers chat, state, reset, and report export/download.
- `tests/test_workspace_attachments.py` covers attachment upload, listing, and deletion.
- `tests/test_attachment_processing.py` covers PDF/DOCX/link/image content extraction.
- `tests/test_surveys.py` covers survey CRUD, public submission, and export.
- `tests/test_questionnaire.py` covers questionnaire validation, admin question management, and answer submission flows.
- `tests/test_orchestration.py` covers the agentic orchestration endpoint.
- `tests/test_base_agent.py`, `test_idea_validation_agent.py`, `test_market_research_agent.py`, `test_survey_intelligence_agent.py` cover individual agent implementations.
- `tests/test_database_constraints.py` covers schema constraints, foreign keys, indexes, and integrity failures.

Shared fixtures live in `tests/conftest.py` and provide:

- an async test database session
- an ASGI client wired to the FastAPI app
- automatic dependency overrides for database access

### Running Tests

```bash
# Run the full suite
pytest

# Run a single file
pytest tests/test_auth.py

# Run a single test
pytest tests/test_auth.py::test_register_success_persists_user_and_dispatches_otp

# Run with a coverage report printed to the terminal (missing-line numbers included)
pytest --cov=app --cov-report=term-missing

# Also generate a browsable HTML coverage report (writes to htmlcov/index.html)
pytest --cov=app --cov-report=term-missing --cov-report=html
```

By default, the suite runs against an in-memory SQLite database (`sqlite+aiosqlite:///:memory:`) — no `DATABASE_URL`/PostgreSQL setup is required to run tests. Set `TEST_DATABASE_URL` to point at a real PostgreSQL instance instead if you want to test against the production database engine.

`--cov=app` reads scope/omit rules from `.coveragerc` at the repo root (excludes deprecated stub routers, `__init__.py` files, and a few other modules from the reported percentage — see that file for the full list).

Notes:

- The suite uses `pytest`, `pytest-asyncio`, and `pytest-cov`.
- `test_admin_script.py`, `test_llm_connectivity.py`, `test_llm_streaming.py`, `test_mcp_servers.py`, `test_full_pipeline_up_to_survey_agent.py`, and `test_survey_agent_validation.py` are manual/dev smoke-test scripts at the repo root — they are not part of the `pytest` suite under `tests/` and are run directly (e.g. `python test_admin_script.py`).
- The codebase follows the standard FastAPI split: routers stay thin, services hold business logic, and Pydantic models define request and response contracts.

---

## Rate Limiting

Rate limiting is implemented with SlowAPI and applies per client IP. Exceeding a limit returns `HTTP 429 Too Many Requests`.

Current route limits:

| Route group | Limit |
|---|---|
| `POST /api/v1/auth/refresh` | 30 requests/minute |
| `POST /api/v1/auth/logout` | 30 requests/minute |
| `POST /api/v1/auth/register` | 5 requests/minute |
| `POST /api/v1/auth/verifyOTP` | 5 requests/minute |
| `POST /api/v1/auth/resendOTP` | 3 requests/minute |
| `POST /api/v1/auth/login` | 5 requests/minute |
| `POST /api/v1/auth/verify-login` | 5 requests/minute |
| `POST /api/v1/auth/admin/login` | 5 requests/minute |
| `POST /api/v1/auth/forgot-password/request` | 5 requests/minute |
| `POST /api/v1/auth/forgot-password/verify` | 5 requests/minute |
| `POST /api/v1/auth/forgot-password/reset` | 3 requests/minute |
| `POST /api/v1/auth/change-password` | 5 requests/minute |
| Workspace create / update / delete | 20 requests/minute |
| Workspace list / get / state | 60 requests/minute |
| Workspace chat / report download / report export | 30 requests/minute |

---

## Security

- **Passwords** are hashed using PBKDF2-HMAC-SHA256 (never stored in plain text)
- **OTP MFA** is required to complete both registration and login
- **JWT tokens** use HS256 signing with configurable expiry
- **Ownership enforcement** — all workspace operations verify `workspace.user_id == current_user.id` (403 Forbidden on mismatch)
- **JWT secret** — the server refuses to start in production mode if `JWT_SECRET_KEY` is set to the insecure default value
- **CORS** — permissive (`*`) in DEBUG mode only; restricted to `ALLOWED_ORIGINS` in production
