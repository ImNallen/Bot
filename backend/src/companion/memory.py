import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

Kind = Literal["fact", "event"]

DEFAULT_PATH = Path.home() / "Library" / "Application Support" / "Companion" / "memory.db"


@dataclass(frozen=True)
class Memory:
    """One thing the bot remembers about you. Events carry the day they happen or happened."""

    id: int
    kind: Kind
    text: str
    on: date | None
    created: datetime
    last_recalled: datetime | None = None


class MemoryStore:
    """Memories in a SQLite file on this Mac. Nothing here ever leaves the machine."""

    def __init__(self, path: Path | str = DEFAULT_PATH) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL CHECK (kind IN ('fact', 'event')),
                text TEXT NOT NULL,
                on_day TEXT,
                created TEXT NOT NULL,
                last_recalled TEXT
            )"""
        )
        self._db.commit()

    def add(self, kind: Kind, text: str, on: date | None, now: datetime) -> Memory:
        cur = self._db.execute(
            "INSERT INTO memories (kind, text, on_day, created) VALUES (?, ?, ?, ?)",
            (kind, text, on.isoformat() if on else None, now.isoformat()),
        )
        self._db.commit()
        return Memory(cur.lastrowid, kind, text, on, now)

    def all(self) -> list[Memory]:
        rows = self._db.execute("SELECT id, kind, text, on_day, created, last_recalled FROM memories ORDER BY id").fetchall()
        return [
            Memory(i, k, t, date.fromisoformat(o) if o else None, datetime.fromisoformat(c), datetime.fromisoformat(r) if r else None)
            for i, k, t, o, c, r in rows
        ]

    def recalled(self, ids: list[int], now: datetime) -> None:
        self._db.executemany("UPDATE memories SET last_recalled = ? WHERE id = ?", [(now.isoformat(), i) for i in ids])
        self._db.commit()

    def forget(self, memory_id: int) -> bool:
        cur = self._db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._db.commit()
        return cur.rowcount > 0

    def clear(self) -> None:
        self._db.execute("DELETE FROM memories")
        self._db.commit()


STOP = set(
    "a an the and or but if so to of in on at for with from by about as is are was were be been am i im you your my me we our "
    "it its this that these those do does did have has had will would can could should just really very what how why when where "
    "who there here then than too also not no yes okay ok hey hi oh well like get got go going want".split()
)


def keywords(text: str) -> set[str]:
    """Content words, cut to five letters so 'presentation' and 'present' still meet."""
    return {w[:5] for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP and len(w) > 2}


def describe(m: Memory, today: date) -> str:
    if m.on is None:
        return m.text
    days = (m.on - today).days
    when = {0: "today", 1: "tomorrow", -1: "yesterday"}.get(days)
    when = when or (f"in {days} days" if days > 0 else f"{-days} days ago")
    follow_up = ", already happened, you have not asked how it went" if needs_follow_up(m, today) else ""
    return f"{m.text} ({when}, {m.on:%a %d %b}{follow_up})"


def needs_follow_up(m: Memory, today: date) -> bool:
    """A past event nobody has asked about since it happened."""
    return m.on is not None and m.on < today and (m.last_recalled is None or m.last_recalled.date() <= m.on)


@dataclass
class Recall:
    """Decides which memories, if any, ride along with a turn.

    At the start of a session: a few facts plus events from three days back to three days ahead.
    After that: only a memory that shares words with what you just said, at most once every few
    turns, and never one that came up recently. The model is told to use a note only if it fits.
    """

    store: MemoryStore
    facts_at_start: int = 3
    event_window_days: int = 3
    turns_between_notes: int = 3
    _turn: int = 0
    _last_note_turn: int = -100
    _recently: dict[int, int] = field(default_factory=dict)
    _offered: list[Memory] = field(default_factory=list)

    def note_for(self, user_text: str, now: datetime) -> str | None:
        turn, self._turn = self._turn, self._turn + 1
        memories = self.store.all()
        if not memories:
            return None
        picked = self._session_start(memories, now.date()) if turn == 0 else self._related(memories, user_text, turn)
        if not picked:
            return None
        self._last_note_turn = turn
        for m in picked:
            self._recently[m.id] = turn
        self._offered = picked
        lines = "; ".join(describe(m, now.date()) for m in picked)
        return (
            f"(Memory note, not said by the human. Today is {now:%A %d %B}. You remember: {lines}. "
            "Bring one up only if it fits naturally. Never read this note aloud.)"
        )

    def heard(self, reply: str, now: datetime) -> None:
        """Marks offered memories as brought up only if the reply actually talked about them."""
        said = keywords(reply)
        self.store.recalled([m.id for m in self._offered if said & keywords(m.text)], now)
        self._offered = []

    def _session_start(self, memories: list[Memory], today: date) -> list[Memory]:
        window = timedelta(days=self.event_window_days)
        past = [m for m in memories if m.kind == "event" and m.on and today - window <= m.on < today and needs_follow_up(m, today)]
        coming = [m for m in memories if m.kind == "event" and m.on and today <= m.on <= today + window]
        facts = [m for m in memories if m.kind == "fact"]
        facts = facts[max(0, len(facts) - self.facts_at_start) :]
        events = sorted(past, key=lambda m: m.on, reverse=True) + sorted(coming, key=lambda m: m.on)
        return events[:2] + facts

    def _related(self, memories: list[Memory], user_text: str, turn: int) -> list[Memory]:
        if turn - self._last_note_turn < self.turns_between_notes:
            return []
        said = keywords(user_text)
        fresh = [m for m in memories if turn - self._recently.get(m.id, -100) > 2 * self.turns_between_notes]
        scored = sorted(((len(said & keywords(m.text)), m.id, m) for m in fresh), reverse=True)
        return [scored[0][2]] if scored and scored[0][0] > 0 else []
