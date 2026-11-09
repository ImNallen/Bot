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
        raw: list[str] = []
        self.first_token_seconds = None
        try:
            async for chunk in self.llm.stream(self.messages(user_text)):
                if self.first_token_seconds is None:
                    self.first_token_seconds = time.perf_counter() - start
                raw.append(chunk)
                for event in parser.feed(chunk):
                    yield Timed(time.perf_counter() - start, event)
            for event in parser.finish():
                yield Timed(time.perf_counter() - start, event)
        finally:
            self.last_raw = "".join(raw)
            self.history += [{"role": "user", "content": user_text}, {"role": "assistant", "content": self.last_raw}]
            self._trim()
