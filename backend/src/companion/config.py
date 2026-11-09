import os
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Settings:
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    model: str = "qwen3.6:35b-a3b-q8_0"
    reasoning_effort: str = "none"
    temperature: float = 0.8
    max_tokens: int = 220
    history_turns: int = 12
    examples_as_turns: bool = True
    name: str = "Bot"
    user: str = "the human"

    mic: str | None = None
    speaker: str | None = None
    echo_cancellation: bool = True
    voice: str = "af_heart"
    speech_speed: float = 1.0
    vad_threshold: float = 0.5
    start_ms: int = 96
    barge_in_ms: int = 192
    pause_ms: int = 300
    reply_gap_ms: int = 650
    sleep_after_s: float = 300
    hub_port: int = 8765

    @classmethod
    def from_env(cls) -> "Settings":
        """Any field can be set as COMPANION_<FIELD>, for example COMPANION_MIC=Wave or COMPANION_PAUSE_MS=400."""
        overrides = {}
        for f in fields(cls):
            raw = os.environ.get(f"COMPANION_{f.name.upper()}")
            if raw is None:
                continue
            default = getattr(cls, f.name)
            if isinstance(default, bool):
                overrides[f.name] = raw.lower() in ("1", "true", "yes", "on")
            elif isinstance(default, (int, float)):
                overrides[f.name] = type(default)(raw)
            else:
                overrides[f.name] = raw
        return cls(**overrides)
