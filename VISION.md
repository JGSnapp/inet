Сейчас в интернете множество бесплатных инструментов для парсинга и веб\-ресерча или с большими бесплатными квотами. Каждый день появляются новые сервисы. Также есть множество бесплатных прокси разного качества. Каждый раз приходится тестирвать различные платформы, выбирать, настраивать под задачу. Это сложно и ненадежно. Ходить и искать бесплатные апи, прописывать фолбэки, чередовать с браузерной автоматизацией \- это долго, надо самому собирать и плюс постоянно появляются новые сервисы и проекты на гитхабе, которые отличаются друг от друга.

Предполагается создание системы с ИИ-агентом, который будет иметь список большого количества подобных бесплатных инструментов, систем и т.д. Он будет иметь различные скиллы, программные ограничения и все остальное, что потребуется для разворачивания и тестирования этих инструментов. Также он будет дополнять этот список утилит и апи.

Основной функционал \- подбор и настройка различных инструментов, максимальная экономия квот, автоматизация поиска и внедрения новых инструментов, использование бесплатных прокси

Система заточена на

Система будет состаоять из нескольких компонентов:

1. Базовый пайплайн, который встречает любой поисковой запрос из нескольких этапов, которые при неудаче фолбэкают друг на друга. Бесплатные API делятся на два класса. Безлимитные и беcключевые (Jina, SearXNG, Wayback, RSS) стоят в лестнице на общих основаниях. Квотируемые обёрнуты регулятором: при пустом бакете ступень выпадает из пайплайна. Состав пайплайна поэтому динамический.  Примерная структура такая: Начальная сортировка ступеней по score; порядок не зафиксирован и перестраивается механизмом продвижения.  
   1. Официальный источник: RSS, sitemap, публичный API, JSON-эндпоинт страницы  
   2. httpx с обычными заголовками  
   3. curl\_cffi с TLS-отпечатком Chrome  
   4. Wayback Machine — условная, если задаче не нужна свежесть  
   5. r.jina.ai — безлимитный reader, снимает JS-рендер без своего браузера  
   6. Playwright headless \+ stealth  
   7. Квотируемый API (Firecrawl, Tavily и т.п.) — условная, при остатке в бакете  
   8. Playwright \+ ожидание селектора

2. Если вдруг происходит отказ, ошибка или что-то еще что-то и ни один из способов не сработал \- запускается сам агент. Он как раз перебирает различные варианты систем из списка, тестирует у себя в песочнице и т.д. Таким образом, запустив агента можно будет ждать, пока он с помощь этих инструментов не получит доступ к сайту или не наладит парсинг или пока с помощью них не найдет новые инструменты, с помощью которых это сможет сделать. Как итог мы получаем улучшения классического пайплайна, а также индивидуальные настройки для этого или других видов сайтов. Он может добавлять проверки, ветвления и т.д. Также у него будет возможность дорабатывать инструменты и вести свои версии подобно, например,  гит. Дополнительно он сможет делать фолбэки на самого себя у этих инструментов, что если не работает \- ему приходит сообщение и он работает дальше. Агент сможет настраивать тайминги и другие вещи, а также будет вести журнал и логи. Это создаст надежную отказоустойчивую, адаптивную, бесплатную систему. Также ии делает заметки и запоминает где и на чем что падало и пытается находить общие паттерны у разных сайтов. ИИ работает в отдельном потоке, обрабатывая кейсы в порядке очереди.  
3. Должна быть разработана система с анализом того, когда возвращается ошибка, капча и т.д. для фолбэков по коду, объему текста, ключевым словам. Такие триггеры настраиваются автоматически или самим агеном.  
4. Если для поиска требуются прокси \- запускает агента поисковика прокси, который ищет новые, а система проверяет фильтрует и составляет рабочий лист прокси.  
5. Дополнительная ступень и часть системы для задач парсинга конкретных сайтов или страниц \- Playwright, Browser Use и подобное через использование агента. Используется если другие методы не подошли и своместно с другими методами.  
6. Получается глобально сводится все к двум пайплайнам: search(query, limit) \-\> \[{url, title, snippet}\] fetch(url) \-\> {content, status, final\_url} \+ браузерное использование  
7. Добавляется сохранение кэша. Самая большая экономия квот \- это не выбор дешёвой ступени, а отсутствие повторного запроса. Нормализация URL, кэш контента с TTL, негативный кэш неудач (чтобы не долбить мёртвую страницу восемью ступенями подряд), дедупликация одинаковых запросов в полёте.

