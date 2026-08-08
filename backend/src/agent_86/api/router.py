from fastapi import APIRouter

from backend.src.agent_86.api.routes.chat import router as chat_router
from backend.src.agent_86.api.routes.health import router as health_router
from backend.src.agent_86.api.routes.messages import router as messages_router
from backend.src.agent_86.api.routes.sessions import router as sessions_router

router = APIRouter()
router.include_router(health_router)
router.include_router(sessions_router)
router.include_router(messages_router)
router.include_router(chat_router)