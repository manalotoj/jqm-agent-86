from fastapi import APIRouter, Request, Response

from agent_86.core.runtime_config import RuntimeConfiguration


router = APIRouter(tags=["runtime-config"])


@router.get("/runtime-config")
async def runtime_config(request: Request, response: Response) -> dict[str, str | bool | None]:
    configuration: RuntimeConfiguration = request.app.state.runtime_configuration
    response.headers["Cache-Control"] = "no-store"
    return configuration.browser_payload()