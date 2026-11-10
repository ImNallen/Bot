import re
import sqlite3
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from companion.memory import STOP

CONVERSATION_GAP = timedelta(minutes=10)


@dataclass(frozen=True)
class TurnRecord:
    """One finished voice exchange, kept only to show fun numbers in the menu."""

    at: datetime
    mood: str
    latency: float | None
    interrupted: bool
    user_text: str
    reply: str
    user_seconds: float
    bot_seconds: float


class StatsStore:
    """Turn records in a SQLite file on this Mac, next to the memories."""

    def __init__(self, path: Path | str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS turns (
                at TEXT NOT NULL, mood TEXT NOT NULL, latency REAL, interrupted INTEGER NOT NULL,
                user_text TEXT NOT NULL, reply TEXT NOT NULL, user_seconds REAL NOT NULL, bot_seconds REAL NOT NULL
            )"""
        )
        self._db.commit()

    def add(self, r: TurnRecord) -> None:
        self._db.execute(
            "INSERT INTO turns VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (r.at.isoformat(), r.mood, r.latency, int(r.interrupted), r.user_text, r.reply, r.user_seconds, r.bot_seconds),
        )
        self._db.commit()

    def all(self) -> list[TurnRecord]:
        rows = self._db.execute("SELECT * FROM turns ORDER BY at").fetchall()
        return [TurnRecord(datetime.fromisoformat(a), m, lat, bool(i), u, r, us, bs) for a, m, lat, i, u, r, us, bs in rows]


def conversations(turns: list[TurnRecord]) -> list[list[TurnRecord]]:
    """Turns grouped into conversations: a quiet gap of ten minutes starts a new one."""
    groups: list[list[TurnRecord]] = []
    for t in turns:
        if groups and t.at - groups[-1][-1].at <= CONVERSATION_GAP:
            groups[-1].append(t)
        else:
            groups.append([t])
    return groups


def favorite_word(texts: list[str]) -> str | None:
    counts = Counter(w for text in texts for w in re.findall(r"[a-z']+", text.lower()) if len(w) > 3 and w not in STOP)
    word, n = counts.most_common(1)[0] if counts else (None, 0)
    return word if n >= 3 else None


def summarize(turns: list[TurnRecord], today: date) -> dict:
    """Everything the Stats page shows, worked out from the raw turn records."""
    chats = conversations(turns)
    week = [t for t in turns if (today - t.at.date()).days < 7]
    moods = Counter(t.mood for t in week)
    latencies = [t.latency for t in turns[-200:] if t.latency is not None]
    per_day = Counter(t.at.date() for t in turns)
    hours = Counter(t.at.hour for t in turns)
    return {
        "since": turns[0].at.date().isoformat() if turns else None,
        "talkingSeconds": round(sum(t.user_seconds + t.bot_seconds for t in turns)),
        "conversations": len(chats),
        "interruptions": sum(t.interrupted for t in turns),
        "replyStart": round(statistics.median(latencies), 2) if latencies else None,
        "cloudBytes": 0,
        "moods": [{"mood": mood, "share": round(n / len(week), 3)} for mood, n in moods.most_common(5)],
        "perDay": [per_day.get(today - timedelta(days=d), 0) for d in range(13, -1, -1)],
        "favoriteWord": favorite_word([t.user_text for t in turns]),
        "saidQuestion": sum(len(re.findall(r"\bquestion\b", t.reply.lower())) for t in turns),
        "chattyHour": hours.most_common(1)[0][0] if hours else None,
        "longestChatSeconds": round(max((length(c) for c in chats), default=0)),
    }


def length(chat: list[TurnRecord]) -> float:
    first = chat[0]
    return (chat[-1].at - first.at).total_seconds() + first.user_seconds + first.bot_seconds
