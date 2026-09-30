from __future__ import annotations

import os
from typing import Any

from config import settings
from i18n import tr


SUPPORTED_PROVIDERS = (
    "openai",
    "anthropic",
    "google",
    "groq",
    "deepseek",
    "ollama",
    "openai_compatible",
)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(
            tr(
                f"Для выбранного AI-провайдера задайте {name}.",
                f"Set {name} for the selected AI provider.",
            )
        )
    return value


def _timeout() -> Any:
    """Fail fast on stuck connections and let the client retry instead of waiting 10 minutes."""
    import httpx

    total = float(os.getenv("AI_TIMEOUT", "180"))
    return httpx.Timeout(total, connect=float(os.getenv("AI_CONNECT_TIMEOUT", "10")))


def create_chat_model() -> Any:
    """Create one LangChain chat model from the common environment settings."""
    provider = settings.provider
    common = {"model": settings.model, "temperature": settings.temperature}
    retries = int(os.getenv("AI_MAX_RETRIES", "4"))

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            **common,
            api_key=_required_env("OPENAI_API_KEY"),
            timeout=_timeout(),
            max_retries=retries,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            **common,
            api_key=_required_env("ANTHROPIC_API_KEY"),
            max_retries=retries,
        )

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            **common,
            google_api_key=_required_env("GOOGLE_API_KEY"),
            max_retries=retries,
        )

    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            **common,
            api_key=_required_env("GROQ_API_KEY"),
            max_retries=retries,
        )

    if provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(
            **common,
            api_key=_required_env("DEEPSEEK_API_KEY"),
            max_retries=retries,
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            **common,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )

    if provider == "openai_compatible":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            **common,
            api_key=os.getenv("AI_API_KEY", "not-needed"),
            base_url=os.getenv("AI_BASE_URL", "http://localhost:11434/v1"),
            timeout=_timeout(),
            max_retries=retries,
        )

    choices = ", ".join(SUPPORTED_PROVIDERS)
    raise ValueError(
        tr(
            f"Неизвестный AI_PROVIDER={provider!r}. Доступно: {choices}.",
            f"Unknown AI_PROVIDER={provider!r}. Available: {choices}.",
        )
    )
