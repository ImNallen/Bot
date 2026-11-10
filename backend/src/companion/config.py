import json
import os
from dataclasses import dataclass, fields
from pathlib import Path

APP_DIR = Path.home() / "Library" / "Application Support" / "Companion"


@dataclass
class Settings:
    """Everything tunable. Shared by the voice loop, the model client and the conversation, so a change
    made from the overlay's menu reaches all of them at once."""

    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    model: str = "qwen3.6:35b-a3b-q8_0"
    reasoning_effort: str = "none"
    keep_loaded: bool = True
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
    barge_in: bool = True
    barge_in_ms: int = 192
    pause_ms: int = 300
    reply_gap_ms: int = 650
    sleep_after_s: float = 300
    hub_port: int = 8765
    remember: bool = True
    learn: bool = True
    memory_path: str = str(APP_DIR / "memory.db")
    stats_path: str = str(APP_DIR / "stats.db")
    preferences_path: str = str(APP_DIR / "preferences.json")
    memory_idle_s: float = 45

    @classmethod
    def from_env(cls, saved: dict | None = None) -> "Settings":
        """Defaults, then `saved` preferences, then COMPANION_<FIELD> variables, for example COMPANION_MIC=Wave."""
        values = dict(saved or {})
        for f in fields(cls):
            raw = os.environ.get(f"COMPANION_{f.name.upper()}")
            if raw is None:
                continue
            default = getattr(cls, f.name)
            if isinstance(default, bool):
                values[f.name] = raw.lower() in ("1", "true", "yes", "on")
            elif isinstance(default, (int, float)):
                values[f.name] = type(default)(raw)
            else:
                values[f.name] = raw
        return cls(**values)

    @classmethod
    def load(cls) -> "Settings":
        """What the voice app starts with: choices made in the menu are kept, and the environment still wins."""
        path = Path(os.environ.get("COMPANION_PREFERENCES_PATH", cls.preferences_path))
        return cls.from_env(read_saved(path))


# Fields the overlay's menu may change, and so the only ones written to the preferences file.
SAVED = ("mic", "voice", "speech_speed", "vad_threshold", "reply_gap_ms", "barge_in", "model", "keep_loaded", "reasoning_effort", "learn")


def read_saved(path: Path) -> dict:
    """Saved menu choices. A missing or damaged file, or a value of the wrong type, is ignored rather than trusted."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    kinds = {f.name: type(getattr(Settings, f.name)) for f in fields(Settings)}
    kept = {}
    for name in SAVED:
        if name not in data:
            continue
        value, kind = data[name], kinds[name]
        if name == "mic":
            if value is None or isinstance(value, str):
                kept[name] = value
        elif kind is float and isinstance(value, (int, float)) and not isinstance(value, bool):
            kept[name] = float(value)
        elif kind is not float and type(value) is kind:
            kept[name] = value
    return kept


def write_saved(settings: Settings) -> None:
    path = Path(settings.preferences_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({name: getattr(settings, name) for name in SAVED}, indent=2))
    tmp.replace(path)
