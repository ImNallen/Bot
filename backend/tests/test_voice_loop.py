import asyncio
import time

from companion.config import Settings
from companion.vad import SpeechStarted
from companion.voice import Models, State, VoiceLoop


class QuietIO:
    level = 0.0
    playing = False

    def now(self) -> float:
        return time.monotonic()

    def stop(self) -> None:
        pass


def test_dozes_off_after_idle_and_wakes_when_spoken_to():
    events: list[dict] = []

    async def scenario() -> State:
        loop = VoiceLoop(QuietIO(), Models(None, None, None, None), Settings(sleep_after_s=0.1), publish=events.append, verbose=False)
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
