import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

import numpy as np

from companion.audio import AudioIO
from companion.config import Settings
from companion.conversation import Conversation
from companion.hub import Event
from companion.prefs import menu_prefs
from companion.remember import Memorizer, with_memory
from companion.reply import Mood, MoodEvent, SentenceEvent
from companion.stats import StatsStore, TurnRecord
from companion.stt import Transcriber
from companion.tts import Synthesizer
from companion.vad import SAMPLE_RATE, Rechunker, Segmenter, SileroVad, SpeechEnded, SpeechStarted, VadEvent

DIM, RESET = "\033[2m", "\033[0m"
PREVIEW_LINE = "Hello, friend. This is my voice. You like it, question?"


class State(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    SLEEPING = "sleeping"


@dataclass
class Turn:
    """One exchange, with the timestamps needed to explain its latency."""

    audio: np.ndarray
    speech_end: float
    text: str = ""
    mood: Mood = Mood.NEUTRAL
    spoken: list[tuple[float, str]] = field(default_factory=list)
    spoken_seconds: float = 0.0
    captions: list[asyncio.TimerHandle] = field(default_factory=list)
    transcribed_at: float | None = None
    first_sentence_at: float | None = None
    first_audio_at: float | None = None
    interrupted_at: float | None = None

    @property
    def latency(self) -> float | None:
        return None if self.first_audio_at is None else self.first_audio_at - self.speech_end


class VoiceLoop:
    """Mic to speech detection to Parakeet to the LLM to Kokoro to speakers, with barge-in.

    Work starts after `pause_ms` of silence, but audio waits until `reply_gap_ms`. Speech before then
    means you were not done: the reply is dropped and your next words are joined to what you already
    said. Speech while speaking stops playback at once, and only the sentences you actually heard go
    into the conversation history.
    """

    def __init__(
        self,
        io: AudioIO,
        models: "Models",
        settings: Settings,
        publish: Callable[[Event], None] = lambda event: None,
        verbose: bool = True,
    ) -> None:
        self.io, self.settings, self.publish = io, settings, publish
        self.convo, self.stt, self.tts, self._mlx = models.convo, models.stt, models.tts, models.mlx
        self.memorizer, self.stats = models.memorizer, models.stats
        self._saving: asyncio.Task | None = None
        self.mic_on = True
        self.verbose = verbose
        self.state = State.IDLE
        self.turns: list[Turn] = []
        self._task: asyncio.Task | None = None
        self._turn: Turn | None = None
        self._unanswered: np.ndarray | None = None
        self._mic_level = 0.0
        self._idle_since = io.now()
        self._segmenter = Segmenter(threshold=settings.vad_threshold, start_ms=settings.start_ms, end_silence_ms=settings.pause_ms)

    def command(self, name: str) -> None:
        """From the overlay's menu: mute or unmute the microphone, or doze off now."""
        if name in ("mute", "unmute"):
            self.mic_on = name == "unmute"
            self.publish_status()
            self._say(f"{DIM}· microphone {'on' if self.mic_on else 'off'}{RESET}")
        elif name == "sleep":
            if self.state in (State.THINKING, State.SPEAKING):
                self._interrupt()
            self._set(State.SLEEPING)

    def publish_status(self) -> None:
        memories = len(self.memorizer.store.all()) if self.memorizer else 0
        self.publish({"type": "status", "micOn": self.mic_on, "model": self.settings.model, "memories": memories, "prefs": menu_prefs(self.settings)})

    def settings_changed(self) -> None:
        """Copies settings that parts of the loop keep their own copy of, after a change from the menu."""
        self._segmenter.threshold = self.settings.vad_threshold
        if self.tts:
            self.tts.voice, self.tts.speed = self.settings.voice, self.settings.speech_speed
        self.publish_status()

    async def preview(self, voice: str) -> None:
        """Says a short line in another voice, only while nobody is talking."""
        if self.state not in (State.IDLE, State.SLEEPING):
            return
        chunks = await asyncio.get_running_loop().run_in_executor(self._mlx, lambda: list(self.tts.synthesize(PREVIEW_LINE, Mood.HAPPY, voice)))
        if self.state in (State.IDLE, State.SLEEPING):
            self.io.stop()
            for chunk in chunks:
                self.io.play(chunk, self.tts.sample_rate)

    async def run(self) -> None:
        self.publish_status()
        vad, rechunk = SileroVad(), Rechunker()
        levels = asyncio.create_task(self._report_levels())
        try:
            async for samples in self.io.frames():
                self._mic_level = max(float(np.sqrt(np.mean(samples**2))), self._mic_level * 0.8)
                self._feed(rechunk.push(samples), vad)
        finally:
            levels.cancel()

    def _feed(self, chunks: list[np.ndarray], vad: SileroVad) -> None:
        for chunk in chunks:
            speaking = self.state is State.SPEAKING
            self._segmenter.start_ms = self.settings.barge_in_ms if speaking else self.settings.start_ms
            for event in self._segmenter.feed(chunk, vad(chunk)):
                self._on_vad(event)

    async def _report_levels(self) -> None:
        """Loudness for the mouth and the listening ring, and dozing off after a long quiet spell."""
        while True:
            await asyncio.sleep(1 / 30)
            self.publish({"type": "levels", "speech": round(self.io.level, 4), "mic": round(self._mic_level, 4)})
            idle_for = self.io.now() - self._idle_since if self.state in (State.IDLE, State.SLEEPING) else 0
            if self.state is State.IDLE and idle_for > self.settings.sleep_after_s:
                self._set(State.SLEEPING)
            if idle_for > self.settings.memory_idle_s and self.memorizer and self.settings.learn and self.convo.exchanges and not self._saving:
                self._saving = asyncio.create_task(self._save_memories())

    def _on_vad(self, event: VadEvent) -> None:
        if not self.mic_on or (self.state is State.SPEAKING and not self.settings.barge_in):
            return
        match event:
            case SpeechStarted():
                if self._saving:
                    self._saving.cancel()
                if self.state in (State.THINKING, State.SPEAKING):
                    self._interrupt()
                self._set(State.LISTENING)
            case SpeechEnded(audio, silence_ms) if self.state is State.LISTENING:
                if self._unanswered is not None:
                    audio = np.concatenate([self._unanswered, audio])
                    self._unanswered = None
                turn = Turn(audio, speech_end=self.io.now() - silence_ms / 1000)
                self._turn = turn
                self._set(State.THINKING)
                self._task = asyncio.create_task(self._respond(turn))
                self._task.add_done_callback(self._turn_finished)

    def _interrupt(self) -> None:
        turn, self._turn = self._turn, None
        self.io.stop()
        for caption in turn.captions if turn else []:
            caption.cancel()
        if self._task:
            self._task.cancel()
        if turn is None:
            return
        turn.interrupted_at = self.io.now()
        heard = [sentence for starts, sentence in turn.spoken if starts <= turn.interrupted_at]
        if heard:
            self.convo.interrupted(f"[mood:{turn.mood}] {' '.join(heard)} …")
            self._record(turn, " ".join(heard), interrupted=True)
            self._say(f"bot {DIM}[{turn.mood}]{RESET} › {' '.join(heard)} {DIM}(interrupted){RESET}")
        else:
            self._unanswered = turn.audio

    async def _save_memories(self) -> None:
        """Runs while the conversation is quiet; talking cancels it and the turns wait for next time."""
        batch = list(self.convo.exchanges)
        try:
            added = await self.memorizer.remember(batch, datetime.now())
            del self.convo.exchanges[: len(batch)]
            if added:
                self.publish_status()
            for memory in added:
                self._say(f"{DIM}· remembered: {memory.text}{' (' + str(memory.on) + ')' if memory.on else ''}{RESET}")
        except asyncio.CancelledError:
            pass
        except Exception as error:
            self._say(f"{DIM}· could not save memories: {error!r}{RESET}")
        finally:
            self._saving = None

    def _turn_finished(self, task: asyncio.Task) -> None:
        if task.cancelled() or task.exception() is None:
            return
        self._say(f"{DIM}turn failed: {task.exception()!r}{RESET}")
        self._turn = None
        self._set(State.IDLE)

    async def _respond(self, turn: Turn) -> None:
        self.turns.append(turn)
        loop = asyncio.get_running_loop()
        turn.text = await loop.run_in_executor(self._mlx, self.stt.transcribe, turn.audio)
        turn.transcribed_at = self.io.now()
        if not turn.text:
            self._set(State.IDLE)
            return
        self._say(f"you › {turn.text}")
        self.publish({"type": "heard", "text": turn.text})
        async for timed in self.convo.reply(turn.text):
            match timed.event:
                case MoodEvent(mood):
                    turn.mood = mood
                    self.publish({"type": "mood", "mood": mood.value})
                case SentenceEvent(sentence):
                    turn.first_sentence_at = turn.first_sentence_at or self.io.now()
                    chunks = await loop.run_in_executor(self._mlx, lambda: list(self.tts.synthesize(sentence, turn.mood)))
                    if not turn.spoken:
                        await self._hold_until_pause_is_real(turn)
                    starts = [self.io.play(chunk, self.tts.sample_rate) for chunk in chunks]
                    turn.spoken_seconds += sum(len(chunk) for chunk in chunks) / self.tts.sample_rate
                    if not starts:
                        continue
                    turn.first_audio_at = turn.first_audio_at or starts[0]
                    delay = max(0.0, starts[0] - self.io.now())
                    turn.captions.append(loop.call_later(delay, self.publish, {"type": "said", "text": sentence}))
                    if not turn.spoken:
                        self._set(State.SPEAKING)
                    turn.spoken.append((starts[0], sentence))
        reply = " ".join(sentence for _, sentence in turn.spoken)
        self._say(f"bot {DIM}[{turn.mood}]{RESET} › {reply}")
        self._say(self._timing(turn))
        self._record(turn, reply, interrupted=False)
        while self.io.playing:
            await asyncio.sleep(0.02)
        self._turn = None
        self._set(State.IDLE)

    async def _hold_until_pause_is_real(self, turn: Turn) -> None:
        """Work starts after a short pause; speaking waits for a longer one, so a mid-thought pause is not answered."""
        wait = turn.speech_end + self.settings.reply_gap_ms / 1000 - self.io.now()
        if wait > 0:
            await asyncio.sleep(wait)

    def _record(self, turn: Turn, reply: str, interrupted: bool) -> None:
        if not self.stats or not turn.text:
            return
        heard_for = turn.interrupted_at - turn.first_audio_at if interrupted and turn.first_audio_at else turn.spoken_seconds
        record = TurnRecord(datetime.now(), turn.mood.value, turn.latency, interrupted, turn.text, reply, len(turn.audio) / SAMPLE_RATE, max(0.0, heard_for))
        try:
            self.stats.add(record)
        except Exception as error:
            self._say(f"{DIM}· could not save stats: {error!r}{RESET}")

    def _timing(self, turn: Turn) -> str:
        if turn.latency is None:
            return ""
        pause = self.settings.pause_ms / 1000
        parts = [
            ("pause", pause),
            ("stt", turn.transcribed_at - turn.speech_end - pause),
            ("reply", turn.first_sentence_at - turn.transcribed_at),
            ("voice+hold", turn.first_audio_at - turn.first_sentence_at),
        ]
        breakdown = " · ".join(f"{name} {seconds:.2f}" for name, seconds in parts)
        return f"{DIM}{turn.latency:.2f} s from end of speech to voice ({breakdown}){RESET}"

    def _set(self, state: State) -> None:
        if state is self.state:
            return
        self.state = state
        if state is State.IDLE:
            self._idle_since = self.io.now()
        self.publish({"type": "state", "state": state.value})
        if state is State.LISTENING:
            self._say(f"{DIM}· listening{RESET}")
        elif state is State.SLEEPING:
            self.convo.new_session()
            self._say(f"{DIM}· dozing off{RESET}")

    def _say(self, line: str) -> None:
        if self.verbose and line:
            print(line, flush=True)


@dataclass
class Models:
    convo: Conversation
    stt: Transcriber
    tts: Synthesizer
    mlx: ThreadPoolExecutor
    memorizer: Memorizer | None = None
    stats: StatsStore | None = None


async def load(settings: Settings) -> Models:
    """MLX binds compute streams to the thread that loads a model, so STT and TTS load and run on one worker thread."""
    from companion.llm import LLM
    from companion.stt import ParakeetTranscriber
    from companion.tts import KokoroSynthesizer

    def build() -> tuple[Transcriber, Synthesizer]:
        stt = ParakeetTranscriber()
        tts = KokoroSynthesizer(voice=settings.voice, speed=settings.speech_speed)
        stt.transcribe(np.zeros(16_000, dtype=np.float32))
        list(tts.synthesize("Ready.", Mood.NEUTRAL))
        return stt, tts

    print(f"{DIM}Loading models…{RESET}", flush=True)
    llm = LLM(settings)
    mlx = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx")
    stt, tts = await asyncio.get_running_loop().run_in_executor(mlx, build)
    await llm.warm()
    convo, memorizer = with_memory(llm, settings)
    await convo.prime()
    stats = StatsStore(settings.stats_path) if settings.remember else None
    return Models(convo, stt, tts, mlx, memorizer, stats)


async def run() -> None:
    from companion.audio import DeviceAudio
    from companion.control import Control
    from companion.hub import Hub

    settings = Settings.load()
    models = await load(settings)
    hub = Hub(port=settings.hub_port)
    await hub.start()
    io = DeviceAudio(mic=settings.mic, speaker=settings.speaker, echo_cancellation=settings.echo_cancellation)
    print(f"{DIM}Listening. Just talk. Ctrl+C quits. Overlay link on ws://127.0.0.1:{hub.port}{RESET}\n", flush=True)
    loop = VoiceLoop(io, models, settings, publish=hub.publish)
    hub.on_request = Control(loop, models.convo, io.use_mic).handle
    await loop.run()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print()
