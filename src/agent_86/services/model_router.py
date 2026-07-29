from agent_86.core.config import settings


class ModelRouter:
    def choose_chat_model(
        self,
        metadata: dict,
    ) -> str:
        requested_model = metadata.get("model")

        if requested_model == settings.foundry_premium_chat_model:
            return settings.foundry_premium_chat_model

        if requested_model == settings.foundry_default_chat_model:
            return settings.foundry_default_chat_model

        return settings.foundry_default_chat_model