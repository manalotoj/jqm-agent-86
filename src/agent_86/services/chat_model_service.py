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
        prompt_parts: list[str] = [
            "You are a helpful assistant.",
        ]

        if tool_results:
            prompt_parts.append(
                "External tools were executed. Their results are included in the conversation history."
            )

        prompt_parts.extend(
            f"{message.role}: {message.content}"
            for message in messages
        )

        prompt = "\n".join(prompt_parts)

        response = await self._client.responses.create(
            model=model,
            input=prompt,
        )

        return response.output_text