import httpx
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncOpenAI

from agent_86.core.config import settings
from agent_86.domain.models.message import Message
from agent_86.tools.tool import ToolResult


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
        tool_results: list[ToolResult] | None = None,
    ) -> str:
        # Build a structured messages array for the Responses API
        input_messages = [
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": "You are a helpful assistant."}
                ],
            }
        ]

        # Optionally add system message about external tools
        if tool_results:
            input_messages.append(
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "External tools were executed. Their results are included in the conversation history.",
                        }
                    ],
                }
            )


        def _content_type_for_role(role: str) -> str:
            return "output_text" if role == "assistant" else "input_text"

        # Append conversation messages as structured roles and contents
        for message in messages:
            input_messages.append(
                {
                    "role": message.role,
                    "content": [{"type": _content_type_for_role(message.role), "text": message.content}],
                }
            )

        response = await self._client.responses.create(
            model=model,
            input=input_messages,
        )

        return response.output_text
