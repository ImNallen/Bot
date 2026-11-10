from collections import deque
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16_000
CHUNK = 512
CHUNK_MS = CHUNK * 1000 / SAMPLE_RATE


@dataclass(frozen=True)
class SpeechStarted:
    pass


@dataclass(frozen=True)
class SpeechEnded:
    audio: np.ndarray
    silence_ms: float


VadEvent = SpeechStarted | SpeechEnded


class Segmenter:
    """Cuts a stream of 16 kHz chunks into utterances from per-chunk speech probabilities.

    Speech starts after `start_ms` of consecutive speech and ends after `end_silence_ms` of quiet.
    `start_ms` can be raised while the bot talks so its own leftover echo does not count as you.
    """

    def __init__(self, *, threshold: float = 0.5, start_ms: float = 96, end_silence_ms: float = 500, preroll_ms: float = 320) -> None:
        self.threshold = threshold
        self.start_ms = start_ms
        self.end_silence_ms = end_silence_ms
        self._preroll: deque[np.ndarray] = deque(maxlen=max(1, round(preroll_ms / CHUNK_MS)))
        self._speech_run: list[np.ndarray] = []
        self._utterance: list[np.ndarray] | None = None
        self._quiet_chunks = 0

    @property
    def in_speech(self) -> bool:
        return self._utterance is not None

    def feed(self, chunk: np.ndarray, prob: float) -> list[VadEvent]:
        if self._utterance is None:
            return self._while_quiet(chunk, prob)
        return self._while_speaking(chunk, prob)

    def _while_quiet(self, chunk: np.ndarray, prob: float) -> list[VadEvent]:
        if prob < self.threshold:
            self._preroll.extend(self._speech_run)
            self._speech_run = []
            self._preroll.append(chunk)
            return []
        self._speech_run.append(chunk)
        if len(self._speech_run) * CHUNK_MS < self.start_ms:
            return []
        self._utterance = [*self._preroll, *self._speech_run]
        self._preroll.clear()
        self._speech_run = []
        self._quiet_chunks = 0
        return [SpeechStarted()]

    def _while_speaking(self, chunk: np.ndarray, prob: float) -> list[VadEvent]:
        assert self._utterance is not None
        self._utterance.append(chunk)
        self._quiet_chunks = 0 if prob >= self.threshold - 0.15 else self._quiet_chunks + 1
        silence_ms = self._quiet_chunks * CHUNK_MS
        if silence_ms < self.end_silence_ms:
            return []
        audio = np.concatenate(self._utterance)
        self._utterance = None
        self._quiet_chunks = 0
        return [SpeechEnded(audio, silence_ms)]


class SileroVad:
    def __init__(self) -> None:
        from pysilero_vad import SileroVoiceActivityDetector

        self._model = SileroVoiceActivityDetector()

    def __call__(self, chunk: np.ndarray) -> float:
        return self._model.process_samples(chunk.tolist())

    def reset(self) -> None:
        self._model.reset()


class Rechunker:
    """Collects arbitrarily sized 16 kHz float arrays into the fixed 512-sample chunks Silero needs."""

    def __init__(self) -> None:
        self._pending = np.zeros(0, dtype=np.float32)

    def push(self, samples: np.ndarray) -> list[np.ndarray]:
        self._pending = np.concatenate([self._pending, samples.astype(np.float32)])
        count = len(self._pending) // CHUNK
        chunks = [self._pending[i * CHUNK : (i + 1) * CHUNK] for i in range(count)]
        self._pending = self._pending[count * CHUNK :]
        return chunks
