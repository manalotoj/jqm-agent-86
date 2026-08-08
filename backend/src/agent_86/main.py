from fastapi import FastAPI
from fastapi.applications import FastAPI as FastAPIType

from agent_86.api.router import router
from agent_86.core.config import get_settings
from agent_86.core.errors import ConfigurationError


def create_app() -> FastAPI:
    try:
        settings = get_settings()
    except ConfigurationError as exc:
        raise SystemExit(str(exc)) from None

    app = FastAPI(title=settings.app_name)
    app.include_router(router)
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