from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Optional
import json
import httpx
from openai import AsyncOpenAI
from openai import OpenAIError
from openai.types.responses.easy_input_message_param import EasyInputMessageParam
from openai.types.responses.response_function_tool_call_param import ResponseFunctionToolCallParam
from openai.types.responses.response_input_item_param import FunctionCallOutput

from agent_86.core.config import Settings
from agent_86.domain.models.message import Message, MessageRole
from agent_86.domain.schemas.session_summary import ChatSessionSummary
from agent_86.tools.tool import ToolContext, ToolResult
from agent_86.services.tool_service import ToolService
from agent_86.services.tool_selection import should_require_web_search
from agent_86.tools.tool_registry import ToolRegistry


@dataclass
class GeneratedTranscriptMessage:
    role: MessageRole
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatModelReply:
    assistant_text: str
    transcript_messages: list[GeneratedTranscriptMessage]
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass
class ChatStreamEvent:
    event: str
    data: dict[str, Any] = field(default_factory=dict)


ChatStreamEventCallback = Callable[[ChatStreamEvent], Awaitable[None] | None]
DEFAULT_MAX_TOOL_ROUNDTRIPS_PER_REQUEST = 4
ROUNDTRIP_LIMIT_SYSTEM_MESSAGE = (
    "Tool usage limit reached for this request. Do not call any more tools. "
    "Provide the best possible final answer using only the conversation and prior tool results."
)


