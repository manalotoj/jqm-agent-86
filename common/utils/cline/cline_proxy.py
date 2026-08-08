# proxy.py
from fastapi import FastAPI, Request, Response
import httpx

app = FastAPI()
TARGET = "https://foundry-jqm-westus-default.services.ai.azure.com/api/projects/proj-default/openai/v1"

@app.api_route("/{path:path}", methods=["GET", "POST"])
async def passthrough(request: Request, path: str):
    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)  # let httpx recompute this

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.request(
            request.method,
            f"{TARGET}/{path}",
            content=body,
            headers=headers,
            params=request.query_params,
        )

    # strip hop-by-hop headers that shouldn't be relayed
    excluded = {"content-encoding", "transfer-encoding", "connection"}
    response_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}

    return Response(content=resp.content, status_code=resp.status_code, headers=response_headers)