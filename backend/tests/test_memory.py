import asyncio
from datetime import date, datetime

from companion.memory import MemoryStore, Recall
from companion.remember import Memorizer, parse_memories

MONDAY = datetime(2026, 11, 9, 9, 0)
FRIDAY = datetime(2026, 11, 13, 18, 0)


def store_with(*items: tuple[str, str, date | None]) -> MemoryStore:
    store = MemoryStore(":memory:")
    for kind, text, on in items:
        store.add(kind, text, on, MONDAY)
    return store


def test_session_start_mentions_nearby_events_and_facts_but_not_distant_events():
    store = store_with(
        ("fact", "prefers tea over coffee", None),
        ("event", "has a big presentation at work", date(2026, 11, 12)),
        ("event", "is flying to Tokyo", date(2026, 12, 20)),
    )
    note = Recall(store).note_for("Hey, I am back.", FRIDAY)
    assert note is not None
    assert "presentation" in note and "1 days ago" not in note and "yesterday" in note
    assert "tea" in note
    assert "Tokyo" not in note
    assert "Friday 13 November" in note


def test_no_memories_means_no_note():
    assert Recall(MemoryStore(":memory:")).note_for("Hello", MONDAY) is None


def test_later_turns_only_bring_up_related_memories_and_not_too_often():
    store = store_with(("fact", "has a cat named Pixel", None), ("fact", "is learning Rust", None))
    recall = Recall(store)
    recall.note_for("hi", MONDAY)
    assert recall.note_for("what should I eat", MONDAY) is None
    assert recall.note_for("my rust code will not compile", MONDAY) is None, "too soon after the session note"
    assert recall.note_for("still fighting rust lifetimes", MONDAY) is None, "Rust came up at session start"
    note = recall.note_for("the cat is sitting on my keyboard again", MONDAY)
    assert note is None or "Pixel" in note


def test_a_related_memory_surfaces_once_the_cooldown_has_passed():
    store = store_with(("fact", "has a cat named Pixel", None))
    store.add("event", "has a dentist appointment", date(2026, 12, 1), MONDAY)
    recall = Recall(store, facts_at_start=0)
    assert recall.note_for("morning", MONDAY) is None
    for _ in range(2):
        recall.note_for("busy day", MONDAY)
    note = recall.note_for("my cat knocked over the plant", MONDAY)
    assert note is not None and "Pixel" in note
    assert recall.note_for("the cat is back on the table", MONDAY) is None, "same memory right away"


def test_parse_memories_keeps_valid_items_and_drops_the_rest():
    raw = """{"memories": [
        {"kind": "event", "text": "has a dentist appointment.", "date": "2026-11-12"},
        {"kind": "fact", "text": "prefers tea", "date": null},
        {"kind": "event", "text": "event without a date", "date": null},
        {"kind": "event", "text": "bad date", "date": "next week"},
        {"kind": "opinion", "text": "likes cats", "date": null},
        {"kind": "fact", "text": "", "date": null},
        "not an object"
    ]}"""
    assert parse_memories(raw) == [("event", "has a dentist appointment", date(2026, 11, 12)), ("fact", "prefers tea", None)]
    assert parse_memories("not json") == []
    assert parse_memories('{"memories": "nope"}') == []


class FakeLLM:
    def __init__(self, answer: str) -> None:
        self.answer, self.prompts = answer, []

    async def complete_json(self, messages, max_tokens=500):
        self.prompts.append(messages[0]["content"])
        return self.answer


def test_memorizer_stores_new_memories_and_skips_ones_it_already_has():
    store = store_with(("fact", "prefers tea over coffee", None))
    llm = FakeLLM('{"memories": [{"kind": "fact", "text": "prefers tea over coffee"}, {"kind": "event", "text": "has a presentation at work", "date": "2026-11-12"}]}')
    added = asyncio.run(Memorizer(llm, store, "Adam").remember([("I have a presentation Thursday", "[mood:neutral] Practice tonight.")], MONDAY))
    assert [(m.kind, m.text, m.on) for m in added] == [("event", "has a presentation at work", date(2026, 11, 12))]
    assert len(store.all()) == 2
    assert "Monday 2026-11-09" in llm.prompts[0] and "[mood:" not in llm.prompts[0]


def test_store_persists_to_disk_and_forgets(tmp_path):
    path = tmp_path / "memory.db"
    first = MemoryStore(path)
    kept = first.add("fact", "plays the cello", None, MONDAY)
    gone = first.add("fact", "dislikes mornings", None, MONDAY)
    assert first.forget(gone.id) and not first.forget(9999)
    assert [m.text for m in MemoryStore(path).all()] == [kept.text]


def test_a_past_event_is_followed_up_once_and_then_left_alone():
    store = store_with(("event", "has a big presentation at work", date(2026, 11, 12)))
    friday = Recall(store)
    note = friday.note_for("Hey", FRIDAY)
    assert note is not None and "you have not asked how it went" in note
    friday.heard("[mood:happy] You are back. How presentation go, question?", FRIDAY)
    saturday = datetime(2026, 11, 14, 10, 0)
    assert Recall(store).note_for("Morning", saturday) is None


def test_an_offered_memory_the_bot_did_not_mention_stays_available():
    store = store_with(("event", "has a big presentation at work", date(2026, 11, 12)))
    friday = Recall(store)
    assert friday.note_for("Hey", FRIDAY) is not None
    friday.heard("[mood:happy] Welcome back. Tea is warm.", FRIDAY)
    saturday = datetime(2026, 11, 14, 10, 0)
    assert "presentation" in (Recall(store).note_for("Morning", saturday) or "")


def test_follow_ups_come_before_upcoming_events():
    store = store_with(
        ("event", "sister is visiting", date(2026, 11, 14)),
        ("event", "has a big presentation at work", date(2026, 11, 12)),
    )
    note = Recall(store).note_for("Hey", FRIDAY)
    assert note.index("presentation") < note.index("sister")
