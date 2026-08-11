from fastapi import FastAPI
from fastapi.applications import FastAPI as FastAPIType
from fastapi.middleware.cors import CORSMiddleware

from agent_86.api.router import router
from agent_86.core.config import get_settings
from agent_86.core.errors import ConfigurationError
from agent_86.core.logging import configure_logging, get_logger
from agent_86.core.telemetry import configure_telemetry


logger = get_logger(__name__)


def create_app() -> FastAPI:
    try:
        settings = get_settings()
    except ConfigurationError as exc:
        raise SystemExit(str(exc)) from None

    configure_logging(settings)
    configure_telemetry(settings)

    app = FastAPI(title=settings.app_name)
    if settings.cors_allowed_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(router)
    logger.info("app_created", app_name=settings.app_name, app_env=settings.app_env)
    return app


class _LazyApp:
    def __init__(self) -> None:
        self._app: FastAPIType | None = None

    def _get_app(self) -> FastAPIType:
        if self._app is None:
            self._app = create_app()
        return self._app

    def __getattr__(self, name: str):
        return getattr(self._get_app(), name)

    async def __call__(self, scope, receive, send) -> None:
        await self._get_app()(scope, receive, send)


app = _LazyApp()