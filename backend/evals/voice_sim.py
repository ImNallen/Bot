"""Drive the real voice loop with scripted speech, in real time, and measure it.

Speech is generated with a different Kokoro voice and fed in as the microphone. Nothing is played
aloud; the simulated speaker only records when audio would start and stop. There is no echo in
this setup, so self-interruption from the speakers has to be checked live.

Usage: uv run python evals/voice_sim.py [--hub]

--hub also publishes state, mood and speech levels on ws://127.0.0.1:8765, so a running overlay
acts out the scripted conversation.
"""

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass, field, replace

import numpy as np

from companion.audio import resample
from companion.config import Settings
from companion.reply import Mood
from companion.vad import SAMPLE_RATE
from companion.voice import VoiceLoop, load

FRAME = SAMPLE_RATE // 100


@dataclass
class Step:
    kind: str
    text: str
    audio: np.ndarray
    wait: float
    started: float | None = None
    ended: float | None = None


@dataclass
class SimAudio:
    steps: list[Step]
    plays: list[float] = field(default_factory=list)
    stops: list[float] = field(default_factory=list)
    _play_end: float = 0.0
    _clips: list[tuple[float, np.ndarray, int]] = field(default_factory=list)

    def now(self) -> float:
        return time.monotonic()

    @property
    def playing(self) -> bool:
        return self.now() < self._play_end

    @property
    def level(self) -> float:
        """RMS of the 20 ms of scheduled audio that would be coming out of the speaker right now."""
        now = self.now()
        if now >= self._play_end:
            return 0.0
        for start, audio, rate in self._clips:
            offset = int((now - start) * rate)
            if 0 <= offset < len(audio):
                window = audio[offset : offset + rate // 50]
                return float(np.sqrt(np.mean(window**2))) if len(window) else 0.0
        return 0.0

    def play(self, audio: np.ndarray, sample_rate: int) -> float:
        start = max(self.now(), self._play_end)
        self._play_end = start + len(audio) / sample_rate
        self.plays.append(start)
        self._clips.append((start, audio, sample_rate))
        return start

    def stop(self) -> None:
        if self.playing:
            now = self.now()
            self.stops.append(now)
            self.plays = [p for p in self.plays if p <= now]
            self._clips = [c for c in self._clips if c[0] <= now]
            self._play_end = now

    def _answered_since(self, t: float) -> list[float]:
        return [p for p in self.plays if p > t]

    def _ready(self, step: Step, previous: Step | None, t0: float) -> bool:
        now = self.now()
        if previous is None:
            return now - t0 >= 1.0
        replies = self._answered_since(previous.ended)
        if now - previous.ended > 20:
            return True
        if step.kind == "barge":
            return self.playing and bool(replies) and now - replies[0] >= step.wait
        return bool(replies) and not self.playing and now - self._play_end >= step.wait

    async def frames(self):
        t0 = self.now()
        rng = np.random.default_rng(0)
        pending, current, previous, pos, n = list(self.steps), None, None, 0, 0
        while True:
            await asyncio.sleep(max(0.0, t0 + n * 0.01 - self.now()))
            n += 1
            if current is None and pending and self._ready(pending[0], previous, t0):
                current, pos = pending.pop(0), 0
                current.started = self.now()
            if current is not None:
                chunk = current.audio[pos : pos + FRAME]
                pos += FRAME
                if pos >= len(current.audio):
                    current.ended = self.now()
                    previous, current = current, None
            else:
                chunk = np.zeros(FRAME, dtype=np.float32)
            yield (chunk + rng.normal(0, 0.001, len(chunk))).astype(np.float32) if len(chunk) == FRAME else np.pad(chunk, (0, FRAME - len(chunk)))
            if not pending and current is None and previous and previous.ended:
                done = self._answered_since(previous.ended) and not self.playing and self.now() - self._play_end > 1.0
                if done or self.now() - previous.ended > 20:
                    return


def _speech(tts, text: str) -> np.ndarray:
    audio = np.concatenate(list(tts.synthesize(text, Mood.NEUTRAL)))
    audio = resample(audio, tts.sample_rate, SAMPLE_RATE)
    voiced = np.flatnonzero(np.abs(audio) > 0.02)
    return audio[voiced[0] : voiced[-1] + 1]


async def main() -> None:
    from companion.tts import KokoroSynthesizer

    settings = replace(Settings.from_env(), remember=False)
    models = await load(settings)
    speaker = await asyncio.get_running_loop().run_in_executor(models.mlx, lambda: KokoroSynthesizer(voice="am_michael"))
    def speech(voice, text: str) -> np.ndarray:
        return models.mlx.submit(_speech, voice, text).result()

    pause = np.zeros(int(0.65 * SAMPLE_RATE), dtype=np.float32)
    steps = [
        Step("say", "Hey friend, how are you doing today?", speech(speaker, "Hey friend, how are you doing today?"), 1.5),
        Step("say", "I burned my toast again this morning.", speech(speaker, "I burned my toast again this morning."), 1.5),
        Step(
            "say",
            "I was thinking… (0.65 s pause) …about getting a cat.",
            np.concatenate([speech(speaker, "I was thinking."), pause, speech(speaker, "About getting a cat.")]),
            1.5,
        ),
        Step("say", "Explain how a hash map works, in detail.", speech(speaker, "Explain how a hash map works, in detail."), 1.5),
        Step("barge", "Wait, stop. Tell me about sleep instead.", speech(speaker, "Wait, stop. Tell me about sleep instead."), 1.0),
        Step("say", "Thanks, that helps.", speech(speaker, "Thanks, that helps."), 1.5),
    ]
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub", action="store_true")
    args = ap.parse_args()
    publish = lambda event: None
    if args.hub:
        from companion.hub import Hub

        hub = Hub(port=settings.hub_port)
        await hub.start()
        publish = hub.publish
        await asyncio.sleep(3)

    io = SimAudio(steps)
    loop = VoiceLoop(io, models, settings, publish=publish)
    await loop.run()

    print("\n--- measured")
    latencies = []
    for step in steps:
        if step.kind == "say":
            first = next((p for p in io.plays if p > step.ended), None)
            latency = None if first is None else first - step.ended
            if latency is not None:
                latencies.append(latency)
            shown = "no reply" if latency is None else f"{latency:.2f} s"
            print(f"say    {shown:>9} from end of speech to voice · {step.text}")
        else:
            stop = next((s for s in io.stops if s > step.started), None)
            shown = "never stopped" if stop is None else f"{(stop - step.started) * 1000:.0f} ms"
            print(f"barge  {shown:>9} from start of speech to silence · {step.text}")
    if latencies:
        print(f"\nend of speech to voice: median {statistics.median(latencies):.2f} s · max {max(latencies):.2f} s (work starts after {settings.pause_ms} ms, voice no sooner than {settings.reply_gap_ms} ms)")
    print("transcripts heard:", [t.text for t in loop.turns])


if __name__ == "__main__":
    asyncio.run(main())
