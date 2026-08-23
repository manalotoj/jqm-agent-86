import re

from opentelemetry import metrics, trace

from agent_86.core.logging import get_logger


logger = get_logger(__name__)
_INTERACTION_ID_PATTERN = re.compile(r"^[a-f0-9-]{36}$", re.IGNORECASE)
_meter = metrics.get_meter("agent_86.workflows")
_workflow_counter = _meter.create_counter("agent86.workflow.operations")


def interaction_id_from_headers(headers) -> str | None:
    value = headers.get("x-agent86-interaction-id")
    return value if value and _INTERACTION_ID_PATTERN.fullmatch(value) else None


def add_workflow_event(name: str, *, interaction_id: str | None = None, **attributes: str | int | bool) -> None:
    safe_attributes = {key: value for key, value in attributes.items() if value is not None}
    if interaction_id:
        safe_attributes["agent86.interaction_id"] = interaction_id
    span = trace.get_current_span()
    span.add_event(name, safe_attributes)
    _workflow_counter.add(1, {"workflow.name": name, **safe_attributes})
    logger.info(name, **safe_attributes)