# Backend Architecture Analysis

This document provides a comprehensive analysis of the current state of the backend in the `Credlayer` project.

## High-Level Summary

Currently, the backend acts as a **foundational skeleton** rather than a fully implemented service. It is structured as an asynchronous Python application using **FastAPI** for HTTP routing, **SQLAlchemy** (with `asyncpg`) for database interaction, and **Redis** for caching.

Based solely on the provided code, there is no domain-specific business logic implemented. The application successfully initializes infrastructure connections (database and Redis), configures CORS, sets up structural exception handlers, and exposes infrastructure probes (health checks). It is primed for further development but does not yet handle any specific webhook ingestion or data scoring.

---

## Technical Breakdown

### 1. FastAPI Application & Endpoint Routing
The FastAPI application is created via an application factory pattern (`create_app` in `src/credlayer/main.py`).
- **Lifespan Management**: Connects and gracefully disconnects from PostgreSQL and Redis on startup and shutdown using FastAPI's asynchronous `@asynccontextmanager` lifespan event.
- **Routing**:
  - **Infrastructure Probes**: Unenveloped health checks (`/healthz` and `/readyz`) are provided by `src/credlayer/api/health.py`. The `/readyz` endpoint actively pings both the database and Redis to ensure readiness.
  - **API Routing**: A core `api_router` is included under the `/api/v1` prefix (configurable via `.env`). However, according to `src/credlayer/api/router.py`, there are no domain-specific routes registered yet (e.g., auth, users, wallets).

### 2. Database Configuration & ORM Models
The backend is designed for an asynchronous PostgreSQL database.
- **Configuration & Sessions**: `src/credlayer/db/session.py` handles the creation of the database engine (`create_async_engine`) and manages connection pooling. It provides an asynchronous session factory (`async_sessionmaker`) yielding `AsyncSession` instances.
- **ORM Models**: The project uses SQLAlchemy 2.0. `src/credlayer/db/base.py` establishes the foundational `Base` declarative class (`DeclarativeBase`). It includes a strict naming convention dictionary to guarantee predictability when generating and applying `Alembic` migrations for constraints (indexes, unique constraints, foreign keys).
- **Current Models**: As of now, there are no domain-specific models defined in the codebase.

### 3. Helius Webhook Ingestion Logic
**Status: Not Implemented.**
There are no routes, services, or models in the codebase related to webhook ingestion, payload validation, or Helius integration.

### 4. Scoring Pipeline / Data Processing Scripts
**Status: Not Implemented.**
The backend lacks any data processing scripts, background task queues (e.g., Celery/ARQ), or scoring algorithms. The `core/` directory contains configuration and logging setup, but no data orchestration logic.

---

## Infrastructure & Configuration

- **Dependency Management**: Standardized using `pyproject.toml` (with Hatchling as the build backend) and `uv` (`uv.lock`).
- **Configuration**: Managed using `pydantic-settings` (`src/credlayer/core/config.py`). It defines environment variables for the database URL, Redis URL, CORS origins, and the JWT auth settings (`JWT_SECRET`, `JWT_EXPIRE_MINUTES`, `ADMIN_EMAILS`).
- **Logging**: Configured via `structlog` (`src/credlayer/core/logging.py`) for structured JSON logging, as seen in the `/readyz` health check when dependencies fail to connect.
