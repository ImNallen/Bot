import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime

from companion.config import Settings
from companion.llm import LLM, Message
from companion.memory import Recall
from companion.persona import example_messages, load_examples, system_prompt
from companion.reply import ReplyEvent, ReplyParser


@dataclass(frozen=True)
class Timed:
    seconds: float
    event: ReplyEvent


class Conversation:
    def __init__(self, llm: LLM, settings: Settings, recall: Recall | None = None, clock: Callable[[], datetime] = datetime.now) -> None:
        self.llm = llm
        self.settings = settings
        self.recall = recall
        self.clock = clock
        examples = load_examples()
        if settings.examples_as_turns:
            self.system, self.prefix = system_prompt(settings), example_messages(examples)
        else:
            self.system, self.prefix = system_prompt(settings, examples), []
        self.history: list[Message] = []
        self.exchanges: list[tuple[str, str]] = []
        self.last_raw = ""
        self.first_token_seconds: float | None = None
        self._user_text = ""
        self._user_content = ""

    async def prime(self) -> None:
        """Run the full persona prompt once so the first real reply does not pay first-request costs."""
        async for _ in self.llm.stream(self.messages("Hello."), max_tokens=1):
            pass

    def reset(self) -> None:
        self.history.clear()
        self.new_session()

    def new_session(self) -> None:
        """The next turn gets a fresh look at what the bot remembers, like greeting someone after a break."""
        if self.recall:
            self.recall = Recall(self.recall.store)

    def messages(self, user_content: str) -> list[Message]:
        return [{"role": "system", "content": self.system}, *self.prefix, *self.history, {"role": "user", "content": user_content}]

    async def reply(self, user_text: str) -> AsyncIterator[Timed]:
        start = time.perf_counter()
        parser = ReplyParser()
        note = self.recall.note_for(user_text, self.clock()) if self.recall else None
        self._user_text = user_text
        self._user_content = f"{note}\n\n{user_text}" if note else user_text
        self.last_raw = ""
        self.first_token_seconds = None
        async for chunk in self.llm.stream(self.messages(self._user_content)):
            if self.first_token_seconds is None:
                self.first_token_seconds = time.perf_counter() - start
            self.last_raw += chunk
            for event in parser.feed(chunk):
                yield Timed(time.perf_counter() - start, event)
        for event in parser.finish():
            yield Timed(time.perf_counter() - start, event)
        self._commit(self.last_raw)

    def interrupted(self, heard: str) -> None:
        """Keep an interrupted turn with only the part the human actually heard."""
        self._commit(heard)

    def _commit(self, reply: str) -> None:
        # History keeps the message exactly as sent, memory note included, so the prompt only grows by appending.
        self.history += [{"role": "user", "content": self._user_content}, {"role": "assistant", "content": reply}]
        self.exchanges.append((self._user_text, reply))
        if self.recall:
            self.recall.heard(reply, self.clock())
        self._trim()

    def _trim(self) -> None:
        # The model's prompt cache survives only while the prompt grows by appending.
        # Dropping half the history at once costs one cold turn instead of one every turn.
        limit = 2 * self.settings.history_turns
        if len(self.history) > limit:
            self.history = self.history[-limit // 2 :]
