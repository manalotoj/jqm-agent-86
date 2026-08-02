from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Optional
import json
import httpx
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncOpenAI
from openai import OpenAIError
from openai.types.responses.easy_input_message_param import EasyInputMessageParam
from openai.types.responses.response_function_tool_call_param import ResponseFunctionToolCallParam
from openai.types.responses.response_input_item_param import FunctionCallOutput

from agent_86.core.config import settings
from agent_86.domain.models.message import Message, MessageRole
from agent_86.tools.tool import ToolContext, ToolResult
from agent_86.services.tool_service import ToolService
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


@dataclass
class ChatStreamEvent:
    event: str
    data: dict[str, Any] = field(default_factory=dict)


ChatStreamEventCallback = Callable[[ChatStreamEvent], Awaitable[None] | None]


class ChatModelService:
    def __init__(self) -> None:
        self._credential = DefaultAzureCredential()
        self._token_provider = get_bearer_token_provider(
            self._credential,
            "https://ai.azure.com/.default",
        )

        http_client = httpx.AsyncClient(verify=settings.azure_openai_verify_ssl)

        self._client = AsyncOpenAI(
            base_url=settings.foundry_openai_base_url,
            api_key=self._token_provider,
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

        while True:
            try:
                if stream:
                    response, streamed_text = await self._stream_response(
                        items=conversation_items,
                        model=model,
                        tools_schema=tools_schema,
                        event_callback=event_callback,
                    )
                    if streamed_text:
                        streamed_text_parts.append(streamed_text)
                    output_text = streamed_text or getattr(response, "output_text", "")
                else:
                    response = await self._client.responses.create(
                        model=model,
                        input=conversation_items,
                        tools=tools_schema,
                        stream=False,
                    )
                    output_text = response.output_text if hasattr(response, "output_text") else ""
            except (OpenAIError, RuntimeError) as exc:
                if stream:
                    raise

                return ChatModelReply(
                    assistant_text=f"OpenAI API error: {str(exc)}",
                    transcript_messages=transcript_events,
                )

            function_calls = self._extract_function_calls(response)
            if not function_calls:
                final_text = "".join(streamed_text_parts) if stream else output_text
                if not final_text:
                    final_text = output_text

                return ChatModelReply(
                    assistant_text=final_text,
                    transcript_messages=transcript_events,
                )

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

        if message.role in {"system", "user", "assistant"}:
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

    async def _stream_response(
        self,
        *,
        items: list[dict[str, Any]],
        model: str,
        tools_schema: list[dict[str, Any]],
        event_callback: Optional[ChatStreamEventCallback],
    ) -> tuple[Any, str]:
        stream = await self._client.responses.create(
            model=model,
            input=items,
            tools=tools_schema,
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
