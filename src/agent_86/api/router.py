from fastapi import APIRouter

from agent_86.api.routes.health import router as health_router
from agent_86.api.routes.sessions import router as sessions_router


router = APIRouter()
router.include_router(health_router)
router.include_router(sessions_router)