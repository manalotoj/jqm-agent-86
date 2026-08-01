from dataclasses import dataclass, field
from typing import Any, Optional, List
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


@dataclass
class GeneratedTranscriptMessage:
    role: MessageRole
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatModelReply:
    assistant_text: str
    transcript_messages: List[GeneratedTranscriptMessage]


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
        available_tool_names: Optional[List[str]] = None,
        tool_context: Optional[ToolContext] = None,
    ) -> ChatModelReply:
        if available_tool_names is None:
            available_tool_names = []
        if tool_service is None:
            tool_service = ToolService()
        if tool_context is None:
            tool_context = ToolContext(session_id="unknown", user_id="unknown", metadata={})

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

        def build_tool_call_item(call_id: str, tool_name: str, args_json: str) -> ResponseFunctionToolCallParam:
            return ResponseFunctionToolCallParam(
                type="function_call",
                call_id=call_id,
                name=tool_name,
                arguments=args_json,
            )

        def build_function_call_output_item(call_id: str, output: str) -> FunctionCallOutput:
            return FunctionCallOutput(
                type="function_call_output",
                call_id=call_id,
                output=output,
            )

        def build_message_item(role: str, content: str) -> EasyInputMessageParam:
            return EasyInputMessageParam(
                type="message",
                role=role,
                content=content,
            )

        def message_to_responses_item(message: Message) -> dict[str, Any]:
            if message.role == "assistant" and message.metadata.get("message_type") == "function_call":
                return build_tool_call_item(
                    call_id=message.metadata.get("call_id", ""),
                    tool_name=message.metadata.get("tool_name", ""),
                    args_json=message.metadata.get("arguments", "{}"),
                )
            if message.role == "tool" and message.metadata.get("message_type") == "function_call_output":
                return build_function_call_output_item(
                    call_id=message.metadata.get("call_id", ""),
                    output=message.content,
                )
            if message.role == "system" or message.role == "user":
                return build_message_item(message.role, message.content)
            if message.role == "assistant":
                return build_message_item(message.role, message.content)
            return build_message_item("system", message.content)

        conversation_items = [message_to_responses_item(m) for m in messages]
        transcript_events: List[GeneratedTranscriptMessage] = []

        async def call_model_loop(items) -> str:
            while True:
                try:
                    response = await self._client.responses.create(
                        model=model,
                        input=items,
                        tools=tools_schema,
                        stream=False,
                    )
                except OpenAIError as e:
                    return f"OpenAI API error: {str(e)}"

                output_text = response.output_text if hasattr(response, "output_text") else ""

                function_calls = []

                if hasattr(response, "function_calls") and response.function_calls:
                    function_calls = response.function_calls
                elif hasattr(response, "output") and isinstance(response.output, list):
                    function_calls = [
                        item for item in response.output if getattr(item, "type", None) == "function_call"
                    ]

                if not function_calls:
                    transcript_events.append(
                        GeneratedTranscriptMessage(
                            role="assistant",
                            content=output_text,
                            metadata={"source": "model_response"},
                        )
                    )
                    return output_text

                for call in function_calls:
                    call_id = getattr(call, "call_id", None)
                    tool_name = getattr(call, "name", None)
                    args_json = getattr(call, "arguments", "{}")

                    try:
                        args = json.loads(args_json)
                    except Exception:
                        args = {}

                    tool_results = await tool_service.execute_tools(
                        tool_names=[tool_name],
                        query=args.get("query", ""),
                        context=tool_context,
                    )

                    tool_result = tool_results[0] if tool_results else ToolResult(
                        tool_name=tool_name, content="No result", metadata={}
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
                            }
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

                    items.append(build_tool_call_item(call_id=call_id, tool_name=tool_name, args_json=args_json))
                    items.append(build_function_call_output_item(call_id=call_id, output=str(tool_result.content)))

        final_text = await call_model_loop(conversation_items)
        return ChatModelReply(assistant_text=final_text, transcript_messages=transcript_events)