Когда ии подбирает новые инструменты они проходят пайплайн проверок. Также через них пробуем получить доступ к \~20 сайтам, содержимое которых мы знаем, подгоняем под апи и т.д. Самообновление также нужно, чтобы он мог обновлять информацию по квотам и апи

Надо добавить возможность передавать агенту платные ключи и апи, чтобы он включал их в свои пайплайны.

Также агент возможно сможет создавать полноценные системы парсинга.  
Пока мысль на будущее, пока не делать:  можно будет сделать так, что ты можешь оплатить какой-то сервис, то ты можешь ему просто скинуть данные сообщением, он сам все подключит и будет использовать. Также он может просить например выделить деньги на определенный сетап для вашей задачи и считать, сколько что будет стоить.

Примеры утилит:

💀 **Проходим любые капчи на сайтах за секунды**

**Использование персональное и капчи \- на усмотрение пользователя. Мы используем уже готовые проекты**

**CAPTCHA Solver** — интересный open-source проект, который предлагает трёхуровневый подход для работы с CAPTCHA при автоматизации браузера.

💬 Вместо того чтобы сразу отправлять каждую проверку в платный сервис, инструмент сначала пытается **предотвратить появление CAPTCHA**, затем автоматически обрабатывает простые проверки, а уже в сложных случаях использует внешние сервисы решения.

**Внутри:**  
🔣 трёхуровневая архитектура для браузерной автоматизации;  
🔣 бесплатный режим для автоматической обработки некоторых Cloudflare Turnstile CAPTCHA без API-ключей;  
🔣 поддержка более **30 типов CAPTCHA** через интеграцию с **2Captcha** и **CapSolver**, включая reCAPTCHA v2/v3, hCaptcha, Cloudflare Turnstile, Amazon WAF и другие.

💻 Проект будет полезен разработчикам, которые занимаются автоматизацией браузера, тестированием веб\-приложений, RPA и парсингом сайтов, где встречаются различные механизмы защиты.

