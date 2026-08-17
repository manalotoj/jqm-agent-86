"""
OpenAI Chat Completions <-> Azure AI Foundry Responses API compatibility proxy.

Designed for clients such as Cline that speak the OpenAI Chat Completions API
but need to call Foundry GPT-5.x reasoning/tool models through /responses.

Features:
- Native passthrough for normal /chat/completions requests.
- Translation to /responses for reasoning + tools.
- Continues routing tool-result turns through /responses.
- Replays opaque reasoning items before the matching function calls.
- Converts Responses output back to Chat Completions format.
- Returns SSE-compatible Chat Completion chunks if the client requested stream=true.
- Provides a local /models endpoint for Cline.

Install:
    pip install fastapi uvicorn httpx

Run:
    set FOUNDRY_TARGET=https://YOUR-RESOURCE.services.ai.azure.com/api/projects/proj-default/openai/v1
    uvicorn proxy:app --host 127.0.0.1 --port 8787

Cline base URL:
    http://127.0.0.1:8787

Use the same API key / Authorization header in Cline that you use against Foundry.
"""

import asyncio
import json
import os
import time
import uuid
from typing import Any, AsyncIterator, Iterator

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()

TARGET = os.getenv(
    "FOUNDRY_TARGET",
    "https://foundry-jqm-westus-default.services.ai.azure.com/"
    "api/projects/proj-default/openai/v1",
).rstrip("/")

# Add or remove models as appropriate for your Foundry project.
RESPONSES_API_MODELS = {
    "gpt-5.6-luna",
    "gpt-5.6-terra",
    "gpt-5.6-sol",
}

HTTP_TIMEOUT_SECONDS = float(os.getenv("FOUNDRY_TIMEOUT_SECONDS", "300"))

# call_id -> Responses reasoning item
#
# Reasoning models may require the opaque reasoning item emitted before a
# function call to be included when the function_call_output is sent later.
#
# Cline only knows the Chat Completions tool-call format, so it cannot retain
# Responses reasoning items itself. The proxy keeps them keyed by call_id.
REASONING_CACHE: dict[str, dict[str, Any]] = {}


# -----------------------------------------------------------------------------
# Request classification
# -----------------------------------------------------------------------------

def get_reasoning_effort(payload: dict[str, Any]) -> str | None:
    """
    Support both possible request shapes:

        {"reasoning_effort": "medium"}

    and:

        {"reasoning": {"effort": "medium"}}
    """
    top_level = payload.get("reasoning_effort")
    if top_level is not None:
        return top_level

    reasoning = payload.get("reasoning")
    if isinstance(reasoning, dict):
        return reasoning.get("effort")

    return None


def request_contains_cached_tool_call(payload: dict[str, Any]) -> bool:
    """
    True when this request is a continuation of a previous translated tool call.

    Cline typically sends back:
      - the assistant message containing tool_calls
      - one or more role=tool messages

    We look for a tool_call ID that exists in our reasoning cache.
    """
    for message in payload.get("messages", []) or []:
        role = message.get("role")

        if role == "tool":
            call_id = message.get("tool_call_id")
            if call_id and call_id in REASONING_CACHE:
                return True

        if role == "assistant":
            for tool_call in message.get("tool_calls", []) or []:
                call_id = tool_call.get("id")
                if call_id and call_id in REASONING_CACHE:
                    return True

    return False


def needs_responses_api(payload: dict[str, Any]) -> bool:
    """
    Route to Responses when:

    1. This is a GPT-5.6 family request with tools and a reasoning effort, OR
    2. This is a continuation of a previously translated tool loop.

    The second condition is important: Cline may omit reasoning_effort on the
    tool-result follow-up turn, but that turn must still use /responses so the
    original reasoning item can be replayed.
    """
    model = payload.get("model", "")
    if model not in RESPONSES_API_MODELS:
        return False

    effort = get_reasoning_effort(payload)
    has_tools = bool(payload.get("tools"))

    initial_reasoning_tool_request = (
        has_tools
        and effort not in (None, "", "none")
    )

    return initial_reasoning_tool_request or request_contains_cached_tool_call(payload)


