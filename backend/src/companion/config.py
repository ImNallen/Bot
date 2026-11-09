import os
from dataclasses import dataclass


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
    companion_name: str = "Bot"
    user_name: str = "the human"

    @classmethod
    def from_env(cls) -> "Settings":
        env = {"COMPANION_MODEL": "model", "COMPANION_BASE_URL": "base_url", "COMPANION_NAME": "companion_name", "COMPANION_USER": "user_name"}
        return cls(**{field: os.environ[var] for var, field in env.items() if var in os.environ})
