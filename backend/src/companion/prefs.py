"""The overlay menu's view of the settings: friendly keys and units in, validated settings changes out."""

from typing import Any

from companion.config import Settings
from companion.tts import KOKORO_VOICES

# Sensitivity 0 to 1 maps to the speech detector's threshold 0.8 down to 0.2; 0.5 is the default 0.5.
LEAST_SENSITIVE, MOST_SENSITIVE = 0.8, 0.2
SPEED = (0.7, 1.4)
PAUSE_S = (0.35, 1.5)
THINKING_EFFORT = "medium"


def menu_prefs(s: Settings) -> dict[str, Any]:
    return {
        "mic": s.mic,
        "voice": s.voice,
        "speed": s.speech_speed,
        "sensitivity": round((LEAST_SENSITIVE - s.vad_threshold) / (LEAST_SENSITIVE - MOST_SENSITIVE), 2),
        "pause": s.reply_gap_ms / 1000,
        "interrupt": s.barge_in,
        "keepLoaded": s.keep_loaded,
        "thinking": s.reasoning_effort != "none",
        "learn": s.learn,
        "memoryOn": s.remember,
    }


def _number(value: Any, low: float, high: float) -> float | None:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high
    return float(value) if ok else None


def to_settings(key: str, value: Any) -> dict[str, Any] | None:
    """The settings fields a menu change sets, or None when the key is unknown or the value is out of range."""
    match key:
        case "mic" if value is None or (isinstance(value, str) and 0 < len(value) < 200):
            return {"mic": value}
        case "voice" if value in KOKORO_VOICES:
            return {"voice": value}
        case "speed" if (speed := _number(value, *SPEED)) is not None:
            return {"speech_speed": round(speed, 2)}
        case "sensitivity" if (level := _number(value, 0, 1)) is not None:
            return {"vad_threshold": round(LEAST_SENSITIVE - level * (LEAST_SENSITIVE - MOST_SENSITIVE), 3)}
        case "pause" if (pause := _number(value, *PAUSE_S)) is not None:
            return {"reply_gap_ms": round(pause * 1000)}
        case "model" if isinstance(value, str) and 0 < len(value) < 200:
            return {"model": value}
        case "interrupt" | "keepLoaded" | "thinking" | "learn" if isinstance(value, bool):
            field = {"interrupt": "barge_in", "keepLoaded": "keep_loaded", "thinking": "reasoning_effort", "learn": "learn"}[key]
            return {field: (THINKING_EFFORT if value else "none") if key == "thinking" else value}
    return None
