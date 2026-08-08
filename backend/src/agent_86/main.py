from fastapi import FastAPI

from backend.src.agent_86.api.router import router
from backend.src.agent_86.core.config import get_settings
from backend.src.agent_86.core.errors import ConfigurationError


def create_app() -> FastAPI:
    try:
        settings = get_settings()
    except ConfigurationError as exc:
        raise SystemExit(str(exc)) from None

    app = FastAPI(title=settings.app_name)
    app.include_router(router)
    return app


app = create_app()