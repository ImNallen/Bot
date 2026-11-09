from collections.abc import Iterator
from typing import Protocol

import numpy as np

from companion.reply import Mood


class Synthesizer(Protocol):
    sample_rate: int

    def synthesize(self, text: str, mood: Mood) -> Iterator[np.ndarray]:
        """Mono float32 audio for one sentence, yielded as it is generated.

        `mood` is unused by Kokoro; more expressive engines can map it to a speaking style.
        """
        ...


class KokoroSynthesizer:
    def __init__(self, voice: str = "af_heart", speed: float = 1.0, model: str = "mlx-community/Kokoro-82M-bf16") -> None:
        from mlx_audio.tts.utils import load_model

        self._model = load_model(model)
        self.sample_rate: int = self._model.sample_rate
        self.voice = voice
        self.speed = speed

    def synthesize(self, text: str, mood: Mood) -> Iterator[np.ndarray]:
        for result in self._model.generate(text=text, voice=self.voice, speed=self.speed, lang_code=self.voice[0]):
            yield np.asarray(result.audio, dtype=np.float32)