class ChatModelService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        http_client = httpx.AsyncClient(verify=settings.azure_openai_verify_ssl)

        self._client = AsyncOpenAI(
            base_url=settings.foundry_openai_base_url,
            api_key=settings.foundry_openai_api_key,
            http_client=http_client,
        )

    async def generate_reply(
        self,
        messages: list[Message],
        model: str,
        *,
        tool_service: Optional[ToolService] = None,
        available_tool_names: Optional[list[str]] = None,
        tool_context: Optional[ToolContext] = None,
    ) -> ChatModelReply:
        return await self._generate_reply_internal(
            messages=messages,
            model=model,
            tool_service=tool_service,
            available_tool_names=available_tool_names,
            tool_context=tool_context,
            stream=False,
        )

    async def generate_reply_stream(
        self,
        messages: list[Message],
        model: str,
        *,
        tool_service: Optional[ToolService] = None,
        available_tool_names: Optional[list[str]] = None,
        tool_context: Optional[ToolContext] = None,
        event_callback: Optional[ChatStreamEventCallback] = None,
    ) -> ChatModelReply:
        return await self._generate_reply_internal(
            messages=messages,
            model=model,
            tool_service=tool_service,
            available_tool_names=available_tool_names,
            tool_context=tool_context,
            event_callback=event_callback,
            stream=True,
        )

    async def generate_structured_summary(
        self,
        *,
        model: str,
        system_prompt: str,
        context_payload: dict[str, Any],
    ) -> ChatSessionSummary:
        response = await self._client.responses.create(
            model=model,
            input=[
                self._build_message_item("system", system_prompt),
                self._build_message_item(
                    "user",
                    json.dumps(context_payload, ensure_ascii=False),
                ),
            ],
            tools=[],
        )

        output_text = getattr(response, "output_text", "")
        if not output_text and hasattr(response, "output") and isinstance(response.output, list):
            output_text = self._extract_output_text(response.output)

        if not output_text:
            raise RuntimeError("Structured summary generation returned no output text")

        parsed = self._extract_json_object(output_text)
        normalized = self._normalize_structured_summary_payload(parsed, context_payload)
        return ChatSessionSummary.model_validate(normalized)

    async def _generate_reply_internal(
        self,
        messages: list[Message],
        model: str,
        *,
        tool_service: Optional[ToolService] = None,
        available_tool_names: Optional[list[str]] = None,
        tool_context: Optional[ToolContext] = None,
        event_callback: Optional[ChatStreamEventCallback] = None,
        stream: bool = False,
    ) -> ChatModelReply:
        if available_tool_names is None:
            available_tool_names = []
        if tool_service is None:
            tool_service = ToolService(ToolRegistry())
        if tool_context is None:
            tool_context = ToolContext(session_id="unknown", user_id="unknown", metadata={})

        tools_schema = self._build_tools_schema(available_tool_names)
        conversation_items = [self._message_to_responses_item(message) for message in messages]
        transcript_events: list[GeneratedTranscriptMessage] = []
        streamed_text_parts: list[str] = []
        collected_tool_results: list[ToolResult] = []
        latest_user_message = self._get_latest_user_message(messages)
        max_tool_roundtrips = self._get_max_tool_roundtrips_per_request()
        tool_roundtrips_used = 0
        roundtrip_limit_notice_added = False

        while True:
            tools_allowed = tool_roundtrips_used < max_tool_roundtrips
            effective_tools_schema = tools_schema if tools_allowed else []
            tool_choice = None
            if effective_tools_schema:
                tool_choice = self._resolve_tool_choice(
                    available_tool_names=available_tool_names,
                    latest_user_message=latest_user_message,
                    collected_tool_results=collected_tool_results,
                )

            try:
                if stream:
                    response, streamed_text = await self._stream_response(
                        items=conversation_items,
                        model=model,
                        tools_schema=effective_tools_schema,
                        tool_choice=tool_choice,
                        event_callback=event_callback,
                    )
                    if streamed_text:
                        streamed_text_parts.append(streamed_text)
                    output_text = streamed_text or getattr(response, "output_text", "")
                else:
                    response = await self._client.responses.create(
                        model=model,
                        input=conversation_items,
                        tools=effective_tools_schema,
                        tool_choice=tool_choice,
                        stream=False,
                    )
                    output_text = response.output_text if hasattr(response, "output_text") else ""
            except (OpenAIError, RuntimeError) as exc:
                if stream:
                    raise

                return ChatModelReply(
                    assistant_text=f"OpenAI API error: {str(exc)}",
                    transcript_messages=transcript_events,
                    tool_results=collected_tool_results,
                )

            function_calls = self._extract_function_calls(response)
            if not function_calls:
                final_text = "".join(streamed_text_parts) if stream else output_text
                if not final_text:
                    final_text = output_text

                return ChatModelReply(
                    assistant_text=final_text,
                    transcript_messages=transcript_events,
                    tool_results=collected_tool_results,
                )

            if not tools_allowed:
                if stream:
                    raise RuntimeError("Model attempted tool calls after tool round-trip limit was reached")

                return ChatModelReply(
                    assistant_text="OpenAI API error: Model attempted tool calls after tool round-trip limit was reached",
                    transcript_messages=transcript_events,
                    tool_results=collected_tool_results,
                )

            tool_roundtrips_used += 1

            for call in function_calls:
                call_id = getattr(call, "call_id", None) or getattr(call, "item_id", "")
                tool_name = getattr(call, "name", None) or "unknown_tool"
                args_json = getattr(call, "arguments", "{}")

                try:
                    args = json.loads(args_json)
                except Exception:
                    args = {}

                await self._emit_event(
                    event_callback,
                    ChatStreamEvent(
                        event="tool_call",
                        data={
                            "tool_name": tool_name,
                            "call_id": call_id,
                            "arguments": args,
                        },
                    ),
                )

                tool_results = await tool_service.execute_tools(
                    tool_names=[tool_name],
                    query=args.get("query", ""),
                    context=tool_context,
                )

                tool_result = tool_results[0] if tool_results else ToolResult(
                    tool_name=tool_name,
                    content="No result",
                    metadata={},
                )
                collected_tool_results.append(tool_result)

                transcript_events.append(
                    GeneratedTranscriptMessage(
                        role="assistant",
                        content=f"Tool call: {tool_name}({args_json})",
                        metadata={
                            "message_type": "function_call",
                            "tool_name": tool_name,
                            "call_id": call_id,
                            "arguments": args_json,
                        },
                    )
                )
                transcript_events.append(
                    GeneratedTranscriptMessage(
                        role="tool",
                        content=str(tool_result.content),
                        metadata={
                            "message_type": "function_call_output",
                            "tool_name": tool_name,
                            "call_id": call_id,
                        },
                    )
                )

                await self._emit_event(
                    event_callback,
                    ChatStreamEvent(
                        event="tool_result",
                        data={
                            "tool_name": tool_name,
                            "call_id": call_id,
                            "content": str(tool_result.content),
                        },
                    ),
                )

                conversation_items.append(
                    self._build_tool_call_item(
                        call_id=call_id,
                        tool_name=tool_name,
                        args_json=args_json,
                    )
                )
                conversation_items.append(
                    self._build_function_call_output_item(
                        call_id=call_id,
                        output=str(tool_result.content),
                    )
                )

            if tool_roundtrips_used >= max_tool_roundtrips and not roundtrip_limit_notice_added:
                conversation_items.append(
                    self._build_message_item("system", ROUNDTRIP_LIMIT_SYSTEM_MESSAGE)
                )
                roundtrip_limit_notice_added = True

    def _build_tools_schema(self, available_tool_names: list[str]) -> list[dict[str, Any]]:
        tools_schema = []

        for tool_name in available_tool_names:
            if tool_name == "web_search":
                tools_schema.append(
                    {
                        "name": "web_search",
                        "type": "function",
                        "description": "Search the web for current or external information relevant to the conversation.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query to run on the web.",
                                }
                            },
                            "required": ["query"],
                            "additionalProperties": False,
                        },
                    }
                )

        return tools_schema

    def _build_tool_call_item(
        self,
        call_id: str,
        tool_name: str,
        args_json: str,
    ) -> ResponseFunctionToolCallParam:
        return ResponseFunctionToolCallParam(
            type="function_call",
            call_id=call_id,
            name=tool_name,
            arguments=args_json,
        )

    def _build_function_call_output_item(
        self,
        call_id: str,
        output: str,
    ) -> FunctionCallOutput:
        return FunctionCallOutput(
            type="function_call_output",
            call_id=call_id,
            output=output,
        )

    def _build_message_item(self, role: str, content: str) -> EasyInputMessageParam:
        return EasyInputMessageParam(
            type="message",
            role=role,
            content=content,
        )

    def _build_multimodal_message_item(
        self,
        role: str,
        text: str,
        image_blocks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "input_text", "text": text}]
        content.extend(image_blocks)
        return {
            "type": "message",
            "role": role,
            "content": content,
        }

    def _message_to_responses_item(self, message: Message) -> dict[str, Any]:
        if message.role == "assistant" and message.metadata.get("message_type") == "function_call":
            return self._build_tool_call_item(
                call_id=message.metadata.get("call_id", ""),
                tool_name=message.metadata.get("tool_name", ""),
                args_json=message.metadata.get("arguments", "{}"),
            )

        if message.role == "tool" and message.metadata.get("message_type") == "function_call_output":
            return self._build_function_call_output_item(
                call_id=message.metadata.get("call_id", ""),
                output=message.content,
            )

        if message.role == "user":
            image_blocks = message.metadata.get("_image_content_blocks")
            if isinstance(image_blocks, list) and image_blocks:
                return self._build_multimodal_message_item(
                    role="user",
                    text=message.content,
                    image_blocks=image_blocks,
                )
            return self._build_message_item("user", message.content)

        if message.role in {"system", "assistant"}:
            return self._build_message_item(message.role, message.content)

        return self._build_message_item("system", message.content)

    def _extract_function_calls(self, response: Any) -> list[Any]:
        if hasattr(response, "function_calls") and response.function_calls:
            return list(response.function_calls)

        if hasattr(response, "output") and isinstance(response.output, list):
            return [
                item
                for item in response.output
                if getattr(item, "type", None) == "function_call"
            ]

        return []

    def _get_max_tool_roundtrips_per_request(self) -> int:
        settings = getattr(self, "_settings", None)
        configured_value = getattr(
            settings,
            "tool_roundtrip_max_per_request",
            DEFAULT_MAX_TOOL_ROUNDTRIPS_PER_REQUEST,
        )
        if not isinstance(configured_value, int):
            return DEFAULT_MAX_TOOL_ROUNDTRIPS_PER_REQUEST

        return max(0, configured_value)

    def _get_latest_user_message(self, messages: list[Message]) -> str:
        for message in reversed(messages):
            if message.role == "user":
                return message.content

        return ""

    def _resolve_tool_choice(
        self,
        *,
        available_tool_names: list[str],
        latest_user_message: str,
        collected_tool_results: list[ToolResult],
    ) -> str | None:
        if not available_tool_names:
            return None

        if collected_tool_results:
            return "auto"

        if "web_search" in available_tool_names and should_require_web_search(latest_user_message):
            return "required"

        return "auto"

    async def _stream_response(
        self,
        *,
        items: list[dict[str, Any]],
        model: str,
        tools_schema: list[dict[str, Any]],
        tool_choice: str | None,
        event_callback: Optional[ChatStreamEventCallback],
    ) -> tuple[Any, str]:
        stream = await self._client.responses.create(
            model=model,
            input=items,
            tools=tools_schema,
            tool_choice=tool_choice,
            stream=True,
        )

        output_parts: list[str] = []
        completed_response: Any | None = None

        async for event in stream:
            event_type = getattr(event, "type", "")

            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", "")
                if delta:
                    output_parts.append(delta)
                    await self._emit_event(
                        event_callback,
                        ChatStreamEvent(event="delta", data={"text": delta}),
                    )
            elif event_type == "response.completed":
                completed_response = getattr(event, "response", None)
            elif event_type in {"response.error", "response.failed"}:
                error = getattr(event, "error", None)
                raise RuntimeError(str(error or "Streaming response failed"))

        if completed_response is None:
            raise RuntimeError("Streaming response completed without a final response payload")

        return completed_response, "".join(output_parts)

    async def _emit_event(
        self,
        event_callback: Optional[ChatStreamEventCallback],
        event: ChatStreamEvent,
    ) -> None:
        if event_callback is None:
            return

        result = event_callback(event)
        if result is not None:
            await result

    def _extract_output_text(self, output_items: list[Any]) -> str:
        parts: list[str] = []
        for item in output_items:
            content = getattr(item, "content", None)
            if not isinstance(content, list):
                continue

            for part in content:
                text = getattr(part, "text", None)
                if isinstance(text, str) and text:
                    parts.append(text)

        return "".join(parts)

    def _extract_json_object(self, value: str) -> dict[str, Any]:
        text = value.strip()
        if text.startswith("```"):
            segments = [segment.strip() for segment in text.split("```") if segment.strip()]
            for segment in segments:
                candidate = segment
                if candidate.lower().startswith("json"):
                    candidate = candidate[4:].strip()
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed

        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("Structured summary response must be a JSON object")
        return parsed

    def _normalize_structured_summary_payload(
        self,
        payload: dict[str, Any],
        context_payload: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(payload)

        if "artifact_refs" in normalized and "artifacts_generated" not in normalized:
            normalized["artifacts_generated"] = normalized.pop("artifact_refs")

        normalized.setdefault("session_id", context_payload.get("session_id", "unknown-session"))
        normalized.setdefault("date_range_start", context_payload.get("date_range_start"))
        normalized.setdefault("date_range_end", context_payload.get("date_range_end"))

        if not normalized.get("one_line_summary"):
            title = str(normalized.get("title", "")).strip()
            topics = normalized.get("topics")
            topic_list = [str(topic).strip() for topic in topics] if isinstance(topics, list) else []
            topic_list = [topic for topic in topic_list if topic]

            if title and topic_list:
                normalized["one_line_summary"] = f"{title}: {', '.join(topic_list)}."
            elif title:
                normalized["one_line_summary"] = title
            else:
                normalized["one_line_summary"] = "Session summary generated from chat context."

        normalized.setdefault("topics", [])
        normalized.setdefault("key_decisions", [])
        normalized.setdefault("action_items", [])
        normalized.setdefault("artifacts_generated", [])
        normalized.setdefault("open_questions", [])
        normalized.setdefault("tools_used", [])
        normalized.setdefault("tags", [])

        normalized["artifacts_generated"] = self._normalize_artifact_refs(
            normalized["artifacts_generated"],
            context_payload.get("persisted_artifacts", []),
        )

        return normalized

    def _normalize_artifact_refs(self, value: Any, persisted_artifacts: Any) -> list[Any]:
        if not isinstance(value, list):
            return []

        artifacts_by_id = {
            artifact_id: artifact
            for artifact in persisted_artifacts
            if isinstance(artifact, dict)
            and isinstance((artifact_id := artifact.get("id")), str)
            and artifact_id
        } if isinstance(persisted_artifacts, list) else {}

        normalized: list[Any] = []
        for artifact_ref in value:
            if not isinstance(artifact_ref, str):
                normalized.append(artifact_ref)
                continue

            artifact = artifacts_by_id.get(artifact_ref)
            if artifact is None:
                continue

            filename = artifact.get("filename")
            content_type = artifact.get("content_type")
            if not isinstance(filename, str) or not filename:
                continue

            normalized.append(
                {
                    "name": filename,
                    "artifact_type": self._infer_artifact_type(filename, content_type),
                    "location": artifact_ref,
                }
            )

        return normalized

    def _infer_artifact_type(self, filename: str, content_type: Any) -> str:
        lower_name = filename.lower()
        lower_content_type = content_type.lower() if isinstance(content_type, str) else ""
        if lower_name.endswith(".docx") or "officedocument.wordprocessingml" in lower_content_type:
            return "docx"
        if lower_name.endswith(".pptx") or "presentationml" in lower_content_type:
            return "pptx"
        if lower_name.endswith(".xlsx") or "spreadsheetml" in lower_content_type:
            return "xlsx"
        if any(extension in lower_name for extension in (".drawio", ".vsdx", ".mmd", ".svg")):
            return "diagram"
        if any(extension in lower_name for extension in (".py", ".ts", ".tsx", ".js", ".json", ".yaml", ".yml", ".md")):
            return "code"
        return "other"
