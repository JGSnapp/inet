from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_MODELS = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-sonnet-5-5",
    "google": "gemini-2.5-flash",
    "groq": "llama-3.3-70b-versatile",
    "deepseek": "deepseek-chat",
    "ollama": "qwen3:8b",
    "openai_compatible": "qwen3:8b",
}

PROVIDER_ALIASES = {
    "gemini": "google",
    "claude": "anthropic",
    "custom": "openai_compatible",
    "lmstudio": "openai_compatible",
    "vllm": "openai_compatible",
    "openrouter": "openai_compatible",
}


def _provider() -> str:
    value = os.getenv("AI_PROVIDER", "openai").strip().lower()
    return PROVIDER_ALIASES.get(value, value)


@dataclass(frozen=True)
class Settings:
    provider: str = _provider()
    temperature: float = float(os.getenv("AI_TEMPERATURE", "0"))

    @property
    def model(self) -> str:
        return os.getenv("AI_MODEL", "").strip() or DEFAULT_MODELS.get(self.provider, "gpt-4.1-mini")


settings = Settings()
