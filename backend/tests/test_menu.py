import asyncio
import json
from datetime import date, datetime, timedelta

from companion.config import Settings, read_saved, write_saved
from companion.control import Control
from companion.memory import MemoryStore
from companion.prefs import menu_prefs, to_settings
from companion.stats import TurnRecord, summarize
from companion.voice import Models, VoiceLoop

TODAY = date(2026, 11, 10)


def test_menu_values_map_to_settings_and_bad_values_are_refused():
    assert to_settings("sensitivity", 0.5) == {"vad_threshold": 0.5}
    assert to_settings("sensitivity", 1) == {"vad_threshold": 0.2}
    assert to_settings("pause", 0.8) == {"reply_gap_ms": 800}
    assert to_settings("thinking", True) == {"reasoning_effort": "medium"}
    assert to_settings("interrupt", False) == {"barge_in": False}
    assert to_settings("mic", None) == {"mic": None}
    for key, value in [("speed", 5), ("speed", True), ("voice", "zz_robot"), ("pause", "long"), ("thinking", 1), ("base_url", "http://evil")]:
        assert to_settings(key, value) is None, (key, value)
    assert menu_prefs(Settings())["sensitivity"] == 0.5


def test_saved_preferences_load_under_the_environment_and_junk_is_dropped(tmp_path, monkeypatch):
    path = tmp_path / "preferences.json"
    write_saved(Settings(voice="bm_george", mic="Wave:3", preferences_path=str(path)))
    assert read_saved(path)["voice"] == "bm_george"
    path.write_text(json.dumps({"voice": 3, "speech_speed": 1, "base_url": "http://elsewhere", "mic": "Wave:3"}))
    assert read_saved(path) == {"speech_speed": 1.0, "mic": "Wave:3"}
    monkeypatch.setenv("COMPANION_MIC", "MacBook")
    assert Settings.from_env(read_saved(path)).mic == "MacBook"
    (tmp_path / "broken.json").write_text("{nope")
    assert read_saved(tmp_path / "broken.json") == {}


def turn(at: datetime, mood="happy", latency=0.9, interrupted=False, said="hello", reply="Hello. Good, question?"):
    return TurnRecord(at, mood, latency, interrupted, said, reply, 2.0, 3.0)


def test_stats_summary():
    start = datetime(2026, 10, 18, 21, 0)
    turns = [
        turn(start, said="coffee time"),
        turn(start + timedelta(minutes=2), said="more coffee please", interrupted=True),
        turn(start + timedelta(minutes=30), mood="sad", latency=0.7, said="coffee again"),
        turn(datetime(2026, 11, 9, 9, 0), mood="sad", latency=1.1),
        turn(datetime(2026, 11, 10, 21, 30)),
    ]
    s = summarize(turns, TODAY)
    assert s["since"] == "2026-10-18" and s["conversations"] == 4 and s["interruptions"] == 1
    assert s["replyStart"] == 0.9 and s["talkingSeconds"] == 25 and s["cloudBytes"] == 0
    assert sorted(s["moods"], key=lambda m: m["mood"]) == [{"mood": "happy", "share": 0.5}, {"mood": "sad", "share": 0.5}]
    assert s["perDay"][-2:] == [1, 1] and len(s["perDay"]) == 14
    assert s["favoriteWord"] == "coffee" and s["saidQuestion"] == 5 and s["chattyHour"] == 21
    assert s["longestChatSeconds"] == 125
    empty = summarize([], TODAY)
    assert empty["since"] is None and empty["replyStart"] is None and empty["favoriteWord"] is None


class FakeLLM:
    def __init__(self) -> None:
        self.warmed: list[str] = []

    async def models(self):
        return {"installed": [{"name": "qwen3.6:35b-a3b-q8_0"}, {"name": "qwen3.6:27b"}]}

    async def warm(self, model=None):
        self.warmed.append("warm")

    async def unload(self, model):
        self.warmed.append(f"unload {model}")


class FakeConvo:
    exchanges: list = []

    def __init__(self) -> None:
        self.llm, self.primed = FakeLLM(), 0

    async def prime(self):
        self.primed += 1

    def new_session(self):
        pass


class FakeMemorizer:
    def __init__(self) -> None:
        self.store = MemoryStore(":memory:")


class QuietIO:
    level, playing = 0.0, False

    def now(self) -> float:
        return 0.0

    def stop(self) -> None:
        pass


def menu(mic_error: Exception | None = None):
    events, saved, mics = [], [], []

    def use_mic(name):
        if mic_error:
            raise mic_error
        mics.append(name)

    convo, memorizer = FakeConvo(), FakeMemorizer()
    loop = VoiceLoop(QuietIO(), Models(convo, None, None, None, memorizer), Settings(), publish=events.append, verbose=False)
    control = Control(loop, convo, use_mic, microphones=lambda: [{"name": "Wave:3", "detail": "", "default": False}], save=saved.append, today=lambda: TODAY)
    return control, loop, events, saved, mics


def test_a_menu_change_applies_live_saves_and_publishes_status():
    control, loop, events, saved, mics = menu()

    async def scenario():
        await control.handle({"type": "set", "key": "sensitivity", "value": 1})
        await control.handle({"type": "set", "key": "mic", "value": "Wave:3"})
        await control.handle({"type": "set", "key": "speed", "value": 9})
        await control.handle({"type": "set", "key": "model", "value": "qwen3.6:27b"})
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(scenario())
    assert loop._segmenter.threshold == 0.2 and mics == ["Wave:3"] and loop.settings.mic == "Wave:3"
    assert len(saved) == 3, "the out-of-range speed changed nothing"
    assert events[-1]["type"] in ("status", "models")
    status = [e for e in events if e["type"] == "status"][-1]
    assert status["model"] == "qwen3.6:27b" and status["prefs"]["sensitivity"] == 1.0
    assert control.llm.warmed[0] == "unload qwen3.6:35b-a3b-q8_0" and control.convo.primed == 1


def test_a_failed_mic_switch_or_unknown_model_leaves_settings_alone():
    control, loop, _, saved, _ = menu(mic_error=OSError("device busy"))
    notice = asyncio.run(control.handle({"type": "set", "key": "mic", "value": "AirPods"}))
    assert notice == {"type": "notice", "text": "Could not switch microphones: device busy"}
    notice = asyncio.run(control.handle({"type": "set", "key": "model", "value": "llama-forever"}))
    assert "not installed" in notice["text"]
    assert loop.settings.mic is None and loop.settings.model == Settings().model and saved == []


def test_memories_page_lists_and_forgets():
    control, loop, events, _, _ = menu()
    store = loop.memorizer.store
    kept = store.add("fact", "plays the cello", None, datetime(2026, 11, 1))
    gone = store.add("event", "had a dentist appointment", date(2026, 11, 8), datetime(2026, 11, 2))
    page = asyncio.run(control.handle({"type": "get", "what": "memories"}))
    assert page["on"] and [m["followUp"] for m in page["items"]] == [False, True]
    page = asyncio.run(control.handle({"type": "forget", "id": gone.id}))
    assert [m["id"] for m in page["items"]] == [kept.id] and events[-1]["memories"] == 1
    page = asyncio.run(control.handle({"type": "forget", "id": None}))
    assert page["items"] == []
