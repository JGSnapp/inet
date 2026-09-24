from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote_plus


DEFAULT_MODELS = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-sonnet-4-20250514",
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
}


def _provider() -> str:
    value = os.getenv("AI_PROVIDER", "openai").strip().lower()
    return PROVIDER_ALIASES.get(value, value)


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AI Agent")
    provider: str = _provider()
    temperature: float = float(os.getenv("AI_TEMPERATURE", "0"))

    db_user: str = os.getenv("POSTGRES_USER", "agent")
    db_password: str = os.getenv("POSTGRES_PASSWORD", "agent")
    db_host: str = os.getenv("POSTGRES_HOST", "postgres")
    db_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    db_name: str = os.getenv("POSTGRES_DB", "agent_db")

    @property
    def model(self) -> str:
        return os.getenv("AI_MODEL", "").strip() or DEFAULT_MODELS.get(
            self.provider, "gpt-4.1-mini"
        )

    @property
    def database_url(self) -> str:
        explicit_url = os.getenv("DATABASE_URL", "").strip()
        if explicit_url:
            return explicit_url
        user = quote_plus(self.db_user)
        password = quote_plus(self.db_password)
        return (
            f"postgresql+psycopg2://{user}:{password}@"
            f"{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
