from fastapi import APIRouter

from agent_86.api.routes.azure_bicep_conversion import router as azure_bicep_conversion_router
from agent_86.api.routes.artifacts import router as artifacts_router
from agent_86.api.routes.chat import router as chat_router
from agent_86.api.routes.health import router as health_router
from agent_86.api.routes.messages import router as messages_router
from agent_86.api.routes.runtime_config import router as runtime_config_router
from agent_86.api.routes.sessions import router as sessions_router
from agent_86.api.routes.session_summaries import router as session_summaries_router

router = APIRouter()
router.include_router(health_router)
router.include_router(runtime_config_router)
router.include_router(sessions_router)
router.include_router(messages_router)
router.include_router(artifacts_router)
router.include_router(chat_router)
router.include_router(session_summaries_router)
router.include_router(azure_bicep_conversion_router)