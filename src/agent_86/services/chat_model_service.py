import httpx
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncOpenAI

from agent_86.core.config import settings
from agent_86.domain.models.message import Message


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
    ) -> str:
        prompt = "\n".join(
            f"{message.role}: {message.content}"
            for message in messages
        )

        response = await self._client.responses.create(
            model=model,
            input=prompt,
        )

        return response.output_text