from typing import Protocol

import numpy as np


class Transcriber(Protocol):
    def transcribe(self, audio: np.ndarray) -> str:
        """Text for a 16 kHz mono float32 utterance."""
        ...


class ParakeetTranscriber:
    def __init__(self, model: str = "mlx-community/parakeet-tdt-0.6b-v3") -> None:
        from parakeet_mlx import from_pretrained

        self._model = from_pretrained(model)

    def transcribe(self, audio: np.ndarray) -> str:
        import mlx.core as mx
        from parakeet_mlx.audio import get_logmel

        mel = get_logmel(mx.array(audio.astype(np.float32)), self._model.preprocessor_config)
        return self._model.generate(mel)[0].text.strip()
