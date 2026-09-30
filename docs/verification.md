# Проверка

## Автоматические проверки (CI)

| Команда | Что проверяет |
| --- | --- |
| `ruff check backend sandbox scripts sdk` | Ошибки импорта, неиспользуемый код, синтаксис |
| `ruff format --check backend sandbox scripts sdk` | Единое форматирование |
| `pytest backend -q` | 67 тестов: резервные переходы, кэш и TTL, бюджеты и квоты, отмена и возобновление, фильтрация адресов (SSRF), XML/XXE, шифрование секретов, discovery, очередь, генерация и продвижение адаптеров, canary и откат, parsing pipelines, релевантность поисковой выдачи, релевантность официальных фидов, песочница с подменённым Docker-клиентом, язык сообщений |
| `npm --prefix frontend run build` | Типы TypeScript и production-сборка Vite |

## Ручная проверка на живой сети (30.09.2026, Windows 11, без Docker)

LLM: OpenAI-совместимый API, модель `deepseek/deepseek-v4-pro-0813`.

- `inet doctor`: все зависимости найдены, LLM отвечает.
- `POST /api/search` «free-threaded CPython 3.14 status»: DuckDuckGo упал по таймауту, DDGS вернул 5 релевантных
  источников (docs.python.org, py-free-threading.github.io и др.), ответ синтезирован со ссылками.
- `POST /api/fetch` https://peps.python.org/pep-0703/: страница прочитана через HTTPX (60 000 символов).
  До исправления ступень `official` подменяла статью общим RSS сайта.
- `POST /tavily/search` и `POST /firecrawl/v1/scrape`: ответы в форматах Tavily и Firecrawl.
- MCP по stdio (`inet mcp`): клиент MCP получил инструменты `web_search`, `fetch_url`, `research`
  и успешно вызвал `fetch_url`.
- `install.ps1` на чистой копии репозитория: окружение создано, `inet doctor` проходит.
- `install.sh` в чистой Ubuntu 24.04 (WSL2, без Node.js и без sudo): uv, Python 3.12, зависимости и
  Chromium установлены; `inet doctor` проходит; `inet fetch https://example.com` сам поднял сервер
  и прочитал страницу. Повторный запуск установщика (обновление) проходит без ошибок. Готовый UI
  скачивается из GitHub Release, поэтому до первого релиза установщик честно сообщает, что UI нет.
- Глубокое исследование «Open-source alternatives to Perplexity for self-hosted AI web search in 2026»:
  8,5 минуты, 7 подзапросов, 20 выбранных сайтов, прочитано 15 на 13 доменах, 87 инструментальных вызовов,
  2 сообщения агента из 120. Отчёт со ссылками собран моделью; карта маршрутов показывает переходы
  official → HTTPX → Mobile HTTPX → curl_cffi → Trafilatura для трудных сайтов.
- `scripts/capture_readme.py --lang en|ru`: сквозной сценарий в Chromium на английском и русском
  интерфейсе (глубокое исследование, ход работы агента, карта маршрутов, каталог, состояние системы).
  Английский прогон 01.10.2026: 12 минут, 20 подзапросов, прочитано 12 сайтов из 15 на 8 доменах
  при 45 сбоях поисковиков. Все события, ошибки и подписи отображаются на языке интерфейса.
- Сеть во время проверки была нестабильной: Wikipedia, Bing, Jina Reader и Mojeek периодически
  не отвечали, DuckDuckGo HTML возвращал анти-бот страницу. Один из повторных быстрых поисков
  завершился ошибкой «ступени исчерпаны», потому что все три поисковика не ответили; это
  корректное поведение, но без Docker (SearXNG) запасных поисковиков больше нет.
- Найдено и исправлено по ходу проверки: подмена статьи общим RSS в ступени `official`;
  единственный поисковик без Docker (добавлены DDGS и Wikipedia); принятие нерелевантной выдачи
  (добавлена проверка релевантности); зависание LLM-запросов на 10 минут (таймауты и повторы);
  причина отказа LLM-диагностики не попадала в журнал.

## Что не проверялось

- Платные API (Tavily, Firecrawl) и сервисы CAPTCHA: вызывались только их подмены в тестах.
- macOS: установщик `install.sh` проверен только на Linux.

## Воспроизведение

```bash
inet doctor
.venv/bin/python -m pytest backend -q
npm --prefix frontend run build
inet serve &                          # затем:
.venv/bin/python scripts/capture_readme.py
.venv/bin/python scripts/make_demo_video.py
.venv/bin/python scripts/live_providers.py
```
