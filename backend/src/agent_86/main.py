import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.applications import FastAPI as FastAPIType
from fastapi.middleware.cors import CORSMiddleware

from agent_86.api.router import router
from agent_86.core.config import get_settings
from agent_86.core.errors import ConfigurationError
from agent_86.core.logging import configure_logging, get_logger
from agent_86.core.observability import interaction_id_from_headers
from agent_86.core.runtime_config import AppConfigurationRefresher, RuntimeConfiguration
from agent_86.core.telemetry import configure_telemetry


logger = get_logger(__name__)


def create_app() -> FastAPI:
    try:
        settings = get_settings()
    except ConfigurationError as exc:
        raise SystemExit(str(exc)) from None

    configure_logging(settings)
    telemetry_enabled = configure_telemetry(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        refresher = AppConfigurationRefresher(app.state.runtime_configuration)
        stop_event = asyncio.Event()
        refresh_task = asyncio.create_task(refresher.refresh_loop(stop_event))
        try:
            yield
        finally:
            stop_event.set()
            await refresh_task

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.runtime_configuration = RuntimeConfiguration(settings)
    if settings.cors_allowed_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(router)
    if telemetry_enabled:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)

    @app.middleware("http")
    async def add_observability_context(request: Request, call_next):
        interaction_id = interaction_id_from_headers(request.headers)
        if interaction_id:
            request.state.interaction_id = interaction_id
            from opentelemetry import trace

            trace.get_current_span().set_attribute("agent86.interaction_id", interaction_id)
        from opentelemetry import trace

        trace.get_current_span().set_attribute("http.route_hint", request.url.path)
        response = await call_next(request)
        if interaction_id:
            response.headers["x-agent86-interaction-id"] = interaction_id
        return response
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