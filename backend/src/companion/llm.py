from collections.abc import AsyncIterator

import httpx
from openai import AsyncOpenAI

from companion.config import Settings

Message = dict[str, str]


class LLM:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(base_url=settings.base_url, api_key=settings.api_key)

    async def stream(self, messages: list[Message], max_tokens: int | None = None) -> AsyncIterator[str]:
        s = self.settings
        response = await self.client.chat.completions.create(
            model=s.model,
            messages=messages,
            stream=True,
            temperature=s.temperature,
            max_tokens=max_tokens or s.max_tokens,
            extra_body={"reasoning_effort": s.reasoning_effort},
        )
        try:
            async for chunk in response:
                if chunk.choices and (delta := chunk.choices[0].delta.content):
                    yield delta
        finally:
            # Closing the connection is what tells Ollama to stop generating an abandoned reply.
            await response.close()

    async def warm(self) -> None:
        """Load the model and keep it resident so the first reply skips the cold start.

        Uses Ollama's native API because the OpenAI-compatible endpoint has no keep_alive.
        Other providers simply skip this.
        """
        root = self.settings.base_url.removesuffix("/v1")
        async with httpx.AsyncClient(timeout=300) as http:
            try:
                await http.post(f"{root}/api/generate", json={"model": self.settings.model, "keep_alive": -1})
            except httpx.HTTPError:
                pass
