from fastapi import APIRouter

from credlayer.api.v1.auth import router as auth_router
from credlayer.api.v1.scores import router as scores_router
from credlayer.api.v1.credentials import router as credentials_router
from credlayer.api.v1.connections import router as connections_router
from credlayer.api.v1.agents import router as agents_router
from credlayer.api.v1.activity import router as activity_router
from credlayer.api.v1.settings import router as settings_router
from credlayer.api.v1.api_keys import router as api_keys_router
from credlayer.api.v1.webhooks import router as webhooks_router
from credlayer.api.v1.request_logs import router as request_logs_router
from credlayer.api.v1.request_logs import stats_router as request_log_stats_router
from credlayer.api.debug import router as debug_router

# v1 endpoint modules register themselves here as they're built.
api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(scores_router)
api_router.include_router(credentials_router)
api_router.include_router(connections_router)
api_router.include_router(agents_router)
api_router.include_router(activity_router)
api_router.include_router(settings_router)
api_router.include_router(api_keys_router)
api_router.include_router(webhooks_router)
api_router.include_router(request_logs_router)
api_router.include_router(request_log_stats_router)
api_router.include_router(debug_router)  # Debug/diagnostic endpoints
