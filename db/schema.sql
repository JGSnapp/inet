CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS documents_title_idx ON documents (LOWER(title));

INSERT INTO documents (title, content, source)
SELECT title, content, source
FROM (
    VALUES
        (
            'О шаблоне',
            'Это минимальный шаблон чат-бота: Streamlit отвечает за интерфейс, FastAPI и LangGraph — за агента, PostgreSQL — за документы.',
            'system'
        ),
        (
            'Инструменты агента',
            'Агент умеет искать документы по словам и получать полный документ по его числовому ID.',
            'system'
        ),
        (
            'Как расширять проект',
            'Замените таблицу documents своей предметной моделью, добавьте функции с декоратором tool и обновите системный промпт агента.',
            'system'
        )
) AS seed(title, content, source)
WHERE NOT EXISTS (SELECT 1 FROM documents);
