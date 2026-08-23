import logging
import sys

try:
    import structlog
except ImportError:  # pragma: no cover - fallback for environments without optional dependency
    structlog = None

from agent_86.core.config import Settings


def configure_logging(settings: Settings) -> None:
    configure_log_level(settings.log_level)
    if structlog is None:
        logging.basicConfig(
            level=_coerce_log_level(settings.log_level),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            stream=sys.stdout,
            force=True,
        )
        return

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer()
    )

    logging.basicConfig(
        level=_coerce_log_level(settings.log_level),
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)


def configure_log_level(value: str) -> None:
    """Apply a runtime log level without replacing stdout's JSON handlers."""
    level = _coerce_log_level(value)
    logging.getLogger().setLevel(level)
    logging.getLogger("agent_86").setLevel(level)


def get_logger(name: str):
    if structlog is None:
        return logging.getLogger(name)
    return structlog.get_logger(name)


def _coerce_log_level(value: str) -> int:
    normalized = value.upper().strip()
    return getattr(logging, normalized, logging.INFO)