# -----------------------------------------------------------------------------
# Chat Completions -> Responses API conversion
# -----------------------------------------------------------------------------

def chat_content_to_responses_content(
    content: Any,
    *,
    role: str,
) -> Any:
    """
    Convert common Chat Completions content forms to Responses content forms.

    Cline generally sends strings, but this supports basic text and image
    Chat Completions content blocks as well.
    """
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return str(content)

    converted: list[dict[str, Any]] = []

    for part in content:
        if isinstance(part, str):
            converted.append(
                {
                    "type": "input_text" if role != "assistant" else "output_text",
                    "text": part,
                }
            )
            continue

        if not isinstance(part, dict):
            continue

        part_type = part.get("type")

        if part_type in ("text", "input_text", "output_text"):
            converted.append(
                {
                    "type": "input_text" if role != "assistant" else "output_text",
                    "text": part.get("text", ""),
                }
            )

        elif part_type == "image_url":
            image_url = part.get("image_url", {})
            if isinstance(image_url, dict):
                url = image_url.get("url")
            else:
                url = image_url

            if url:
                converted.append(
                    {
                        "type": "input_image",
                        "image_url": url,
                    }
                )

        else:
            # Preserve unknown blocks rather than silently discarding them.
            converted.append(part)

    return converted


def chat_messages_to_responses_input(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert Chat Completions messages into Responses API input items.
    """
    input_items: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role")

        # Responses supports developer; map system -> developer.
        if role in ("system", "developer", "user"):
            response_role = "developer" if role == "system" else role

            input_items.append(
                {
                    "type": "message",
                    "role": response_role,
                    "content": chat_content_to_responses_content(
                        msg.get("content", ""),
                        role=response_role,
                    ),
                }
            )
            continue

        if role == "assistant":
            content = msg.get("content")

            if content not in (None, ""):
                input_items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": chat_content_to_responses_content(
                            content,
                            role="assistant",
                        ),
                    }
                )

            tool_calls = msg.get("tool_calls", []) or []

            # Replay cached reasoning items immediately before the corresponding
            # function_call item(s). If multiple tool calls share the same
            # reasoning item, include that item only once.
            replayed_reasoning_ids: set[str] = set()

            for tool_call in tool_calls:
                call_id = tool_call.get("id")

                reasoning_item = REASONING_CACHE.get(call_id)
                if reasoning_item is not None:
                    reasoning_id = reasoning_item.get("id") or call_id

                    if reasoning_id not in replayed_reasoning_ids:
                        input_items.append(reasoning_item)
                        replayed_reasoning_ids.add(reasoning_id)

                function = tool_call.get("function", {}) or {}

                input_items.append(
                    {
                        "type": "function_call",
                        "call_id": call_id,
                        "name": function.get("name"),
                        "arguments": function.get("arguments", "{}"),
                    }
                )

            continue

        if role == "tool":
            tool_call_id = msg.get("tool_call_id")

            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": tool_call_id,
                    "output": msg.get("content", ""),
                }
            )

            continue

    return input_items


def chat_tools_to_responses_tools(
    tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """
    Chat Completions:

        {
          "type": "function",
          "function": {
            "name": "...",
            "description": "...",
            "parameters": {...}
          }
        }

    Responses API:

        {
          "type": "function",
          "name": "...",
          "description": "...",
          "parameters": {...}
        }
    """
    flattened: list[dict[str, Any]] = []

    for tool in tools or []:
        if tool.get("type") != "function":
            flattened.append(tool)
            continue

        function = tool.get("function", {}) or {}

        flattened.append(
            {
                "type": "function",
                "name": function.get("name"),
                "description": function.get("description", ""),
                "parameters": function.get("parameters", {}),
            }
        )

    return flattened


def chat_tool_choice_to_responses_tool_choice(tool_choice: Any) -> Any:
    """
    Convert a named Chat Completions tool choice to Responses format.

    Chat:
        {"type": "function", "function": {"name": "my_tool"}}

    Responses:
        {"type": "function", "name": "my_tool"}
    """
    if not isinstance(tool_choice, dict):
        return tool_choice

    if tool_choice.get("type") == "function":
        function = tool_choice.get("function", {}) or {}
        name = function.get("name")

        if name:
            return {
                "type": "function",
                "name": name,
            }

    return tool_choice


def chat_request_to_responses_request(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Convert an OpenAI Chat Completions request to a Responses API request.

    Intentionally does NOT pass through stream=true. We buffer the Responses
    result and emit Chat-Completions SSE ourselves when the caller requested
    streaming.
    """
    responses_payload: dict[str, Any] = {
        "model": payload["model"],
        "input": chat_messages_to_responses_input(payload.get("messages", [])),
        "stream": False,
    }

    tools = payload.get("tools")
    if tools:
        responses_payload["tools"] = chat_tools_to_responses_tools(tools)

    if payload.get("tool_choice") is not None:
        responses_payload["tool_choice"] = chat_tool_choice_to_responses_tool_choice(
            payload["tool_choice"]
        )

    reasoning_effort = get_reasoning_effort(payload)
    if reasoning_effort not in (None, "", "none"):
        responses_payload["reasoning"] = {
            "effort": reasoning_effort,
        }

    # Chat Completions clients vary between these names.
    max_tokens = (
        payload.get("max_completion_tokens")
        if payload.get("max_completion_tokens") is not None
        else payload.get("max_tokens")
    )

    if max_tokens is not None:
        responses_payload["max_output_tokens"] = max_tokens

    # Some reasoning models/providers reject temperature. Only send it if
    # Cline actually supplied it.
    if payload.get("temperature") is not None:
        responses_payload["temperature"] = payload["temperature"]

    if payload.get("top_p") is not None:
        responses_payload["top_p"] = payload["top_p"]

    return responses_payload


# -----------------------------------------------------------------------------
# Responses API -> Chat Completions conversion
# -----------------------------------------------------------------------------

def cache_reasoning_items(output: list[dict[str, Any]]) -> None:
    """
    Associate the most recent reasoning item with subsequent function calls.

    Typical Responses output sequence:

        reasoning
        function_call
        function_call

    All following calls are associated with that reasoning item.
    """
    pending_reasoning: dict[str, Any] | None = None

    for item in output:
        item_type = item.get("type")

        if item_type == "reasoning":
            pending_reasoning = item
            continue

        if item_type == "function_call" and pending_reasoning is not None:
            call_id = item.get("call_id")
            if call_id:
                REASONING_CACHE[call_id] = pending_reasoning


def extract_message_text(item: dict[str, Any]) -> str:
    """
    Extract visible assistant text from a Responses `message` output item.
    """
    content = item.get("content")

    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return ""

    parts: list[str] = []

    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue

        if not isinstance(block, dict):
            continue

        if block.get("type") in ("output_text", "text"):
            parts.append(block.get("text", ""))

    return "".join(parts)


def responses_result_to_chat_completion(
    resp_json: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    """
    Convert a completed Responses result to a normal Chat Completions object.
    """
    output = resp_json.get("output", []) or []
    cache_reasoning_items(output)

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for item in output:
        item_type = item.get("type")

        if item_type == "reasoning":
            # Do not expose reasoning / chain of thought to Cline.
            continue

        if item_type == "message":
            text = extract_message_text(item)
            if text:
                text_parts.append(text)
            continue

        if item_type == "function_call":
            tool_calls.append(
                {
                    "id": item.get("call_id", f"call_{uuid.uuid4().hex[:24]}"),
                    "type": "function",
                    "function": {
                        "name": item.get("name"),
                        "arguments": item.get("arguments", "{}"),
                    },
                }
            )

    # Foundry/OpenAI may also provide aggregate output_text.
    top_level_text = resp_json.get("output_text")
    final_text = "".join(text_parts) or top_level_text or None

    message: dict[str, Any] = {
        "role": "assistant",
        "content": final_text,
    }

    if tool_calls:
        # Most OpenAI-compatible clients expect null content when tool_calls
        # are present.
        message["content"] = None
        message["tool_calls"] = tool_calls

    usage = resp_json.get("usage", {}) or {}

    finish_reason = "tool_calls" if tool_calls else "stop"

    return {
        "id": resp_json.get("id", f"chatcmpl_{uuid.uuid4().hex[:24]}"),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }


# -----------------------------------------------------------------------------
# Chat Completion SSE generation
# -----------------------------------------------------------------------------

def sse_event(data: dict[str, Any] | str) -> bytes:
    """
    Serialize one Server-Sent Event frame.
    """
    if isinstance(data, str):
        return f"data: {data}\n\n".encode("utf-8")

    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


def chat_completion_to_sse(
    completion: dict[str, Any],
) -> Iterator[bytes]:
    """
    Emit buffered Chat Completion data as OpenAI-compatible SSE.

    This is protocol-compatible streaming, not token-by-token upstream
    streaming. Cline receives valid SSE and can process text/tool calls.
    """
    choice = completion["choices"][0]
    message = choice["message"]

    completion_id = completion["id"]
    created = completion["created"]
    model = completion["model"]

    # Initial role event.
    yield sse_event(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                    },
                    "finish_reason": None,
                }
            ],
        }
    )

    delta: dict[str, Any] = {}

    if message.get("content") is not None:
        delta["content"] = message["content"]

    if message.get("tool_calls"):
        # Supplying a complete tool call in one SSE delta is valid and avoids
        # having to reconstruct partial function arguments.
        delta["tool_calls"] = []

        for index, tool_call in enumerate(message["tool_calls"]):
            delta["tool_calls"].append(
                {
                    "index": index,
                    "id": tool_call["id"],
                    "type": "function",
                    "function": {
                        "name": tool_call["function"]["name"],
                        "arguments": tool_call["function"]["arguments"],
                    },
                }
            )

    if delta:
        yield sse_event(
            {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": delta,
                        "finish_reason": None,
                    }
                ],
            }
        )

    # Completion event.
    yield sse_event(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": choice["finish_reason"],
                }
            ],
        }
    )

    yield sse_event("[DONE]")


