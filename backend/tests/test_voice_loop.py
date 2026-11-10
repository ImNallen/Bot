import asyncio
import time

from companion.config import Settings
from companion.vad import SpeechStarted
from companion.voice import Models, State, VoiceLoop


class FakeConversation:
    def __init__(self) -> None:
        self.exchanges: list = []
        self.sessions = 0

    def new_session(self) -> None:
        self.sessions += 1


class QuietIO:
    level = 0.0
    playing = False

    def now(self) -> float:
        return time.monotonic()

    def stop(self) -> None:
        pass


def test_muting_ignores_speech_and_reports_status():
    events: list[dict] = []
    loop = VoiceLoop(QuietIO(), Models(FakeConversation(), None, None, None), Settings(), publish=events.append, verbose=False)
    loop.command("mute")
    loop._on_vad(SpeechStarted())
    assert loop.state is State.IDLE
    loop.command("unmute")
    loop._on_vad(SpeechStarted())
    assert loop.state is State.LISTENING
    assert [e["micOn"] for e in events if e["type"] == "status"] == [False, True]


def test_sleep_command_dozes_off_at_once():
    loop = VoiceLoop(QuietIO(), Models(FakeConversation(), None, None, None), Settings(), verbose=False)
    loop.command("sleep")
    assert loop.state is State.SLEEPING


def test_dozes_off_after_idle_and_wakes_when_spoken_to():
    events: list[dict] = []
    convo = FakeConversation()

    async def scenario() -> State:
        loop = VoiceLoop(QuietIO(), Models(convo, None, None, None), Settings(sleep_after_s=0.1), publish=events.append, verbose=False)
        reporter = asyncio.create_task(loop._report_levels())
        await asyncio.sleep(0.3)
        asleep = loop.state
        loop._on_vad(SpeechStarted())
        reporter.cancel()
        assert asleep is State.SLEEPING
        return loop.state

    assert asyncio.run(scenario()) is State.LISTENING
    assert [e["state"] for e in events if e["type"] == "state"] == ["sleeping", "listening"]
    assert sum(e["type"] == "levels" for e in events) >= 5
    assert convo.sessions == 1, "dozing off starts a new memory session for the next greeting"


class SlowMemorizer:
    def __init__(self, delay: float) -> None:
        self.delay, self.batches = delay, []

    async def remember(self, exchanges, now):
        await asyncio.sleep(self.delay)
        self.batches.append(list(exchanges))
        return []


def run_quietly(memorizer, speak_after: float | None) -> FakeConversation:
    convo = FakeConversation()
    convo.exchanges = [("I have a dentist appointment Friday", "[mood:neutral] Teeth important.")]

    async def scenario():
        settings = Settings(memory_idle_s=0.1, sleep_after_s=60)
        loop = VoiceLoop(QuietIO(), Models(convo, None, None, None, memorizer), settings, verbose=False)
        reporter = asyncio.create_task(loop._report_levels())
        if speak_after is not None:
            await asyncio.sleep(speak_after)
            loop._on_vad(SpeechStarted())
        await asyncio.sleep(0.5)
        reporter.cancel()

    asyncio.run(scenario())
    return convo


def test_saves_memories_after_a_quiet_spell_and_clears_what_it_saved():
    memorizer = SlowMemorizer(delay=0.01)
    convo = run_quietly(memorizer, speak_after=None)
    assert len(memorizer.batches) == 1
    assert convo.exchanges == []


def test_talking_cancels_saving_and_keeps_the_turns_for_later():
    memorizer = SlowMemorizer(delay=5)
    convo = run_quietly(memorizer, speak_after=0.2)
    assert memorizer.batches == []
    assert len(convo.exchanges) == 1


def test_with_interrupting_off_speech_over_the_bot_is_ignored():
    loop = VoiceLoop(QuietIO(), Models(FakeConversation(), None, None, None), Settings(barge_in=False), verbose=False)
    loop.state = State.SPEAKING
    loop._on_vad(SpeechStarted())
    assert loop.state is State.SPEAKING


def test_with_learning_off_nothing_new_is_saved():
    memorizer = SlowMemorizer(delay=0.01)
    convo = FakeConversation()
    convo.exchanges = [("I have a dentist appointment Friday", "[mood:neutral] Teeth important.")]

    async def scenario():
        loop = VoiceLoop(QuietIO(), Models(convo, None, None, None, memorizer), Settings(memory_idle_s=0.1, learn=False), verbose=False)
        reporter = asyncio.create_task(loop._report_levels())
        await asyncio.sleep(0.4)
        reporter.cancel()

    asyncio.run(scenario())
    assert memorizer.batches == []


def test_finished_and_interrupted_turns_are_counted_for_stats():
    import numpy as np

    from companion.reply import Mood
    from companion.stats import StatsStore
    from companion.voice import Turn

    stats = StatsStore(":memory:")
    loop = VoiceLoop(QuietIO(), Models(FakeConversation(), None, None, None, None, stats), Settings(), verbose=False)
    done = Turn(np.zeros(32_000, dtype=np.float32), speech_end=10.0, text="hello", mood=Mood.HAPPY, spoken_seconds=3.0, first_audio_at=10.8)
    cut = Turn(np.zeros(16_000, dtype=np.float32), speech_end=20.0, text="tell me more", first_audio_at=20.9, interrupted_at=22.4)
    loop._record(done, "Hello friend.", interrupted=False)
    loop._record(cut, "Long story", interrupted=True)
    loop._record(Turn(np.zeros(10), speech_end=0.0), "", interrupted=False)
    rows = stats.all()
    assert [(r.mood, r.interrupted, r.user_seconds, r.bot_seconds) for r in rows] == [("happy", False, 2.0, 3.0), ("neutral", True, 1.0, 1.5)]
    assert abs(rows[0].latency - 0.8) < 1e-9
