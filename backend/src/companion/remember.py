import json
import re
from datetime import date, datetime

from companion.config import Settings
from companion.conversation import Conversation
from companion.llm import LLM
from companion.memory import Kind, Memory, MemoryStore, Recall, describe, keywords

PROMPT = """You keep a small memory about {user} for their companion, who lives on their computer.
Read the conversation and list only new things worth remembering weeks from now.

Today is {today:%A %Y-%m-%d}.

Keep:
- lasting facts about {user}: work, projects, people and pets in their life, likes and dislikes, habits, health, goals
- dated events: appointments, plans, deadlines, trips, things that happened to them

Skip small talk, anything only the companion said, guesses, and anything already in the existing memories.
Write each memory as a short phrase about {user} in the third person, without their name.
Give every event an absolute date resolved from today, as YYYY-MM-DD. Facts have no date.

Existing memories:
{existing}

Conversation:
{transcript}

Answer with JSON only, like {{"memories": [{{"kind": "event", "text": "has a dentist appointment", "date": "2026-11-12"}}]}}.
Answer {{"memories": []}} when there is nothing new."""

TAG = re.compile(r"^\s*\[mood:[a-z]+\]\s*", re.IGNORECASE)


def parse_memories(raw: str) -> list[tuple[Kind, str, date | None]]:
    """Reads the model's JSON. Anything malformed is dropped rather than half-trusted."""
    try:
        items = json.loads(raw).get("memories", [])
    except (json.JSONDecodeError, AttributeError):
        return []
    found: list[tuple[Kind, str, date | None]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        kind, text, day = item.get("kind"), item.get("text"), item.get("date")
        if kind not in ("fact", "event") or not isinstance(text, str) or not 3 <= len(text.strip()) <= 160:
            continue
        on = None
        if kind == "event":
            try:
                on = date.fromisoformat(day) if isinstance(day, str) else None
            except ValueError:
                on = None
            if on is None:
                continue
        found.append((kind, text.strip().rstrip("."), on))
    return found


def is_duplicate(text: str, on: date | None, known: list[Memory]) -> bool:
    words = keywords(text)
    for m in known:
        if m.on != on:
            continue
        overlap = len(words & keywords(m.text)) / max(1, len(words | keywords(m.text)))
        if m.text.lower() == text.lower() or overlap >= 0.6:
            return True
    return False


class Memorizer:
    """Turns finished exchanges into memories with one extra model call, run while the conversation is quiet."""

    def __init__(self, llm: LLM, store: MemoryStore, user: str) -> None:
        self.llm, self.store, self.user = llm, store, user

    async def remember(self, exchanges: list[tuple[str, str]], now: datetime) -> list[Memory]:
        if not exchanges:
            return []
        known = self.store.all()
        transcript = "\n".join(f"{self.user}: {said}\nCompanion: {TAG.sub('', reply)}" for said, reply in exchanges)
        existing = "\n".join(f"- {describe(m, now.date())}" for m in known) or "(none yet)"
        prompt = PROMPT.format(user=self.user, today=now, existing=existing, transcript=transcript)
        raw = await self.llm.complete_json([{"role": "user", "content": prompt}])
        added: list[Memory] = []
        for kind, text, on in parse_memories(raw):
            if not is_duplicate(text, on, known + added):
                added.append(self.store.add(kind, text, on, now))
        return added


def with_memory(llm: LLM, settings: Settings) -> tuple[Conversation, Memorizer | None]:
    """A conversation that recalls memories, plus the memorizer that saves new ones, when memory is on."""
    if not settings.remember:
        return Conversation(llm, settings), None
    store = MemoryStore(settings.memory_path)
    return Conversation(llm, settings, recall=Recall(store)), Memorizer(llm, store, settings.user)
