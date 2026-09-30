"""User-facing message language.

Each research run carries the language of the UI that started it; events, errors and exports
of that run are written in it. Background jobs and API clients use INET_LANG (default: en).
Prompts sent to the model are English; answers follow the language of the question.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar

SUPPORTED = ("en", "ru")


def normalize(value: str | None) -> str:
    value = (value or "").strip().lower()[:2]
    return value if value in SUPPORTED else default_language()


def default_language() -> str:
    value = os.getenv("INET_LANG", "en").strip().lower()[:2]
    return value if value in SUPPORTED else "en"


current: ContextVar[str | None] = ContextVar("inet_language", default=None)


def language() -> str:
    return current.get() or default_language()


def tr(ru: str, en: str) -> str:
    """Pick the Russian or English variant for the active language."""
    return ru if language() == "ru" else en


def activate(lang: str | None) -> None:
    """Set the language for the current task (inherited by tasks it creates)."""
    current.set(normalize(lang))


@contextmanager
def use(lang: str | None):
    token = current.set(normalize(lang))
    try:
        yield
    finally:
        current.reset(token)
