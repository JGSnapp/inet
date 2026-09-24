# Проверка полного контура

## Подтверждено

- `python -m pytest backend -q`: **49 тестов пройдены**. Есть предупреждение deprecated alias внутри Starlette/AnyIO; ошибок тестов нет.
- `npm.cmd --prefix frontend run build`: production-сборка успешна, без предупреждений ESLint. Node уведомляет об устаревшем API внутри react-scripts.
- `docker compose config --quiet`: конфигурация сервисов, изолированной сети, volumes и зависимостей валидна.
- `git diff --check`: ошибок whitespace нет.
- `python scripts/live_providers.py`: реальные HTTPX, curl_cffi, Playwright с ожиданием селектора и официальный JSON GitHub вернули содержимое.
- `python scripts/browser_smoke.py`: Chromium проверил поиск, источники, карту, каталог, систему, лабораторию, сохранение ключа, правил сайта и плана парсинга. JavaScript-ошибок нет, на ширине 390 px горизонтального переполнения нет.
- Полный `docker compose up --build -d` успешен: backend healthy, frontend HTTP 200, sandbox/egress/fixtures работают, SearXNG запущен как управляемый сервис.
- Живой pipeline для Python docs прошёл `semantic-html`, был сохранён и затем выбран Research-маршрутизатором в сквозном запросе.
- OpenAlex был обнаружен как unauthenticated JSON API; детерминированно полученный ConnectorSpec прошёл реальный запрос, вернул 5 sources и был включён с параметрами `search` / `per-page`.

## Что покрывают тесты

Резервные переходы, дедупликация, положительный/отрицательный TTL, резервирование бюджета, отмена и checkpoint resume, сохранение истории, качество контента, фильтрация адресов, gzip-ответы, шифрование секретов, пользовательские API, удалённые квоты/cooldown, discovery, персистентная очередь, структурированная генерация адаптера, 40-проверочный gate для fetch, запрет продвижения до испытаний, canary/rollback, исправление ревизий, CSS-политики, crawl, фильтрация прокси, XML/XXE, запрет утечки авторизации на redirect, managed-service lifecycle, parsing pipelines, drift-monitor, API probing, connector inference и отклонённые connector revisions.

Sandbox-тесты проверяют параметры запуска контейнера, отсутствие host mounts/секретов, обязательную очистку, фиксированные зависимости, фильтр egress и единственное внутреннее исключение для fixtures. Эти проверки используют подменённый Docker-клиент, а не реально работающий daemon.

## Внешние интеграции, не подтверждённые этой сессией

Платные API и CAPTCHA-сервисы не вызывались. Их контракты и переходы проверены с подменами. Полный 20 + 20 gate конкретного нового сгенерированного Python-адаптера в этой сессии не запускался; инфраструктура Docker runtime и Chromium проверена отдельно. Реальная доступность бесплатных прокси нестабильна; рабочий пул формируется только после сетевой проверки каждого адреса.

Код контуров реализован, но эти ограничения проверки нельзя трактовать как успешное внешнее испытание всех интеграций или всех ресурсов каталога.

## Воспроизведение

```powershell
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\python -m pytest backend -q
npm.cmd --prefix frontend run build
.venv\Scripts\python scripts/browser_smoke.py
.venv\Scripts\python scripts/live_providers.py
docker compose up --build
```

После запуска Docker и настройки LLM: в лаборатории запустите discovery, дождитесь generate/evaluate, откройте отчёт версии, затем выполните fetch через неё. На карте и в аудите будут видны canary и результаты реального исполнения. Без прохождения gate активного указателя на кандидата не появится.

Браузерный сценарий поднимает API и статический сервер на loopback-портах 8007/3007 с временной БД и отключённой фоновой автоматизацией; в конце останавливает свои процессы. Снимки находятся в игнорируемом `artifacts/`: главная, ответ, карта, лаборатория и мобильная главная.
