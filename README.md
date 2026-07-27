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
  - [Orchestration](#orchestration-endpoints)
  - [Health & Root](#health--root)
- [LLM Providers](#llm-providers)
- [Skills System](#skills-system)
- [Rate Limiting](#rate-limiting)
- [Security](#security)

---

## Overview

Axiora Pulse is an AI-powered platform that helps founders validate business ideas through structured mentor conversations, market research, and automated agent workflows. This repository contains the FastAPI backend that powers:

- **AI Mentor Chat** — Guided idea-validation conversations inside workspaces
- **Agentic Orchestration** — Multi-agent idea validation and market research pipelines
- **JWT Authentication** — Secure register/login with OTP-based MFA
- **Workspace Management** — Persistent workspaces scoped to each user

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
| Email | SMTP (OTP dispatch) |

---

## Project Structure

```
backend/
├── main.py                     # FastAPI app entry point, middleware, routers
├── alembic/                    # Database migration scripts
│   └── versions/
├── alembic.ini                 # Alembic configuration
├── requirements.txt
└── app/
    ├── api/
    │   └── v1/
    │       ├── auth.py         # Auth endpoints (register, login, OTP, password)
    │       ├── workspace.py    # Workspace CRUD + AI Mentor sub-resources
    │       └── orchestration.py# Agentic orchestration endpoints
    ├── core/
    │   ├── dependencies.py     # get_current_user JWT dependency
    │   ├── security.py         # Token creation, password hashing, OTP utils
    │   ├── limiter.py          # SlowAPI rate limiter setup
    │   └── logging.py          # Structured logging configuration
    ├── db/
    │   ├── database.py         # Async DB engine, session factory, migration runner
    │   └── models.py           # SQLAlchemy ORM models (User, Workspace)
    ├── models/
    │   ├── auth_models.py      # Pydantic request/response models for auth
    │   ├── workspace_models.py # Pydantic request/response models for workspaces
    │   └── orchestration_models.py
    ├── services/
    │   ├── auth_service.py     # Registration, OTP verification, login logic
    │   ├── workspace_service.py# Workspace CRUD and mentor session logic
    │   ├── mentor_service.py   # AI Mentor conversation engine
    │   ├── report_service.py   # PDF/Doc report generation
    │   ├── email_service.py    # SMTP email delivery
    │   └── otp_dispatcher.py   # OTP routing (email / SMS)
    ├── agents/                 # AI agent implementations
    ├── orchestration/          # Multi-agent workflow orchestrator
    ├── skills/                 # Skill YAML definitions + registry
    ├── llm/                    # LLM provider abstraction layer
    ├── mcp/                    # Model Context Protocol integration
    ├── guardrails/             # Input/output safety guards
    └── workers/                # Background task workers
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

# 4. Copy the environment template and fill in your values
copy .env.example .env       # Windows
# cp .env.example .env       # macOS / Linux
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
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime in minutes |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime in days |

### LLM Providers

| Variable | Required | Description |
|---|---|---|
| `DEFAULT_PROVIDER` | ✅ | Active LLM provider: `openai`, `anthropic`, `huggingface`, or `azure_openai` |
| `DEFAULT_MODEL` | — | Fallback model if no provider-specific model is set |
| `HF_TOKEN` | If using HuggingFace | HuggingFace API token |
| `HF_MODEL` | — | HuggingFace model ID (e.g. `meta-llama/Llama-3.1-8B-Instruct`) |
| `OPENAI_API_KEY` | If using OpenAI | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model to use |
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
| `EMAIL_FROM` | — | Display name for outgoing emails |

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

All endpoints are prefixed with `/api/v1`. Authentication uses **JWT Bearer tokens**.

### Auth Endpoints

| Method | Route | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | ❌ | Create a new account. Sends a 6-digit OTP to the provided email. |
| `POST` | `/api/v1/auth/verifyOTP` | ❌ | Verify the registration OTP. Returns `access_token` + `refresh_token`. |
| `POST` | `/api/v1/auth/resendOTP` | ❌ | Resend a new registration OTP (invalidates the previous one). |
| `POST` | `/api/v1/auth/login` | ❌ | Validate credentials and dispatch a login OTP. |
| `POST` | `/api/v1/auth/verify-login` | ❌ | Verify the login OTP. Returns `access_token` + `refresh_token`. |
| `POST` | `/api/v1/auth/forgot-password/request` | ❌ | Request a password reset OTP. |
| `POST` | `/api/v1/auth/forgot-password/verify` | ❌ | Verify the reset OTP. Returns a short-lived `reset_token`. |
| `POST` | `/api/v1/auth/forgot-password/reset` | ❌ | Set a new password using the `reset_token`. |
| `POST` | `/api/v1/auth/change-password` | ✅ | Change password for the authenticated user. Revokes all existing sessions. |

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
| `GET` | `/api/v1/workspaces/{workspace_id}` | Get a single workspace by ID |
| `PUT` | `/api/v1/workspaces/{workspace_id}` | Update workspace `name` and/or `description` |
| `DELETE` | `/api/v1/workspaces/{workspace_id}` | Delete a workspace (returns `204 No Content`) |
| `POST` | `/api/v1/workspaces/{workspace_id}/chat` | Send a message to the AI Mentor inside a workspace |
| `GET` | `/api/v1/workspaces/{workspace_id}/state` | Get full dialogue history and validation state |
| `POST` | `/api/v1/workspaces/{workspace_id}/reset` | Reset mentor conversation for a workspace |
| `GET` | `/api/v1/workspaces/{workspace_id}/reports/{agent_name}` | Download a PDF/Doc agent report |
| `POST` | `/api/v1/workspaces/{workspace_id}/reports/export` | Export an agent report via POST body |

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
| Azure OpenAI | `azure_openai` | `AZURE_OPENAI_API_KEY` |

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

## Rate Limiting

Endpoints are rate-limited using SlowAPI (backed by IP address):

| Endpoint Group | Limit |
|---|---|
| Register / Login / OTP routes | 3–5 requests/minute |
| Workspace create / delete / update | 20 requests/minute |
| Workspace list / get | 60 requests/minute |
| Workspace chat / reports | 30 requests/minute |

Exceeding a limit returns `HTTP 429 Too Many Requests`.

---

## Security

- **Passwords** are hashed using PBKDF2-HMAC-SHA256 (never stored in plain text)
- **OTP MFA** is required to complete both registration and login
- **JWT tokens** use HS256 signing with configurable expiry
- **Ownership enforcement** — all workspace operations verify `workspace.user_id == current_user.id` (403 Forbidden on mismatch)
- **JWT secret** — the server refuses to start in production mode if `JWT_SECRET_KEY` is set to the insecure default value
- **CORS** — permissive (`*`) in DEBUG mode only; restricted to `ALLOWED_ORIGINS` in production