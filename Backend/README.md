# CredLayer Backend

Core FastAPI backend for CredLayer: manages database models, caching, chain indexing, developer platform APIs, and acts as the API Gateway for the standalone ML scoring microservice (`models/`).

See `docs/backend-ai-specification.md` at the repo root for the full specification.

---

## 1. Quick Start

### Install Dependencies
Requires [uv](https://docs.astral.sh/uv/):
```bash
cd Backend
uv sync
```

### Database Setup

#### Option A: Railway PostgreSQL (production)

Set `DATABASE_URL` to the value Railway provides (reference it from the API service as `${{Postgres.DATABASE_URL}}`). `postgresql://` URLs are converted to the asyncpg driver automatically. Migrations create the whole schema on a fresh database:

```bash
uv run alembic upgrade head
```

#### Option B: Local PostgreSQL with Docker
```bash
docker compose up postgres redis -d
```
Then use the default `.env.example` configuration.

### Run the Backend Gateway (Port 8000)
```bash
uv run uvicorn credlayer.main:app --port 8000 --reload
```

---

## 2. Microservice Integration (`models/` Service)

The Backend acts as an API gateway for the standalone ML service (`models/`).

Configure `ML_SERVICE_URL` to the deployed ML service URL in production. For local development only, set it to `http://127.0.0.1:8001`.
```env
ML_SERVICE_URL=https://<deployed-ml-service-host>
```

*Make sure the `models/` service is running in a separate terminal:*
```bash
cd ../models
uv run uvicorn credlayer_ml.main:app --port 8001 --reload
```

---

## 3. Testing the Backend API Endpoints

### Liveness & Readiness Probes
```bash
# Liveness (no external dependencies)
curl -s http://localhost:8000/healthz | python3 -m json.tool

# Readiness (pings Postgres and optionally Redis)
curl -s http://localhost:8000/readyz | python3 -m json.tool
```

Expected response:
```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "redis": "not_configured"
  }
}
```

### Single Wallet Reputation Score (GET)
Queries the GNN model through the gateway:
```bash
curl -s http://localhost:8000/api/v1/scores/FfetZ9oHhYmHQq7n7K37UQAMCu3pf4Bx5TKyKQpTSQYs | python3 -m json.tool
```

**Example Response:**
```json
{
    "success": true,
    "data": {
        "address": "FfetZ9oHhYmHQq7n7K37UQAMCu3pf4Bx5TKyKQpTSQYs",
        "trustScore": 468,
        "trustLevel": "low",
        "riskLevel": "medium",
        "confidence": 0.9,
        "fraudProbability": 0.5311985015869141,
        "network": "solana",
        "explanation": "The prediction for node 44059 was most influenced by: Features [feature_0 (0.0000), feature_1 (0.0000), feature_2 (0.0000), feature_3 (0.0000), feature_4 (0.0000)], Neighbor Connections [None]"
    },
    "message": null,
    "timestamp": "2026-08-26T10:53:27.761457Z"
}
```

### Batch Wallet Reputation Scoring (POST)
```bash
curl -s -X POST http://localhost:8000/api/v1/scores/batch \
  -H "Content-Type: application/json" \
  -d '{
    "addresses": [
      "FfetZ9oHhYmHQq7n7K37UQAMCu3pf4Bx5TKyKQpTSQYs",
      "G61NTJEvxUuTPsNuW9AKKDX2yQWnVgaZWs4YQ9xMcpPx",
      "DKXrKtQFUNAr5Rcq19CMFzYgqynJ3uJ78bux4fsPty5P"
    ]
  }' | python3 -m json.tool
```

---

## 4. Interactive Swagger UI

Open your browser to:
[http://localhost:8000/docs](http://localhost:8000/docs)

---

## 5. Local Infrastructure (Postgres & Redis)

Start local Postgres and Redis containers:
```bash
docker compose up postgres redis
```

**Note:** Redis is optional. The backend will start without it and report `"redis": "not_configured"` in health checks.

---

## 6. Database Migrations

### View Current Status
```bash
# Check migration version
uv run alembic current

# View migration history
uv run alembic history

# Verify schema matches migrations
python scripts/check_migrations.py
```

### Create New Migrations
```bash
# Auto-generate migration from model changes
uv run alembic revision --autogenerate -m "add_new_table"

# Review generated file in migrations/versions/
# Edit if needed, then apply:
uv run alembic upgrade head
```

### Apply Migrations
```bash
# Upgrade to latest
uv run alembic upgrade head

# Upgrade one version
uv run alembic upgrade +1

# Downgrade one version
uv run alembic downgrade -1
```

### Troubleshooting Migrations

If you see "column does not exist" errors:

1. **Check schema:**
   ```bash
   python scripts/check_migrations.py
   ```

2. **Check the applied revision:** `uv run alembic current`

3. **Reset if needed (destroys data):**
   ```bash
   # Local only
   ./scripts/reset_and_migrate.sh

   ```

---

## 7. Railway Deployment

### Quick Deploy

1. **Connect GitHub repo** to Railway
2. **Set environment variables:**
   ```env
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   JWT_SECRET=<openssl rand -hex 32>
   ADMIN_EMAILS=you@example.com
   ENVIRONMENT=production
   CORS_ORIGINS=["https://your-frontend.vercel.app"]
   ```
3. **Deploy** - migrations run automatically via Dockerfile

### Deployment Troubleshooting

See detailed guides:
- `RAILWAY_SETUP.md` - Complete Railway deployment guide
- `QUICK_FIX.md` - Common error solutions

---

## 8. Project Structure

```
Backend/
├── src/credlayer/
│   ├── api/
│   │   ├── v1/          # API endpoints (models defined inline)
│   │   │   ├── activity.py
│   │   │   ├── agents.py
│   │   │   ├── api_keys.py
│   │   │   ├── connections.py
│   │   │   ├── credentials.py
│   │   │   ├── request_logs.py
│   │   │   ├── scores.py
│   │   │   ├── settings.py
│   │   │   └── webhooks.py
│   │   ├── deps.py      # FastAPI dependencies
│   │   ├── envelope.py  # Response wrapper
│   │   ├── errors.py    # Error handling
│   │   ├── health.py    # Health check endpoints
│   │   └── router.py    # Main API router
│   ├── cache/
│   │   └── redis.py     # Redis client (optional)
│   ├── core/
│   │   ├── config.py    # Settings & environment
│   │   ├── errors.py    # Core exceptions
│   │   └── logging.py   # Structured logging
│   ├── db/
│   │   ├── base.py      # SQLAlchemy base
│   │   └── session.py   # Database session management
│   ├── schemas/
│   │   └── common.py    # Shared Pydantic models
│   └── main.py          # FastAPI application entry
├── migrations/          # Alembic migrations
│   └── versions/
│       ├── 001_create_credentials_table.py
│       ├── 002_create_connections_table.py
│       ├── 003_create_agents_tables.py
│       ├── 004_create_activity_table.py
│       ├── 005_create_settings_table.py
│       ├── 006_create_api_keys_table.py
│       └── 007_create_webhooks_request_logs_tables.py
├── scripts/             # Utility scripts
│   ├── check_migrations.py      # Verify schema
│   ├── safe_migrate.py          # Smart migration helper
│   ├── verify_schema.sql        # Manual SQL check
│   └── railway_reset_db.sql     # Database reset for Railway
├── tests/               # Test suite
├── .env.example         # Environment template
├── alembic.ini          # Alembic configuration
├── docker-compose.yml   # Local services
├── Dockerfile           # Production container
├── pyproject.toml       # Python dependencies
└── README.md            # This file
```

---

## 9. Database Schema

All tables from migrations 001-007:

| Table | Description |
|-------|-------------|
| `credentials` | Wallet attestations and credentials |
| `connections` | Trust graph connections |
| `agents` | AI agents |
| `agent_executions` | Agent execution history |
| `activity` | Event audit log |
| `settings` | User preferences |
| `api_keys` | Developer API keys |
| `webhooks` | Webhook subscriptions |
| `request_logs` | API request logs |
| `alembic_version` | Migration tracking |

---

## 10. Environment Variables

### Required
```env
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
ENVIRONMENT=development|production
```

### Optional
```env
# Redis (optional - app works without it)
REDIS_URL=redis://localhost:6379/0

# ML Service
# Local development only; production must use the deployed ML service URL.
ML_SERVICE_URL=https://<deployed-ml-service-host>

# API Configuration
API_V1_PREFIX=/api/v1
LOG_LEVEL=INFO
CORS_ORIGINS=["http://localhost:3000"]

# Auth
JWT_SECRET=<openssl rand -hex 32>
JWT_EXPIRE_MINUTES=1440
ADMIN_EMAILS=you@example.com
```

---

## 11. Tests

```bash
uv run pytest
# or
PYTHONPATH=src python3 -m unittest discover -s tests -p "test_*.py"
```

---

## 12. Helpful Resources

- **Deployment:** `RAILWAY_SETUP.md`
- **Quick Fixes:** `QUICK_FIX.md`
- **Scripts:** `scripts/README.md`
- **API Spec:** `docs/backend-ai-specification.md`

---

## 13. Common Issues

### "Column does not exist" errors
Schema mismatch. Run `alembic upgrade head` or `scripts/check_migrations.py`.

### Database connection errors on Railway
Check `DATABASE_URL` references the Railway Postgres service (private network host).

### Redis connection errors
Redis is optional. Set `REDIS_URL` or leave empty - app will work without it.

### Prepared statement errors
Use direct connection, not transaction pooler. Or add `?prepared_statement_cache_size=0` to DATABASE_URL.

---

**Need Help?** Check the documentation files in `Backend/` or run diagnostic scripts in `Backend/scripts/`.

---

## 14. Authentication

Email + password auth lives in `src/credlayer/api/v1/auth.py` (Argon2 hashing, HS256 JWT bearer tokens, `users` table from migration 008).

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/auth/register` | Create account, returns token |
| `POST /api/v1/auth/login` | Email + password, returns token |
| `POST /api/v1/auth/logout` | Revokes all of the user's tokens |
| `GET /api/v1/auth/me` | Current user (protected) |
| `POST /api/v1/auth/forgot-password`, `/reset-password` | Password reset |
| `GET /api/v1/auth/admin/users` | Admin-only example |

Protect a route with `Depends(get_current_user)` or `Depends(require_roles("admin"))`.
