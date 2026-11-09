"""Two sessions with the real model: tell it things on Monday, come back on Friday.

Checks that the right memories are saved with absolute dates, that Friday's greeting brings up the
presentation without reading the note aloud, and that unrelated turns carry no memory note.
Uses a throwaway memory file, never your real one.

Usage: uv run python evals/memory_eval.py [--trials 3]
"""

import argparse
import asyncio
import shutil
import tempfile
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from companion.config import Settings
from companion.conversation import Conversation
from companion.llm import LLM
from companion.memory import MemoryStore, Recall
from companion.remember import Memorizer
from companion.reply import SentenceEvent

MONDAY = datetime(2026, 11, 9, 9, 30)
FRIDAY = datetime(2026, 11, 13, 18, 15)
MONDAY_TALK = [
    "I have a big presentation at work on Thursday and I'm kind of nervous about it.",
    "My sister Lena is coming to visit next weekend.",
    "Also, I switched from coffee to tea this month.",
]


async def say(convo: Conversation, text: str) -> str:
    return " ".join([t.event.text async for t in convo.reply(text) if isinstance(t.event, SentenceEvent)])


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3)
    args = ap.parse_args()
    settings = replace(Settings.from_env(), user="Adam")
    llm = LLM(settings)
    store_path = Path(tempfile.mkdtemp()) / "memory.db"
    store = MemoryStore(store_path)

    print("--- Monday")
    monday = Conversation(llm, settings, recall=Recall(store), clock=lambda: MONDAY)
    for line in MONDAY_TALK:
        print(f"you › {line}\nbot › {await say(monday, line)}")
    added = await Memorizer(llm, store, settings.user).remember(monday.exchanges, MONDAY)
    print("\nremembered:")
    for m in added:
        print(f"  {m.kind:<5} {m.text}{'  · ' + str(m.on) if m.on else ''}")
    presentation = [m for m in added if m.kind == "event" and "present" in m.text.lower()]
    print(f"\npresentation saved as an event on Thursday 2026-11-12: {bool(presentation) and presentation[0].on == date(2026, 11, 12)}")
    print(f"tea saved as a fact: {any(m.kind == 'fact' and 'tea' in m.text.lower() for m in added)}")

    print("\n--- Friday evening, fresh session (each trial starts from its own copy of Monday's memories)")
    mentioned = 0
    for trial in range(args.trials):
        copy = Path(tempfile.mkdtemp()) / "memory.db"
        shutil.copy(store_path, copy)
        friday = Conversation(llm, settings, recall=Recall(MemoryStore(copy)), clock=lambda: FRIDAY)
        greeting = await say(friday, "Hey, I'm back.")
        leaked = any(w in greeting.lower() for w in ("memory note", "you remember", "note says"))
        hit = "present" in greeting.lower()
        mentioned += hit
        print(f"bot › {greeting}   [{'mentions presentation' if hit else 'no mention'}{', LEAKED NOTE' if leaked else ''}]")
        if trial == 0:
            later = ["What should I cook tonight?", "Maybe pasta. Any tips?"]
            for line in later:
                reply = await say(friday, line)
                carried = friday.history[-2]["content"].startswith("(Memory note")
                print(f"  you › {line}\n  bot › {reply}   [{'memory note attached' if carried else 'no note'}]")
    print(f"\nFriday greeting brought up the presentation in {mentioned}/{args.trials} trials")


if __name__ == "__main__":
    asyncio.run(main())