# -----------------------------------------------------------------------------
# Generic passthrough helpers
# -----------------------------------------------------------------------------

def upstream_headers(request: Request) -> dict[str, str]:
    """
    Copy request headers while removing hop-by-hop/local headers.

    Authorization and api-key headers are retained and passed to Foundry.
    """
    headers = dict(request.headers)

    for name in (
        "host",
        "content-length",
        "connection",
        "transfer-encoding",
    ):
        headers.pop(name, None)

    return headers


def response_headers_from_upstream(headers: httpx.Headers) -> dict[str, str]:
    """
    Remove hop-by-hop headers that Starlette/Uvicorn manages itself.
    """
    excluded = {
        "content-encoding",
        "content-length",
        "transfer-encoding",
        "connection",
    }

    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in excluded
    }


async def stream_upstream_response(
    client: httpx.AsyncClient,
    upstream_response: httpx.Response,
) -> AsyncIterator[bytes]:
    """
    Forward an upstream stream without buffering it.
    """
    try:
        async for chunk in upstream_response.aiter_raw():
            yield chunk
    finally:
        await upstream_response.aclose()
        await client.aclose()


# -----------------------------------------------------------------------------
# Cline-facing endpoints
# -----------------------------------------------------------------------------

@app.get("/models")
@app.get("/v1/models")
async def models() -> dict[str, Any]:
    """
    Cline commonly probes /models. Return aliases that are valid at this proxy.
    """
    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": 0,
                "owned_by": "azure-ai-foundry",
            }
            for model in sorted(RESPONSES_API_MODELS)
        ],
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(request: Request, path: str):
    body = await request.body()
    payload: dict[str, Any] | None = None

    is_chat_completion = path.rstrip("/").endswith("chat/completions")

    if is_chat_completion and body:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = None

    translate = bool(payload and needs_responses_api(payload))

    if payload:
        print(
            "INCOMING",
            json.dumps(
                {
                    "model": payload.get("model"),
                    "stream": payload.get("stream"),
                    "reasoning_effort": get_reasoning_effort(payload),
                    "has_tools": bool(payload.get("tools")),
                    "cached_tool_continuation": request_contains_cached_tool_call(
                        payload
                    ),
                    "translate": translate,
                }
            ),
            flush=True,
        )

    # -------------------------------------------------------------------------
    # Responses translation path
    # -------------------------------------------------------------------------
    if translate and payload is not None:
        responses_payload = chat_request_to_responses_request(payload)
        url = f"{TARGET}/responses"

        headers = upstream_headers(request)

        # We explicitly request JSON because this proxy buffers the Responses
        # response, then sends Chat Completion JSON or SSE to the caller.
        headers["accept"] = "application/json"
        headers["content-type"] = "application/json"

        print("=" * 80, flush=True)
        print(f"TRANSLATING {request.method} /{path} -> {url}", flush=True)
        print(
            json.dumps(responses_payload, indent=2, ensure_ascii=False),
            flush=True,
        )
        print("=" * 80, flush=True)

        try:
            async with httpx.AsyncClient(
                timeout=HTTP_TIMEOUT_SECONDS
            ) as client:
                upstream = await client.post(
                    url,
                    content=json.dumps(responses_payload).encode("utf-8"),
                    headers=headers,
                    params=request.query_params,
                )
        except httpx.HTTPError as exc:
            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "message": f"Could not reach Foundry: {exc}",
                        "type": "proxy_error",
                    }
                },
            )

        # Preserve actual Foundry errors so they are visible in Cline/logs.
        if upstream.status_code < 200 or upstream.status_code >= 300:
            print(
                f"FOUNDARY RESPONSES ERROR {upstream.status_code}: "
                f"{upstream.text}",
                flush=True,
            )

            return Response(
                content=upstream.content,
                status_code=upstream.status_code,
                headers=response_headers_from_upstream(upstream.headers),
                media_type=upstream.headers.get(
                    "content-type",
                    "application/json",
                ),
            )

        try:
            response_json = upstream.json()
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "message": (
                            "Foundry returned a successful response that was "
                            "not valid JSON."
                        ),
                        "type": "proxy_error",
                        "upstream_body": upstream.text[:4000],
                    }
                },
            )

        print("=" * 80, flush=True)
        print("RAW RESPONSES API REPLY", flush=True)
        print(json.dumps(response_json, indent=2, ensure_ascii=False), flush=True)
        print("=" * 80, flush=True)

        chat_completion = responses_result_to_chat_completion(
            response_json,
            payload["model"],
        )

        # Cline requested stream=true. Return valid OpenAI-style SSE even
        # though the Foundry Responses request itself was buffered.
        if payload.get("stream") is True:
            return StreamingResponse(
                chat_completion_to_sse(chat_completion),
                status_code=200,
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        return Response(
            content=json.dumps(chat_completion, ensure_ascii=False).encode("utf-8"),
            status_code=200,
            media_type="application/json",
        )

    # -------------------------------------------------------------------------
    # Normal native passthrough path
    # -------------------------------------------------------------------------
    url = f"{TARGET}/{path.lstrip('/')}"
    headers = upstream_headers(request)

    print(
        f"PASSTHROUGH {request.method} /{path} -> {url}",
        flush=True,
    )

    client = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)

    try:
        upstream_request = client.build_request(
            request.method,
            url,
            content=body,
            headers=headers,
            params=request.query_params,
        )

        upstream_response = await client.send(
            upstream_request,
            stream=True,
        )

    except httpx.HTTPError as exc:
        await client.aclose()

        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "message": f"Could not reach Foundry: {exc}",
                    "type": "proxy_error",
                }
            },
        )

    return StreamingResponse(
        stream_upstream_response(client, upstream_response),
        status_code=upstream_response.status_code,
        headers=response_headers_from_upstream(upstream_response.headers),
        media_type=upstream_response.headers.get("content-type"),
    )