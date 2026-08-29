# HTTP client for the langup_ai inference gateway (llama.cpp + Gemma on the mini-PC iGPU).
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

    async def speak(self, text: str, language: str, voice: str | None = None) -> tuple[bytes, str]:
        """Synthesize `text`; returns (WAV bytes, the voice that spoke it).

        The gateway holds no cache — it re-synthesizes whatever it is asked
        for — so callers must only reach this on a cache miss.
        """
        payload: dict = {"text": text, "language": language}
        if voice:
            payload["voice"] = voice
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/tts",
                    json=payload,
                    headers={"X-API-Key": self.api_key},
                )
                resp.raise_for_status()
        except httpx.HTTPError as e:
            raise AIProviderError(f"TTS request failed: {e}") from e
        # The gateway reports the voice it actually used, which matters when we
        # did not name one: the cache key is built from the resolved voice.
        return resp.content, resp.headers.get("X-Voice", voice or "")


def get_ai_client() -> AIClient:
    return AIClient()
