from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from credlayer.api.errors import register_exception_handlers
from credlayer.api.health import router as health_router
from credlayer.api.router import api_router
from credlayer.api.v1.api_keys import ApiKeyDB
from credlayer.api.v1.request_logs import RequestLogDB
from credlayer.cache.redis import dispose_redis, init_redis
from credlayer.core.config import get_settings
from credlayer.core.logging import configure_logging
from credlayer.db.session import dispose_engine, init_engine, session_scope

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Validate presented API keys and persist attributable business requests."""

    _excluded_paths = {"/healthz", "/readyz", "/docs", "/openapi.json", "/redoc"}

    def _is_excluded(self, request: Request) -> bool:
        path = request.url.path.rstrip("/") or "/"
        return path in self._excluded_paths or path.startswith(("/static/", "/assets/"))

    @staticmethod
    def _presented_key(request: Request) -> str | None:
        value = request.headers.get("x-api-key") or request.headers.get("api-key")
        if value:
            return value.strip()
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            return authorization[7:].strip()
        return None

    async def _find_api_key(self, request: Request) -> ApiKeyDB | None:
        presented = self._presented_key(request)
        if not presented:
            return None
        key_hash = hashlib.sha256(presented.encode("utf-8")).hexdigest()
        try:
            async with session_scope() as db:
                result = await db.execute(select(ApiKeyDB).where(ApiKeyDB.key_hash == key_hash))
                return result.scalar_one_or_none()
        except Exception as exc:
            logger.warning("api_key_lookup_failed", error=repr(exc))
            return None

    @staticmethod
    def _owner_from_path(request: Request) -> str | None:
        for name in ("wallet", "wallet_address", "owner_wallet", "address"):
            value = request.path_params.get(name)
            if value:
                return str(value)
        return None

    async def _resolve_owner(
        self, request: Request, api_key: ApiKeyDB | None
    ) -> tuple[str | None, object | None]:
        owner = request.query_params.get("owner_wallet")
        if owner:
            return owner, api_key.id if api_key else None
        if api_key:
            return api_key.owner_wallet, api_key.id
        return self._owner_from_path(request), None

    async def _write_log(self, values: dict) -> None:
        try:
            async with session_scope() as db:
                db.add(RequestLogDB(**values))
                await db.commit()
        except Exception as exc:
            logger.warning("request_log_write_failed", error=repr(exc))

    @staticmethod
    def _unauthorized(message: str) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": message,
                    "status_code": 401,
                },
            },
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        if self._is_excluded(request):
            return await call_next(request)

        started = time.perf_counter()
        response: Response | None = None
        exception: Exception | None = None
        api_key = await self._find_api_key(request) if self._presented_key(request) else None

        try:
            presented = self._presented_key(request)
            if presented and api_key is None:
                response = self._unauthorized("Invalid API key")
            elif presented and not api_key.is_active:
                response = self._unauthorized("API key has been revoked")
            elif presented and api_key.expires_at and api_key.expires_at <= datetime.now(UTC):
                response = self._unauthorized("API key has expired")
            else:
                response = await call_next(request)
            return response
        except Exception as exc:
            exception = exc
            raise
        finally:
            try:
                api_v1_prefix = get_settings().api_v1_prefix.rstrip("/")
                portal_prefixes = (
                    f"{api_v1_prefix}/developer",
                    f"{api_v1_prefix}/request-logs",
                    f"{api_v1_prefix}/api-keys",
                )
                is_portal_request = request.url.path.startswith(portal_prefixes)
                # Only log presented API-key traffic; portal polling is not business usage.
                if self._presented_key(request) is not None and not is_portal_request:
                    owner_wallet, api_key_id = await self._resolve_owner(request, api_key)
                    if owner_wallet:
                        status_code = response.status_code if response is not None else 500
                        asyncio.create_task(
                            self._write_log(
                                {
                                    "api_key_id": api_key_id,
                                    "owner_wallet": owner_wallet,
                                    "method": request.method,
                                    "endpoint": request.url.path,
                                    "status_code": status_code,
                                    "error_message": (
                                        repr(exception)
                                        if exception
                                        else (f"HTTP {status_code}" if status_code >= 500 else None)
                                    ),
                                    "duration_ms": max(
                                        0, round((time.perf_counter() - started) * 1000)
                                    ),
                                    "ip_address": (
                                        request.headers.get("x-forwarded-for", "")
                                        .split(",")[0]
                                        .strip()
                                        or (request.client.host if request.client else None)
                                    ),
                                }
                            )
                        )
            except Exception as exc:
                logger.warning("request_log_prepare_failed", error=repr(exc))


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        init_engine(settings)
        init_redis(settings)
        try:
            yield
        finally:
            await dispose_engine()
            await dispose_redis()

    app = FastAPI(title="CredLayer API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