♎️ [**GitHub/Инструкция**](https://github.com/clawdbrunner/captcha-solver)

Есть бесплатный режим. Сохраняем, пригодится\! 👍

😳 [**Лайф**](https://t.me/akagodlike) | 📲 [**Зеркало Max**](https://max.ru/python2day)

\#python \#soft \#github

⚡️ **Парсинг — один из самых недооценённых навыков в IT**

Пока одни вручную копируют контакты, цены и объявления, другие за минуты собирают тысячи записей, анализируют рынок, ищут клиентов, мониторят конкурентов и строят сервисы, которые сами приносят деньги.

💻 **Держи 10 мощных open-source проектов с GitHub, которые точно стоит добавить в закладки.**

1️⃣ [**Firecrawl**](https://github.com/firecrawl/firecrawl)

Настоящий комбайн для AI. Превращает практически любой сайт в чистый Markdown или структурированный JSON, умеет искать, скрейпить и взаимодействовать с веб\-страницами. Отлично подходит для RAG, LLM и AI-агентов.

2️⃣ [**Crawl4AI**](https://github.com/unclecode/crawl4ai)

Современный Python-краулер, который сразу подготавливает страницы для LLM. Получаете чистый Markdown без лишнего HTML и рекламы — идеально для AI-проектов и больших пайплайнов.

3️⃣ [**Browser Use**](https://github.com/browser-use/browser-use)

AI-агент, который сам управляет браузером: кликает, авторизуется, заполняет формы, переходит по страницам и собирает нужную информацию через интерфейс сайта.

4️⃣ [**Crawlee**](https://github.com/apify/crawlee)

Production-фреймворк для серьёзного парсинга. Очереди, ретраи, прокси, браузерная автоматизация, сохранение результатов и масштабирование «из коробки».

5️⃣ [**Scrapy**](https://github.com/scrapy/scrapy)

Классика Python-парсинга, которая до сих пор остаётся одним из лучших инструментов для создания быстрых и надёжных краулеров.

6️⃣ [**Scrapling**](https://github.com/D4Vinci/Scrapling)

Фреймворк, рассчитанный на более устойчивый парсинг сайтов, которые регулярно меняют свою HTML-разметку.

7️⃣ [**scrcpy**](https://github.com/Genymobile/scrcpy)

Позволяет полностью управлять Android-смартфоном с компьютера. Полезен, если нужные данные доступны только через мобильное приложение.

8️⃣ [**AutoScraper**](https://github.com/alirezamika/autoscraper)

Показываете пример нужных данных — библиотека сама пытается определить шаблон и найти аналогичные элементы на странице. Отличный вариант для быстрого старта.

9️⃣ [**curl-impersonate**](https://github.com/lwthiker/curl-impersonate)

Специальная версия curl, которая имитирует сетевой профиль популярных браузеров. Полезна для тестирования совместимости и работы с сайтами, чувствительными к отпечатку клиента.

1️⃣0️⃣ [**Playwright**](https://github.com/microsoft/playwright)

Если сайт полностью построен на JavaScript, без современного браузерного движка уже никуда. Playwright остаётся одним из самых популярных инструментов для автоматизации браузера и сбора данных с динамических сайтов.

💀 **Инструменты можно использовать для самых разных задач:**

🟢поиск клиентов и лидов;  
🟢мониторинг цен конкурентов;  
🟢агрегаторы товаров;  
🟢анализ рынка;  
🟢сбор вакансий;  
🟢наполнение AI и RAG-систем;  
🟢автоматизация рутинной работы;  
🟢создание собственных сервисов и SaaS.

👍 Сохраняй — такая подборка точно пригодится каждому, кто хочет зарабатывать на данных, автоматизации и Python.

😳 [**Лайф**](https://t.me/akagodlike) | 📲 [**Зеркало Max**](https://max.ru/python2day)

\#soft \#github \#python

**VidBee**

VidBee — это современный, открытый видеозагрузчик, позволяющий скачивать видео и аудио с более чем 1000 сайтов по всему миру.

Он поддерживает загрузку с таких платформ, как YouTube, TikTok, Twitter и многих других.

Программа предоставляет чистый и интуитивно понятный интерфейс с возможностью управления очередью загрузок, а также автоматическую подписку на RSS-каналы для фоновоого скачивания новых видео от любимых авторов.

VidBee поддерживает выбор форматов выходных файлов, включая MP4, MKV и WebM, обеспечивая гибкость в сохранении контента.

Lang: TypeScript  
[https://github.com/nexmoe/VidBee](https://github.com/nexmoe/VidBee)

unbrowse

Unbrowse — это инструмент, позволяющий AI-агентам напрямую взаимодействовать с любым веб\-сайтом на скорости сети, минуя традиционные методы автоматизации браузера.

Он «учится» как веб‑сайт используется через обычный браузер, затем превращает повторяющиеся браузерные действия в прямые API‑вызовы и переиспользуемые «скиллы» для агентов, что обеспечивает выполнение задач в 100 раз быстрее и на 80% дешевле по сравнению с обычной автоматизацией браузера.

Unbrowse использует Model Context Protocol (MCP) для интеграции с различными AI-платформами, такими как Claude Code.

Lang: Shell  
[https://github.com/unbrowse-ai/unbrowse](https://github.com/unbrowse-ai/unbrowse)

[https://r.jina.ai/](https://r.jina.ai/)

[https://xmlstock.com](https://xmlstock.com)

[https://github.com/D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling)

⚡️**Скачиваем что угодно и откуда угодно:** энтузиаст выпустил скилл, который **превращает любую нейросеть в настоящего интернет-сыщика.**

Что умеет:  
> • Достаёт посты из Twitter и тренды из TikTok и Рилсов;  
> • Скачивает ролики и субтитры с YouTube;  
> • Парсит практически любые данные с сайтов;  
> • Бонусом — инструменты для работы с большими данными и автоматизации.

Фактически это универсальный инструмент для сбора информации из всего интернета.

Настраиваем личного сыщика — [здесь.](https://github.com/apify/agent-skills)

**☝🏻 https://gromach.com/**

Сервис GroMach предназначен для автоматизации роста органического трафика на веб\-сайтах с помощью искусственного интеллекта.

Он автоматически создает SEO-оптимизированные статьи на основе ключевых слов и публикует их непосредственно на вашем сайте.

Ключевые функции включают интеллектуальный подбор ключевых слов, генерацию качественного контента, автоматическую публикацию и анализ конкурентов.

GroMach также позволяет настраивать контент в соответствии с уникальным голосом вашего бренда и отслеживать позиции ключевых слов в реальном времени.

**Нейронка теперь управляет компьютером за вас —** китайцы из ByteDance выкатили TARS и это буквально Джарвис из «Железного человека»

ИИ видит экран, двигает мышь, печатает, открывает сайты и работает с программами. Говорите или пишите команды обычными словами: «зайди на сайт», «заполни форму», «скачай файл», «забронируй билет» — и он делает это сам. Никаких скриптов.

Работает как с вашим ПК, так и с удалённым. Всё локально, бесплатно и на разных ОС.

По сути — личный цифровой помощник, который реально сидит за компом вместо вас.

Забираем — [здесь.](https://github.com/bytedance/UI-TARS-desktop)

1. [**SearXNG**](https://docs.searxng.org/?utm_source=chatgpt.com) — пожалуй, главный вариант. Бесплатный open-source metasearch, который агрегирует до \~275 внешних поисковых сервисов. Можно поднять у себя и получать результаты через `/search` в JSON, CSV или RSS. Сам SearXNG денег за запросы не берёт; ограничения возникают уже со стороны Google/Bing/DDG и других источников.  
    **Для своего Perplexity: ⭐⭐⭐⭐⭐**  
2. [**YaCy**](https://yacy.net/) — полностью open-source поисковик, crawler и индексатор. Можно создать собственный индекс либо использовать P2P-модель. Search API возвращает JSON/RSS.  
    **Плюс:** вообще не нужен коммерческий поисковый API.  
    **Минус:** качество глобального индекса заметно слабее Google/Brave.  
3. [**Marginalia Search API**](https://about.marginalia-search.com/article/api/) — независимый индекс веба. Можно прямо использовать `API-Key: public`; для некоммерческого проекта дают отдельный бесплатный ключ. Возвращает JSON с title/URL и результатами поиска.  
    Очень хорош как **дополнительный индекс** к основному поиску.  
4. [**DuckDuckGo HTML**](https://html.duckduckgo.com/?utm_source=chatgpt.com) / [**DuckDuckGo Lite**](https://lite.duckduckgo.com/) — бесплатная SERP без JavaScript и без API key. DuckDuckGo официально поддерживает обе non-JS версии.  
    Это особенно удобно для простого HTTP-парсинга. Официального общего JSON Search API у DDG нет, поэтому для production обычно ставят SearXNG перед ним.  
5. [**Stract**](https://github.com/StractOrg/stract) — полноценный open-source поисковик с собственным независимым индексом. Код можно использовать/self-host. Но важный нюанс: GitHub-репозиторий был **архивирован 2 апреля 2026 года**, поэтому я бы не строил на нём основной production backend.  
6. [**Google Programmable Search Engine**](https://developers.google.com/custom-search?utm_source=chatgpt.com) — стандартный Search Element остаётся бесплатным и у него нет дневного лимита запросов, но результаты показываются через клиентский JavaScript и содержат рекламу.  
    Старый JSON API даёт существующим клиентам 100 бесплатных запросов/день, но **новым клиентам он уже недоступен** и будет отключён 1 января 2027 года.

### **Search API с постоянной бесплатной квотой**

7. [**You.com Search API**](https://you.com/pricing?utm_source=chatgpt.com) — сейчас один из самых щедрых вариантов: **100 бесплатных запросов в день**. Возвращает web \+ news results, snippets и metadata.  
    Это до \~3 000 запросов/месяц без оплаты.  
    **Для AI search: ⭐⭐⭐⭐⭐**  
8. [**Parallel Search API**](https://parallel.ai/pricing) — до **5 000 запросов в месяц бесплатно** в зависимости от режима; Search API возвращает ranked URLs и сжатые excerpts для LLM. Есть даже MCP-вариант без аккаунта/API key для coding agents.  
    **Для AI agents: ⭐⭐⭐⭐⭐**  
9. [**Exa**](https://exa.ai/pricing?utm_source=chatgpt.com) — semantic/neural search, ориентированный на AI. Сейчас free tier даёт **$20 при регистрации \+ $10 бесплатных credits каждый месяц**, без payment method.  
    Обычный Search стоит около $7/1000 базовых запросов, поэтому ежемесячного бесплатного кредита хватает примерно на тысячу+ запросов в зависимости от параметров.  
    **Для semantic search: ⭐⭐⭐⭐⭐**  
10. [**Tavily**](https://www.tavily.com/pricing?utm_source=chatgpt.com) — **1 000 API credits каждый месяц бесплатно**, карта не требуется. Basic search \= 1 credit, advanced \= 2\.  
     Очень удобный API именно для LLM/agents.  
11. [**Firecrawl Search**](https://www.firecrawl.dev/) — с июня 2026 есть **keyless access** и **1 000 бесплатных credits каждый месяц**. Можно не только искать, но сразу получать содержимое найденных страниц.  
     Search сейчас стоит примерно 2 credits за 10 результатов, то есть бесплатная квота позволяет сделать около 500 таких search calls.  
     **Search \+ scraping в одном API: ⭐⭐⭐⭐⭐**  
12. [**Brave Search API**](https://brave.com/search/api/?utm_source=chatgpt.com) — собственный независимый индекс Brave. Каждый месяц автоматически начисляется **$5 credits**; Web Search сейчас стоит $5/1000 requests, то есть примерно **1 000 запросов/месяц** покрываются кредитом.  
     Минус: для подключения API Brave сейчас указывает банковскую карту среди prerequisites.  
     **Качество обычного web search: ⭐⭐⭐⭐⭐**  
13. [**SerpApi**](https://serpapi.com/pricing) — официальный free plan: **250 searches/month**. Отдаёт Google, Bing, YouTube, Google Maps, Shopping и десятки других SERP в JSON/Markdown.  
     Особенно интересен, если нужен именно **Google SERP**, а не альтернативный индекс.  
14. [**Zenserp**](https://zenserp.com/pricing-plans/?utm_source=chatgpt.com) — **50 запросов/месяц бесплатно**. Есть Google, Bing, Google News, Shopping, Trends и другие SERP.

### **Бесплатный стартовый пакет, но не обязательно обновляется каждый месяц**

15. [**Yep Search API**](https://platform.yep.com/) — независимый индекс от Ahrefs/Yep. Сейчас дают **1 000 бесплатных API requests без карты** для старта.  
     Сам поисковик [Yep](https://yep.com/) тоже бесплатен и работает на собственном индексе.  
     **Очень интересный независимый источник.**  
16. [**Serper.dev**](https://serper.dev/?utm_source=chatgpt.com) — Google SERP → JSON. При регистрации дают **2 500 бесплатных запросов**, карта не нужна. После этого сервис платный.  
     Если тебе нужны именно Google rankings, очень полезный стартовый источник.  
17. [**SearchAPI.io**](https://www.searchapi.io/pricing) — **100 бесплатных запросов**, карта не требуется. Поддерживает Google Search, Google Jobs, Shopping, YouTube, Amazon и множество специализированных search endpoints.

### **Просто бесплатная поисковая SERP — API нет или он не бесплатный**

18. [**Brave Search**](https://search.brave.com/) — сам веб\-поиск бесплатен, работает на независимом индексе Brave.  
     Если не нужен официальный API, теоретически можно использовать браузер/SearXNG.  
19. [**DuckDuckGo**](https://duckduckgo.com/) — бесплатная поисковая выдача; плюс особенно удобные HTML/Lite endpoints без JS.  
20. [**Google Search**](https://www.google.com/) — обычная SERP бесплатна для пользователя. Для автоматизации имеет смысл либо браузер/SearXNG/SERP scraper, либо сторонние Serper/SerpApi. Старый официальный JSON Search API новым пользователям уже не дают.  
21. [**Bing**](https://www.bing.com/) — обычная web SERP бесплатна, но старый официальный Bing Search API **полностью закрыт с 11 августа 2025 года**. Microsoft предлагает Grounding with Bing вместо него, а он платный.  
     Поэтому для бесплатного программного доступа — SearXNG/browser.  
22. [**Qwant**](https://www.qwant.com/) — бесплатная публичная поисковая выдача. Qwant официально описывает основной search service как free-to-use.  
     Хороший дополнительный engine в SearXNG.  
23. [**Startpage**](https://www.startpage.com/?utm_source=chatgpt.com) — бесплатный приватный поисковик, выдаёт неперсонализированные Google results. Сам сервис подтверждает, что search полностью бесплатен.  
     Официального бесплатного general-purpose API нет.  
24. [**Ecosia**](https://www.ecosia.org/) — бесплатная веб\-поисковая выдача. Можно использовать как ещё один источник через browser/metasearch.  
25. [**Mojeek**](https://www.mojeek.com/) — особенно интересен тем, что имеет **свой независимый веб\-индекс**, а не просто интерфейс к Google. Публичный search бесплатен.  
     Их официальный Web Search API сейчас платный, поэтому бесплатно — через публичную SERP.  
26. [**Yandex Search**](https://yandex.com/) — бесплатная публичная SERP, особенно полезна для русскоязычного/регионального веба. У Yandex есть отдельный Search API, но его я бы не относил к гарантированно бесплатным API.  
27. [**Yep**](https://yep.com/) — бесплатная публичная SERP \+ собственный независимый индекс Ahrefs. В отличие от многих privacy/metasearch систем, это именно независимый crawl/index.

[https://github.com/JGSnapp/GrantScout](https://github.com/JGSnapp/GrantScout)

Ниже — максимально широкий список, который удалось собрать из актуальных каталогов и источников. Я исключил несколько явно умерших/устаревших сервисов; отдельный свежий аудит в июле 2026 года, например, признал `proxy-list.download`, `openproxy.space` и `getproxylist.com` нерабочими. ([webscraping.ai](https://webscraping.ai/blog/best-free-proxy-lists))

### **Обычные сайты с бесплатными proxy**

1. [ProxyScrape](https://proxyscrape.com/free-proxy-list?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5, API, TXT/JSON/CSV. ([GitHub](https://github.com/proxyscrape/free-proxy-list?utm_source=chatgpt.com))  
2. [GeoNode Free Proxy List](https://geonode.com/free-proxy-list?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5, фильтры, API. ([WebScraping.AI](https://webscraping.ai/blog/best-free-proxy-lists))  
3. [HProxy](https://hproxy.com/free-proxy-list?utm_source=chatgpt.com) — большой постоянно проверяемый список. ([HProxy](https://hproxy.com/free-proxy-list?utm_source=chatgpt.com))  
4. [Proxio](https://proxio.io/?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5 \+ API. ([proxio.io](https://proxio.io/?utm_source=chatgpt.com))  
5. [ProxyO2](https://proxyo2.com/?utm_source=chatgpt.com) — фильтры, JSON API, обновление примерно каждую минуту. ([proxyo2](https://proxyo2.com/?utm_source=chatgpt.com))  
6. [ProxyDime Free Proxy List](https://proxydime.com/free-proxy-list/?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5. ([Proxy Dime- Proxy Reviews and Directory](https://proxydime.com/free-proxy-list/?utm_source=chatgpt.com))  
7. [ProxMint HTTP List](https://proxmint.com/free-proxies/http?utm_source=chatgpt.com) — проверяемые HTTP proxy. ([Proxmint](https://proxmint.com/free-proxies/http?utm_source=chatgpt.com))  
8. [NetVortex Free Proxies](https://net-vortex.com/free-proxies?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5, TXT/JSON. ([NetVortex](https://net-vortex.com/free-proxies?utm_source=chatgpt.com))  
9. [Socks5Proxies.com](https://www.socks5proxies.com/?utm_source=chatgpt.com) — SOCKS5 \+ HTTP/HTTPS, uptime/latency. ([Socks5 Proxies](https://www.socks5proxies.com/?utm_source=chatgpt.com))  
10. [CometVPN Free Proxy List](https://cometvpn.com/free-proxy-list/?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS5. ([CometVPN](https://cometvpn.com/free-proxy-list/?utm_source=chatgpt.com))  
11. [Advanced.name Free Proxy](https://advanced.name/freeproxy?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5. ([Advanced Name](https://advanced.name/freeproxy?utm_source=chatgpt.com))  
12. [ProxyHub](https://proxyhub.me/?utm_source=chatgpt.com) — до тысяч proxy, включая SOCKS5. ([proxyhub.me](https://proxyhub.me/?utm_source=chatgpt.com))  
13. [FreeProxy.World](https://www.freeproxy.world/?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5; десятки тысяч записей. ([freeproxy.world](https://www.freeproxy.world/?utm_source=chatgpt.com))  
14. [ProxyDocker](https://www.proxydocker.com/en/?utm_source=chatgpt.com) — бесплатная публичная таблица HTTP/HTTPS/SOCKS. ([proxydocker.com](https://www.proxydocker.com/en/?utm_source=chatgpt.com))  
15. [Proxy11 Free Proxy](https://proxy11.com/free-proxy?utm_source=chatgpt.com) — бесплатный список \+ JSON/TXT/CSV/XML API с лимитом. ([proxy11.com](https://proxy11.com/free-proxy?utm_source=chatgpt.com))  
16. [Free-Proxy-List.net](https://free-proxy-list.net/?utm_source=chatgpt.com) — один из старейших HTTP/HTTPS каталогов. ([webscraping.ai](https://webscraping.ai/blog/best-free-proxy-lists))  
17. [SSLProxies.org](https://www.sslproxies.org/?utm_source=chatgpt.com) — HTTPS/SSL proxy. ([sslproxies.org](https://www.sslproxies.org/?utm_source=chatgpt.com))  
18. [US-Proxy.org](https://www.us-proxy.org/?utm_source=chatgpt.com) — американские HTTP/HTTPS proxy. ([webscraping.ai](https://webscraping.ai/blog/best-free-proxy-lists))  
19. [Socks-Proxy.net](https://www.socks-proxy.net/?utm_source=chatgpt.com) — SOCKS4/SOCKS5. ([socks-proxy.net](https://www.socks-proxy.net/?utm_source=chatgpt.com))  
20. [ProxyNova](https://www.proxynova.com/proxy-server-list/?utm_source=chatgpt.com) — списки по странам, uptime и последняя проверка. ([WebScraping.AI](https://webscraping.ai/blog/best-free-proxy-lists))  
21. [hide.mn Proxy List](https://hide.mn/en/proxy-list/?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS, фильтры. ([WebScraping.AI](https://webscraping.ai/blog/best-free-proxy-lists))  
22. [Spys.one](https://spys.one/en/?utm_source=chatgpt.com) — очень большая мировая база HTTP/HTTPS/SOCKS. ([WebScraping.AI](https://webscraping.ai/blog/best-free-proxy-lists))  
23. [Proxy-List.org](https://proxy-list.org/english/?utm_source=chatgpt.com) — бесплатная выборка, обновление примерно раз в минуту. ([proxy-list.org](https://proxy-list.org/english/?utm_source=chatgpt.com))  
24. [CheckerProxy](https://checkerproxy.net/?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS5 и фильтрация. Указан среди активно используемых источников агрегаторов. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
25. [Free-Proxy.cz](http://free-proxy.cz/en/proxylist/main/?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5, страны, speed/uptime. ([Floppydata](https://floppydata.com/blog/top-7-proxynova-alternatives/?utm_source=chatgpt.com))  
26. [ProxyListPlus](https://list.proxylistplus.com/Fresh-HTTP-Proxy-List-1?utm_source=chatgpt.com) — HTTP proxy. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
27. [PubProxy](http://pubproxy.com/?utm_source=chatgpt.com) — API/публичные proxy; присутствует в актуальном proxy-scraper наборе. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
28. [OpenProxyList.xyz API](https://api.openproxylist.xyz/?utm_source=chatgpt.com) — HTTP/SOCKS4/SOCKS5 API. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
29. [Spys.me](https://spys.me/proxy.txt?utm_source=chatgpt.com) — простой текстовый HTTP proxy list. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
30. [BlogspotProxy](https://blogspotproxy.blogspot.com/?utm_source=chatgpt.com) — ещё один источник, который используют proxy-агрегаторы. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
31. [Proxifly](https://proxifly.dev/?utm_source=chatgpt.com) — бесплатный API \+ GitHub списки HTTP/HTTPS/SOCKS4/SOCKS5. ([WebScraping.AI](https://webscraping.ai/blog/best-free-proxy-lists))

### **GitHub / RAW-списки — особенно удобно для скриптов**

Свежий агрегатор `proxy-scraper` сейчас поддерживает **36 источников**, а его README утверждает, что они регулярно live-тестируются. ([GitHub](https://github.com/IlmLV/proxy-scraper))

32. [ProxyScrape/free-proxy-list](https://github.com/proxyscrape/free-proxy-list?utm_source=chatgpt.com) — TXT/JSON/CSV, HTTP/HTTPS/SOCKS4/SOCKS5. ([GitHub](https://github.com/proxyscrape/free-proxy-list?utm_source=chatgpt.com))  
33. [IPLocate/free-proxy-list](https://github.com/iplocate/free-proxy-list?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5. В независимом тесте июля 2026 показал лучший HTTP live-rate среди протестированных источников. ([WebScraping.AI](https://webscraping.ai/blog/best-free-proxy-lists))  
34. [TheSpeedX/PROXY-List](https://github.com/TheSpeedX/PROXY-List?utm_source=chatgpt.com) — HTTP/SOCKS4/SOCKS5. ([WebScraping.AI](https://webscraping.ai/blog/best-free-proxy-lists))  
35. [monosans/proxy-list](https://github.com/monosans/proxy-list?utm_source=chatgpt.com) — готовые TXT proxy. ([WebScraping.AI](https://webscraping.ai/blog/best-free-proxy-lists))  
36. [vakhov/fresh-proxy-list](https://github.com/vakhov/fresh-proxy-list?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5. ([WebScraping.AI](https://webscraping.ai/blog/best-free-proxy-lists))  
37. [hookzof/socks5\_list](https://github.com/hookzof/socks5_list?utm_source=chatgpt.com) — чистый SOCKS5. ([WebScraping.AI](https://webscraping.ai/blog/best-free-proxy-lists))  
38. [zloi-user/hideip.me](https://github.com/zloi-user/hideip.me?utm_source=chatgpt.com) — HTTP/HTTPS списки. ([WebScraping.AI](https://webscraping.ai/blog/best-free-proxy-lists))  
39. [roosterkid/openproxylist](https://github.com/roosterkid/openproxylist?utm_source=chatgpt.com) — HTTPS/SOCKS4/SOCKS5. ([WebScraping.AI](https://webscraping.ai/blog/best-free-proxy-lists))  
40. [sunny9577/proxy-scraper](https://github.com/sunny9577/proxy-scraper?utm_source=chatgpt.com) — генерируемые HTTP proxy lists. ([WebScraping.AI](https://webscraping.ai/blog/best-free-proxy-lists))  
41. [Databay free-proxy-list](https://github.com/databay-labs/free-proxy-list?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5, по странам, бесплатный API. ([GitHub](https://github.com/databay-labs/free-proxy-list?utm_source=chatgpt.com))  
42. [Relayglass/free-proxy-list](https://github.com/relayglass/free-proxy-list?utm_source=chatgpt.com) — continuously checked, обновление каждые несколько минут. ([GitHub](https://github.com/relayglass/free-proxy-list?utm_source=chatgpt.com))  
43. [XYZS996 Free Proxy Health List](https://github.com/xyzs996/free-proxy-health-list?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5, TXT/JSON/CSV. ([Xyzs996](https://xyzs996.github.io/free-proxy-health-list/?utm_source=chatgpt.com))  
44. [mzyui/proxy-list](https://github.com/mzyui/proxy-list?utm_source=chatgpt.com) — огромный агрегированный HTTP/SOCKS4/SOCKS5 пул. ([GitHub](https://github.com/mzyui/proxy-list?utm_source=chatgpt.com))  
45. [ALIILAPRO/Proxy](https://github.com/ALIILAPRO/Proxy?utm_source=chatgpt.com) — HTTP/SOCKS4/SOCKS5. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
46. [Bes-js/public-proxy-list](https://github.com/Bes-js/public-proxy-list?utm_source=chatgpt.com) — HTTP/SOCKS4/SOCKS5. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
47. [ErcinDedeoglu/proxies](https://github.com/ErcinDedeoglu/proxies?utm_source=chatgpt.com) — HTTP/SOCKS4/SOCKS5. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
48. [r00tee/Proxy-List](https://github.com/r00tee/Proxy-List?utm_source=chatgpt.com) — HTTPS/SOCKS4/SOCKS5. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
49. [rdavydov/proxy-list](https://github.com/rdavydov/proxy-list?utm_source=chatgpt.com) — HTTP/SOCKS4/SOCKS5. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
50. [SevenworksDev/proxy-list](https://github.com/SevenworksDev/proxy-list?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
51. [SoliSpirit/proxy-list](https://github.com/SoliSpirit/proxy-list?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
52. [themiralay/Proxy-List-World](https://github.com/themiralay/Proxy-List-World?utm_source=chatgpt.com) — HTTP. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
53. [VPSLabCloud/VPSLab-Free-Proxy-List](https://github.com/VPSLabCloud/VPSLab-Free-Proxy-List?utm_source=chatgpt.com) — HTTP/SOCKS4/SOCKS5. ([GitHub](https://github.com/IlmLV/proxy-scraper))  
54. [Zaeem20/FREE\_PROXIES\_LIST](https://github.com/Zaeem20/FREE_PROXIES_LIST?utm_source=chatgpt.com) — HTTP/HTTPS/SOCKS4/SOCKS5. ([GitHub](https://github.com/IlmLV/proxy-scraper))

**Итого: 54 источника/каталога.** Причём это не просто старый SEO-список: значительная часть либо непосредственно индексировалась в августе 2026 года, либо входит в актуальный агрегатор из 36 live-test источников. ([GitHub](https://github.com/IlmLV/proxy-scraper))

Для прокси реальная проверка перед использованием обязательна. ([webscraping.ai](https://webscraping.ai/blog/best-free-proxy-lists))

[https://exa.ai/](https://exa.ai/) и [https://parallel.ai/](https://parallel.ai/) \- бесплатные апи для агентного поиска, которые использует OpenCode, также можно исследовать другие харнесс и репозитории кодинг-агентов, чтобы проанализировать, как они получают доступ в интернет

