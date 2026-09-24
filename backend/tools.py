from __future__ import annotations

import json

from langchain_core.tools import tool

from database import get_document_record, search_document_records


@tool
def search_documents(query: str, limit: int = 5) -> str:
    """Search documents in the database by words from their title, text, or source."""
    documents = search_document_records(query=query, limit=limit)
    return json.dumps({"documents": documents}, ensure_ascii=False)


@tool
def get_document(document_id: int) -> str:
    """Get the complete database document by its numeric ID."""
    document = get_document_record(document_id)
    if document is None:
        return json.dumps(
            {"error": f"Документ с ID {document_id} не найден."}, ensure_ascii=False
        )
    return json.dumps({"document": document}, ensure_ascii=False)


TOOLS = [search_documents, get_document]
