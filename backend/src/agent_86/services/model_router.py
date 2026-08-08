from agent_86.core.config import Settings


class ModelRouter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def choose_chat_model(
        self,
        metadata: dict,
    ) -> str:
        requested_model = metadata.get("model")

        if requested_model == self._settings.foundry_premium_chat_model:
            return self._settings.foundry_premium_chat_model

        if requested_model == self._settings.foundry_default_chat_model:
            return self._settings.foundry_default_chat_model

        return self._settings.foundry_default_chat_model