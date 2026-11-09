import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

from companion.audio import AudioIO
from companion.config import Settings
from companion.conversation import Conversation
from companion.reply import Mood, MoodEvent, SentenceEvent
from companion.stt import Transcriber
from companion.tts import Synthesizer
from companion.vad import Rechunker, Segmenter, SileroVad, SpeechEnded, SpeechStarted, VadEvent

DIM, RESET = "\033[2m", "\033[0m"


class State(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


@dataclass
class Turn:
    """One exchange, with the timestamps needed to explain its latency."""

    audio: np.ndarray
    speech_end: float
    text: str = ""
    mood: Mood = Mood.NEUTRAL
    spoken: list[tuple[float, str]] = field(default_factory=list)
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

    def __init__(self, io: AudioIO, models: "Models", settings: Settings, verbose: bool = True) -> None:
        self.io, self.settings = io, settings
        self.convo, self.stt, self.tts, self._mlx = models.convo, models.stt, models.tts, models.mlx
        self.verbose = verbose
        self.state = State.IDLE
        self.turns: list[Turn] = []
        self._task: asyncio.Task | None = None
        self._turn: Turn | None = None
        self._unanswered: np.ndarray | None = None
        self._segmenter = Segmenter(threshold=settings.vad_threshold, start_ms=settings.start_ms, end_silence_ms=settings.pause_ms)

    async def run(self) -> None:
        vad, rechunk = SileroVad(), Rechunker()
        async for samples in self.io.frames():
            for chunk in rechunk.push(samples):
                speaking = self.state is State.SPEAKING
                self._segmenter.start_ms = self.settings.barge_in_ms if speaking else self.settings.start_ms
                for event in self._segmenter.feed(chunk, vad(chunk)):
                    self._on_vad(event)

    def _on_vad(self, event: VadEvent) -> None:
        match event:
            case SpeechStarted():
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
        if self._task:
            self._task.cancel()
        if turn is None:
            return
        turn.interrupted_at = self.io.now()
        heard = [sentence for starts, sentence in turn.spoken if starts <= turn.interrupted_at]
        if heard:
            self.convo.record(turn.text, f"[mood:{turn.mood}] {' '.join(heard)} …")
            self._say(f"bot {DIM}[{turn.mood}]{RESET} › {' '.join(heard)} {DIM}(interrupted){RESET}")
        else:
            self._unanswered = turn.audio

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
        async for timed in self.convo.reply(turn.text):
            match timed.event:
                case MoodEvent(mood):
                    turn.mood = mood
                case SentenceEvent(sentence):
                    turn.first_sentence_at = turn.first_sentence_at or self.io.now()
                    chunks = await loop.run_in_executor(self._mlx, lambda: list(self.tts.synthesize(sentence, turn.mood)))
                    if not turn.spoken:
                        await self._hold_until_pause_is_real(turn)
                    starts = [self.io.play(chunk, self.tts.sample_rate) for chunk in chunks]
                    if not starts:
                        continue
                    turn.first_audio_at = turn.first_audio_at or starts[0]
                    if not turn.spoken:
                        self._set(State.SPEAKING)
                    turn.spoken.append((starts[0], sentence))
        self._say(f"bot {DIM}[{turn.mood}]{RESET} › {' '.join(sentence for _, sentence in turn.spoken)}")
        self._say(self._timing(turn))
        while self.io.playing:
            await asyncio.sleep(0.02)
        self._turn = None
        self._set(State.IDLE)

    async def _hold_until_pause_is_real(self, turn: Turn) -> None:
        """Work starts after a short pause; speaking waits for a longer one, so a mid-thought pause is not answered."""
        wait = turn.speech_end + self.settings.reply_gap_ms / 1000 - self.io.now()
        if wait > 0:
            await asyncio.sleep(wait)

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
        if state is not self.state:
            self.state = state
            if state is State.LISTENING:
                self._say(f"{DIM}· listening{RESET}")

    def _say(self, line: str) -> None:
        if self.verbose and line:
            print(line, flush=True)


@dataclass
class Models:
    convo: Conversation
    stt: Transcriber
    tts: Synthesizer
    mlx: ThreadPoolExecutor


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
    convo = Conversation(llm, settings)
    await convo.prime()
    return Models(convo, stt, tts, mlx)


async def run() -> None:
    from companion.audio import DeviceAudio

    settings = Settings.from_env()
    models = await load(settings)
    io = DeviceAudio(mic=settings.mic, speaker=settings.speaker, echo_cancellation=settings.echo_cancellation)
    print(f"{DIM}Listening. Just talk. Ctrl+C quits.{RESET}\n", flush=True)
    await VoiceLoop(io, models, settings).run()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print()
