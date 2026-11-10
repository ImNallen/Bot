from collections.abc import Iterator
from typing import Protocol

import numpy as np

from companion.reply import Mood

# English Kokoro voices that sound good enough to live with, best first. The id's first letter is
# the accent (a American, b British) and the second is f or m.
KOKORO_VOICES = (
    "af_heart", "af_bella", "af_nicole", "bf_emma", "am_fenrir", "am_michael", "am_puck",
    "af_aoede", "af_kore", "af_sarah", "bf_isabella", "bm_fable", "bm_george",
)  # fmt: skip


def describe_voice(voice: str) -> dict[str, str]:
    accent = {"a": "American", "b": "British"}.get(voice[0], "")
    kind = {"f": "woman", "m": "man"}.get(voice[1], "")
    return {"id": voice, "name": voice.split("_", 1)[1].capitalize(), "detail": f"{accent} · {kind}"}


class Synthesizer(Protocol):
    sample_rate: int
    voice: str
    speed: float

    def synthesize(self, text: str, mood: Mood, voice: str | None = None) -> Iterator[np.ndarray]:
        """Mono float32 audio for one sentence, yielded as it is generated.

        `mood` is unused by Kokoro; more expressive engines can map it to a speaking style.
        `voice` overrides the current voice for this sentence only, for previews.
        """
        ...


class KokoroSynthesizer:
    def __init__(self, voice: str = "af_heart", speed: float = 1.0, model: str = "mlx-community/Kokoro-82M-bf16") -> None:
        from mlx_audio.tts.utils import load_model

        self._model = load_model(model)
        self.sample_rate: int = self._model.sample_rate
        self.voice = voice
        self.speed = speed

    def synthesize(self, text: str, mood: Mood, voice: str | None = None) -> Iterator[np.ndarray]:
        voice = voice or self.voice
        for result in self._model.generate(text=text, voice=voice, speed=self.speed, lang_code=voice[0]):
            yield np.asarray(result.audio, dtype=np.float32)
