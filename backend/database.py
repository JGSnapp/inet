from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, text

from config import settings


engine = create_engine(settings.database_url, pool_pre_ping=True)


def _as_dict(row: Any) -> dict[str, Any]:
    item = dict(row._mapping)
    for key in ("created_at", "updated_at"):
        if item.get(key) is not None:
            item[key] = item[key].isoformat()
    return item


def ping_database() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def search_document_records(query: str = "", limit: int = 5) -> list[dict[str, Any]]:
    query = query.strip()
    limit = max(1, min(limit, 20))
    statement = text(
        """
        SELECT id, title, content, source, created_at, updated_at
        FROM documents
        WHERE :query = ''
           OR title ILIKE :pattern
           OR content ILIKE :pattern
           OR COALESCE(source, '') ILIKE :pattern
        ORDER BY updated_at DESC, id
        LIMIT :limit
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(
            statement,
            {"query": query, "pattern": f"%{query}%", "limit": limit},
        )
        return [_as_dict(row) for row in rows]


def get_document_record(document_id: int) -> dict[str, Any] | None:
    statement = text(
        """
        SELECT id, title, content, source, created_at, updated_at
        FROM documents
        WHERE id = :document_id
        """
    )
    with engine.connect() as connection:
        row = connection.execute(statement, {"document_id": document_id}).first()
        return _as_dict(row) if row else None
