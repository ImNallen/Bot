import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from companion.config import Settings
from companion.llm import LLM, Message
from companion.persona import example_messages, load_examples, system_prompt
from companion.reply import ReplyEvent, ReplyParser


@dataclass(frozen=True)
class Timed:
    seconds: float
    event: ReplyEvent


class Conversation:
    def __init__(self, llm: LLM, settings: Settings) -> None:
        self.llm = llm
        self.settings = settings
        examples = load_examples()
        if settings.examples_as_turns:
            self.system, self.prefix = system_prompt(settings), example_messages(examples)
        else:
            self.system, self.prefix = system_prompt(settings, examples), []
        self.history: list[Message] = []
        self.last_raw = ""
        self.first_token_seconds: float | None = None

    async def prime(self) -> None:
        """Run the full persona prompt once so the first real reply does not pay first-request costs."""
        async for _ in self.llm.stream(self.messages("Hello."), max_tokens=1):
            pass

    def reset(self) -> None:
        self.history.clear()

    def messages(self, user_text: str) -> list[Message]:
        return [{"role": "system", "content": self.system}, *self.prefix, *self.history, {"role": "user", "content": user_text}]

    def _trim(self) -> None:
        # The model's prompt cache survives only while the prompt grows by appending.
        # Dropping half the history at once costs one cold turn instead of one every turn.
        limit = 2 * self.settings.history_turns
        if len(self.history) > limit:
            self.history = self.history[-limit // 2 :]

    async def reply(self, user_text: str) -> AsyncIterator[Timed]:
        start = time.perf_counter()
        parser = ReplyParser()
        self.last_raw = ""
        self.first_token_seconds = None
        async for chunk in self.llm.stream(self.messages(user_text)):
            if self.first_token_seconds is None:
                self.first_token_seconds = time.perf_counter() - start
            self.last_raw += chunk
            for event in parser.feed(chunk):
                yield Timed(time.perf_counter() - start, event)
        for event in parser.finish():
            yield Timed(time.perf_counter() - start, event)
        self.record(user_text, self.last_raw)

    def record(self, user_text: str, reply: str) -> None:
        """Add a finished exchange. An interrupted reply is recorded by the caller with only what was said."""
        self.history += [{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}]
        self._trim()
