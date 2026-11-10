from collections.abc import AsyncIterator

import httpx
from openai import AsyncOpenAI

from companion.config import Settings

Message = dict[str, str]

# Thinking tokens count against the reply's budget, so a thinking model gets room for them on top.
THINKING_BUDGET = 1500


class LLM:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(base_url=settings.base_url, api_key=settings.api_key)

    async def stream(self, messages: list[Message], max_tokens: int | None = None) -> AsyncIterator[str]:
        s = self.settings
        budget = max_tokens or s.max_tokens
        if s.reasoning_effort != "none" and budget > 1:
            budget += THINKING_BUDGET
        response = await self.client.chat.completions.create(
            model=s.model,
            messages=messages,
            stream=True,
            temperature=s.temperature,
            max_tokens=budget,
            extra_body={"reasoning_effort": s.reasoning_effort},
        )
        try:
            async for chunk in response:
                if chunk.choices and (delta := chunk.choices[0].delta.content):
                    yield delta
        finally:
            # Closing the connection is what tells Ollama to stop generating an abandoned reply.
            await response.close()

    async def complete_json(self, messages: list[Message], max_tokens: int = 500) -> str:
        """One non-streamed answer constrained to JSON, for background jobs like saving memories."""
        response = await self.client.chat.completions.create(
            model=self.settings.model,
            messages=messages,
            temperature=0.2,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            extra_body={"reasoning_effort": self.settings.reasoning_effort},
        )
        return response.choices[0].message.content or ""

    @property
    def server(self) -> str:
        return self.settings.base_url.removesuffix("/v1")

    async def warm(self, model: str | None = None) -> None:
        """Load the model, and with `keep_loaded` keep it resident so no reply pays for a cold start.

        Uses Ollama's native API because the OpenAI-compatible endpoint has no keep_alive.
        Other providers simply skip this.
        """
        await self._keep_alive(model or self.settings.model, -1 if self.settings.keep_loaded else "5m", timeout=300)

    async def unload(self, model: str) -> None:
        """Free the memory a model holds, for example the old one after switching."""
        await self._keep_alive(model, 0, timeout=30)

    async def _keep_alive(self, model: str, keep_alive: int | str, timeout: float) -> None:
        async with httpx.AsyncClient(timeout=timeout) as http:
            try:
                await http.post(f"{self.server}/api/generate", json={"model": model, "keep_alive": keep_alive})
            except httpx.HTTPError:
                pass

    async def models(self) -> dict:
        """Ollama's version and the chat models it has, with which are in memory right now."""
        async with httpx.AsyncClient(timeout=5) as http:
            try:
                version = (await http.get(f"{self.server}/api/version")).json()["version"]
                tags = (await http.get(f"{self.server}/api/tags")).json()["models"]
                loaded = {m["name"] for m in (await http.get(f"{self.server}/api/ps")).json()["models"]}
                shows = [await http.post(f"{self.server}/api/show", json={"model": m["name"]}) for m in tags]
            except (httpx.HTTPError, KeyError, ValueError):
                return {"server": self.server, "running": False, "version": None, "installed": []}
        installed = [
            {
                "name": m["name"],
                "size": m.get("size", 0),
                "quantization": m.get("details", {}).get("quantization_level", ""),
                "loaded": m["name"] in loaded,
            }
            for m, show in zip(tags, shows, strict=True)
            if "completion" in show.json().get("capabilities", ["completion"])
        ]
        return {"server": self.server, "running": True, "version": version, "installed": installed}
