# HTTP client for the langup_ai inference gateway (Ollama on the mini-PC).
# Prompts/parsing do NOT live here — this only moves messages over the wire.
import httpx

from app.core import settings
from app.core.exc import AIProviderError


class AIClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.ai.AI_SERVICE_URL).rstrip("/")
        self.api_key = api_key or settings.ai.AI_SERVICE_API_KEY
        self.timeout = timeout or settings.ai.AI_SERVICE_TIMEOUT_SECONDS

    async def chat_json(self, system: str, user: str, temperature: float = 0.7) -> dict:
        """One-shot JSON-constrained completion; returns {"content": str, "model": str}."""
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "json_format": True,
            "temperature": temperature,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat",
                    json=payload,
                    headers={"X-API-Key": self.api_key},
                )
                resp.raise_for_status()
        except httpx.HTTPError as e:
            raise AIProviderError(f"AI service request failed: {e}") from e
        return resp.json()


def get_ai_client() -> AIClient:
    return AIClient()
