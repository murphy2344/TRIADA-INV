# CLAUDE_PROJECT_CONTEXT.md
# TRIADA Group / TRIADA-INV — технический паспорт проекта и рабочий контекст для Claude Code

> **Версия документа:** 1.0  
> **Дата подготовки:** 22 ноября 2026  
> **Репозиторий:** https://github.com/murphy2344/TRIADA-INV  
> **Основная ветка:** `main`  
> **Назначение:** передать Claude Code единый контекст компании, продукта, кода, инфраструктуры, интеграций, целей основателя и правил разработки.
>
> **Критически важно:** этот документ собран по текущим файлам репозитория и доступной истории проекта. Он не заменяет проверку исходного кода, Render, Neon и фактических переменных окружения. Наличие переменной в `.env.example` или `render.yaml` НЕ доказывает, что секрет задан в production или сервис реально работает. Описание функции в `ROADMAP.md` НЕ доказывает, что она исправна в production. Всегда различай: **подтверждено кодом**, **задекларировано документацией**, **исторически наблюдалось**, **планируется**, **не проверено**.

---

# 0. Инструкция Claude Code: как работать с этим проектом

Ты работаешь над реальным продуктом TRIADA-INV, который является частью более широкой задумки TRIADA Group. Ты не начинаешь проект с нуля. В репозитории есть существующая архитектура, накопленные решения, история изменений, база данных, интеграции и работающие пользовательские сценарии.

## 0.1 Главные правила

1. **Сначала исследуй, затем меняй.** Перед изменениями прочитай относящиеся к задаче модули, конфигурацию, тесты, миграции, `SPEC.md`, `ROADMAP.md` и этот файл.
2. **Не переписывай проект целиком.** Предпочитай небольшие, изолированные, проверяемые изменения. Не заменяй рабочую реализацию новой архитектурой без доказанной необходимости.
3. **Не выдумывай состояние инфраструктуры.** Проверяй Render deploys/logs/metrics и Neon, если соответствующие подключения доступны. Если доступов нет — прямо сообщай, что проверка production не выполнена.
4. **Не раскрывай секреты.** Никогда не выводи в терминал, лог, Markdown, PR, commit message или отчёт значения API keys, Telegram tokens, session strings, database URLs, passwords. Не читай и не печатай секреты без крайней необходимости. Не добавляй секреты в репозиторий.
5. **Не ломай обратную совместимость БД.** Любое изменение схемы должно иметь миграцию для PostgreSQL/Neon и учитывать SQLite fallback, если он сохраняется. Проверяй миграции на отдельной/тестовой БД, не на production без явного согласования.
6. **Проверяй обе СУБД.** SQL-совместимость PostgreSQL и SQLite — отдельный риск из-за адаптера `modules/db_compat.py`.
7. **Финансовые данные должны быть проверяемыми.** Для каждого числа по возможности указывай инструмент, валюту, источник, время получения, период, единицы измерения и задержку. Не называй delayed/free data real-time.
8. **AI не является источником фактов.** Модель интерпретирует предоставленные данные. Факты должны приходить из источников/провайдеров. Отделяй факты, утверждения источника и гипотезы.
9. **Не добавляй дорогие сервисы самовольно.** Основной принцип — free/low-cost stack. Любой платный API, тариф или инфраструктурный ресурс требует оценки пользы, стоимости, лимитов и согласования с основателем.
10. **Не делай deploy автоматически после любого изменения.** Сначала тесты, diff review, проверка миграций и оценка риска. Production deploy — только если задача этого требует и доступ/разрешение есть. После deploy проверяй фактический commit и health.
11. **Не отмечай задачу выполненной по факту написания кода.** Готово = код изменён, тесты запущены, результаты проверены, ограничения названы. Production-ready = дополнительно проверено в целевой среде.
12. **Не удаляй существующие функции/команды ради упрощения** без анализа использования и явного объяснения.
13. **Сохраняй русский язык пользовательских сообщений**, если существующий UX не требует иного. Имена переменных/кода — на английском.
14. **Работай поэтапно:** один логический блок → тесты → ревью diff → отчёт → следующий блок.
15. Если видишь противоречие между этим паспортом, `SPEC.md`, `ROADMAP.md` и кодом, **код показывает текущую реализацию**, `SPEC.md` — желаемый контракт, `ROADMAP.md` — намерения/план, а этот документ — сводный контекст. Зафиксируй противоречие, не угадывай.

## 0.2 Формат отчёта после каждой задачи

Всегда сообщай:
- **Цель:** что требовалось исправить/создать.
- **Диагностика:** что было обнаружено и где.
- **Изменения:** файлы, функции, схема БД, API-контракты.
- **Причина решения:** почему выбран именно этот вариант.
- **Тесты:** точные команды и фактический результат; не писать «прошло», если не запускалось.
- **Риски/ограничения:** что осталось неизвестным или не проверено.
- **Git:** ветка, commit/PR, статус merge.
- **Production:** deploy ID, deployed commit, состояние Render и post-deploy проверки — только если реально проверены.
- **Следующий приоритет:** одна конкретная следующая задача.

---

# 1. TRIADA Group — компания и глобальное видение

## 1.1 Что такое TRIADA Group

TRIADA Group — задуманная основателем технологическая компания и зонтичная экосистема продуктов. Это не только название Telegram-бота. Цель — создать группу взаимосвязанных технологических направлений, которые используют общие инженерные, AI- и продуктовые принципы.

На данный момент TRIADA Group следует считать **стратегической концепцией/будущей компанией**, а не утверждать, что все её подразделения уже зарегистрированы, запущены или имеют самостоятельные работающие продукты. Юридическая структура, регистрация, окончательный корпоративный устав, утверждённая бизнес-модель и финансовая структура в доступном контексте не подтверждены.

## 1.2 Предполагаемые направления

### TRIADA AI
Стратегическое направление, связанное с искусственным интеллектом:
- интеллектуальные агенты и AI-системы;
- анализ информации и данных;
- прогнозирование и поддержка принятия решений;
- автоматизация бизнес-процессов;
- AI-инструменты для компаний и пользователей;
- оркестрация специализированных моделей/агентов.

### TRIADA Finance
Финансовое и инвестиционно-технологическое направление:
- финансовая аналитика;
- глобальные рынки;
- инвестиционные исследования;
- данные, риск-аналитика и портфельные инструменты;
- TRIADA-INV как первый ключевой продуктовый вектор.

### TRIADA Energy
Потенциальное направление в энергетике:
- энергетические рынки и технологии;
- аналитика энергетических данных;
- потенциальные цифровые продукты и решения для энергетического сектора.

**Статус:** это направления долгосрочного видения основателя. Не описывай их как действующие бизнес-единицы или готовые продукты без отдельного подтверждения.

## 1.3 Философия компании

Рабочая формулировка: **делать сложные системы простыми в использовании, не упрощая их содержание.**

Принципы:
1. Evidence before confidence — доказательства важнее уверенного тона.
2. Signal over noise — ценность важнее количества сообщений.
3. Clarity over complexity — сложная инженерия, понятный интерфейс.
4. Reliability before expansion — стабильность раньше новых функций.
5. Measured performance — измерять результат, а не обещания.
6. Modular growth — расширять продукт через чёткие контракты модулей.
7. Honest limitations — открыто показывать ограничения и неопределённость.
8. Capital discipline — учитывать стоимость каждого API, модели и сервиса.
9. Premium execution — высокий уровень качества, консистентности и деталей.
10. Long-term product thinking — строить систему, а не набор несвязанных функций.

## 1.4 Роль основателя

Основатель формирует видение, продуктовую стратегию, приоритеты, пользовательские сценарии и требования к качеству. Не следует ожидать, что он будет самостоятельно проектировать каждую техническую деталь или писать код.

Задача Claude Code — переводить продуктовые цели в инженерные решения, объяснять компромиссы простым языком и не перекладывать на основателя необходимость повторно описывать известный контекст.

---

# 2. TRIADA-INV — что это за продукт и зачем он нужен

## 2.1 Определение

**TRIADA-INV** — глобальная финансовая intelligence-платформа для инвесторов и трейдеров. Сейчас её основная реализация — Python Telegram-бот с публичной новостно-аналитической поверхностью и персональными функциями. Долгосрочная цель — полноценный терминал с Telegram Mini App и/или web-интерфейсом.

Ключевая продуктовая формула:

> **Bloomberg Terminal в Telegram — глубина и связность финансовой аналитики, доступные быстро и понятно со смартфона, с минималистичным качеством пользовательского опыта в духе Apple.**

Это направление развития и стандарт амбиций, а не заявление об эквивалентности Bloomberg по лицензированным данным, задержкам, инфраструктуре, охвату или институциональной точности.

## 2.2 Какую потребность закрывает

Инвестору приходится собирать картину рынка из множества разрозненных продуктов:
- новостные сайты и терминалы;
- сайты компаний и SEC;
- экономические календари;
- графики и скринеры;
- фундаментальные отчёты;
- технические индикаторы;
- аналитические прогнозы;
- портфельные приложения;
- оповещения и таблицы.

Это требует времени и постоянного переключения между источниками. Кроме того, пользователь часто видит новость, но не получает ответа на главные вопросы:
- Почему это важно?
- Какие активы затронуты?
- Какой механизм влияния на бизнес и цену?
- Это краткосрочный шум или долгосрочный катализатор?
- Что уже учтено рынком?
- Какие факты подтверждены?
- Какие сценарии возможны?
- Какие риски и условия отменяют гипотезу?
- Как событие связано с моим портфелем?
- Как похожие рекомендации работали раньше?

TRIADA-INV должна соединить этот workflow в одной системе.

## 2.3 Ценность для разных пользователей

### Частный инвестор
- быстрее понимает, что происходит на мировых рынках;
- получает объяснение финансовых новостей простым языком;
- видит связь событий с активами из watchlist/portfolio;
- получает фундаментальный и технический контекст;
- не обязан постоянно мониторить десятки сайтов.

### Активный трейдер
- следит за событиями и ценовыми уровнями;
- использует графики, индикаторы, скринеры и alerts;
- получает структурированное объяснение катализаторов;
- видит риск и условия, при которых сценарий перестаёт быть актуальным.

### Начинающий инвестор
- получает понятные объяснения терминов и показателей;
- видит источники и аргументацию;
- может постепенно переходить от простых обзоров к глубокому анализу.

### Опытный пользователь
- получает сжатую картину большого объёма информации;
- может сравнивать активы и компании;
- анализирует earnings, макроэкономику, сектора, институциональные данные;
- оценивает историю сигналов и качество гипотез.

## 2.4 Что должно отличать TRIADA-INV

1. Не просто RSS-агрегатор, а event-centric intelligence.
2. Не просто AI-summary, а факты + контекст + влияние + сценарии + риски.
3. Не просто сигнал LONG/SHORT, а объяснимая гипотеза с горизонтом и условиями invalidation.
4. Не просто общий поток новостей, а связь с watchlist и личным портфелем.
5. Не просто график, а проверяемые данные с источником и timestamp.
6. Не просто обещание точности, а честный исторический track record.
7. Не перегруженный терминал, а интерфейс, в котором сложность скрыта за понятной навигацией.

## 2.5 Границы продукта

- География: глобальные рынки.
- Российские биржи, MOEX/IMOEX/RTS и RUB-инструменты намеренно исключены.
- Продукт не должен обещать гарантированную доходность.
- Не является брокером или биржей, пока не реализованы и юридически не оформлены соответствующие возможности.
- Не должен имитировать real-time при использовании задержанных или бесплатных источников.
- AI-ответ не является финансовым фактом или гарантированной инвестиционной рекомендацией.

---

# 3. Продуктовая архитектура: текущие и будущие поверхности

## 3.1 Публичный Telegram-канал/группа — Global News Radar

Назначение: общий поток рыночной информации для сообщества.

Задекларированные в коде/спецификации типы публикаций и задач:
- BREAKING — важные новости;
- HOURLY — часовой дайджест;
- MORNING — утренний обзор;
- EVENING — вечерний обзор;
- WEEKLY — недельный обзор;
- MONTHLY — месячный обзор;
- market pulse;
- Market Snapshot;
- Sector Performance / Sector Heatmap;
- Fear & Greed;
- Earnings Today / This Week;
- Economic Calendar;
- COT Report;
- 13F Filings;
- Screener / Top Movers / Breakouts;
- технические alerts;
- открытие торговых сессий Tokyo, London, New York.

Публичный канал должен давать не просто поток заголовков, а отобранную картину рынка. Качество, relevance, freshness и источники важнее частоты.

## 3.2 Персональный Telegram-бот — Personal Intelligence Terminal

Назначение: индивидуальные инструменты пользователя.

Функции, заявленные в текущем ROADMAP:
- портфель: добавление/удаление активов и анализ;
- watchlist;
- новости по выбранным тикерам;
- price alerts и smart alerts;
- графики и статистика;
- сравнение до пяти тикеров;
- backtesting long/short;
- AI Trade Ideas на основе RSI/SMA/momentum;
- фундаментальные данные;
- peers / сравнение конкурентов;
- analysts / данные об ожиданиях аналитиков;
- интерактивные подсказки для новичков;
- обратная связь администратору.

**Важно:** ROADMAP описывает заявленный статус функций, но перед изменением или обещанием пользователю проверяй каждую команду и сценарий в исходном коде и тестах. Наличие пункта в ROADMAP не гарантирует корректную работу в production.

## 3.3 Telegram Mini App / Web Terminal — будущее

Это целевая визуальная оболочка, не считать реализованной без соответствующего frontend-кода и deployment.

Предполагаемые разделы:
1. **Home / Market Overview:** глобальные индексы, основные активы, рыночный пульс, ключевые события.
2. **Markets / Asset Terminal:** тикер, график, price history, technicals, fundamentals, peers, analyst estimates.
3. **News Intelligence:** события, источники, затронутые активы, impact map, timeline.
4. **Portfolio:** позиции, allocation, P&L, exposure, risk, события по портфелю.
5. **AI Research / AI Lab:** запросы к аналитическим агентам, исследования и сценарии.
6. **Market Analytics:** секторы, heatmap, macro, sentiment, breadth, market regime.
7. **Alerts:** правила, уровни, события, расписание и управление уведомлениями.
8. **History / Track Record:** прошлые рекомендации, исходные условия, результаты и статистика.

Базовая UX-идея:
- Apple-inspired: спокойный премиальный минимализм, чёткая типографика, чистая иерархия, пространство, аккуратные графики.
- Bloomberg-inspired по глубине и связности аналитики, но не копировать проприетарный интерфейс или контент.
- Сложная информация должна быть доступна по углублению, а не сразу перегружать главный экран.
- Telegram bot остаётся быстрым командным/notification-интерфейсом; Mini App — богатым визуальным терминалом.

---

# 4. Текущая техническая архитектура (по репозиторию)

## 4.1 Общая схема

Текущая реализация — Python application, запускаемая через `python main.py`. В одном Render web service совмещены Telegram bot и Flask web/status interface. Планировщик APScheduler выполняет периодические задачи. Новости собираются из RSS и дополнительного Finnhub endpoint. AI-анализ проходит через провайдерную цепочку. Результаты публикуются в Telegram, а данные хранятся через DB compatibility layer.

Упрощённый pipeline:

```
RSS feeds + Finnhub
        |
        v
Source fetch / cache / retry / source diagnostics
        |
        v
Normalize news item + source metadata + published timestamp
        |
        v
Archive / persist news state
        |
        v
Exact + text + event deduplication
        |
        v
AI relevance + classification + market impact + scenario
        |
        +------> optional critic for selected high-impact items
        |
        v
Ticker / chart / media resolution
        |
        v
Telegram formatting + publication
        |
        +------> recommendation ledger / track record
        |
        v
Scheduled digests, dashboards, alerts and reports
```

## 4.2 Основные файлы и ответственность

| Файл/каталог | Роль |
|---|---|
| `main.py` | Точка входа, запуск Telegram application, Flask dashboard/status, admin commands и инициализация |
| `config/config.py` | Environment variables, модели AI, провайдеры, RSS_FEEDS, DB_PATH |
| `modules/news_sources.py` | RSS + Finnhub ingestion, concurrent fetch, cache, cooldown, source diagnostics |
| `modules/ai_analyzer.py` | Structured AI analysis, provider fallback, parsing, usage logs, cooldown |
| `modules/critic.py` | Независимая критика отдельных высокозначимых рекомендаций |
| `modules/pipeline.py` | Основной orchestration: сбор, анализ, публикации, отчёты, track record |
| `modules/scheduler.py` | APScheduler jobs, расписание в Europe/Moscow |
| `modules/storage.py` | Persistence: новости, публикации, статистика, рекомендации, портфель/watchlist/alerts |
| `modules/db_compat.py` | SQLite/PostgreSQL compatibility adapter |
| `modules/dedup.py` | Дедупликация новостей/событий через Upstash Redis либо SQLite fallback |
| `modules/charting.py` | Получение котировок/графиков и fallback-рендеринг |
| `modules/media.py` | Подбор изображений и генерация fallback-карточек |
| `modules/formatter.py` | HTML formatting и карточки сообщений |
| `modules/telegram_sender.py` | Отправка сообщений в Telegram |
| `modules/alert_checker.py` | Проверка пользовательских alerts |
| `modules/track_record.py` | Горизонты оценки рекомендаций и логика track record |
| `modules/telegram_monitor.py` | Дополнительный мониторинг Telegram-каналов через Telethon, если настроен |
| `migrations/` | Версионированные SQL migrations |
| `tests/` | Регрессионные и модульные тесты — проверить фактический состав перед работой |
| `assets/` | Статичные медиа/stub assets |

Не считай эту таблицу исчерпывающей: перед работой изучай актуальную файловую структуру.

---

# 5. Сервисы, базы данных и интеграции

## 5.1 Hosting / code / database

| Сервис | Роль | Что подтверждено | Что нужно проверить |
|---|---|---|---|
| GitHub | Исходный код, PR, commits, документация | Репозиторий `murphy2344/TRIADA-INV`, основная ветка `main` | Текущий HEAD, незакоммиченные изменения, открытые PR |
| Render | Hosting Python app | В `render.yaml` описан один Python web service `triada-investing-bot`, free plan, start `python main.py` | Текущий deploy, health, deployed SHA, logs, RAM/CPU, env vars presence (не значения) |
| Neon | PostgreSQL managed DB | В коде есть PostgreSQL path через `DATABASE_URL`, миграция `migrations/001_initial_postgres.sql`; исторически Neon выбран для production | Какой Neon project/branch реально указан в Render, статус compute, schema, backup, connection |
| SQLite | Локальный/fallback storage | `DB_PATH = data/bot.db`; если `DATABASE_URL` не начинается с postgres URL, adapter использует SQLite | Не считать SQLite production primary, пока не проверены env vars и runtime logs |
| Upstash Redis | Dedup/cache/locks | `modules/dedup.py` использует REST API при наличии URL+token; fallback — SQLite | Наличие двух env vars и фактическое использование в runtime; Redis не является основной реляционной БД |

### Database design notes

- Переключение на PostgreSQL происходит в `modules/db_compat.py`, если `DATABASE_URL` начинается с `postgres://` или `postgresql://`.
- Иначе используется SQLite файл `data/bot.db`.
- PostgreSQL schema инициализируется из `migrations/001_initial_postgres.sql`.
- SQLite fallback использует `aiosqlite`.
- PostgreSQL driver: `psycopg[binary]`, async connection.
- Compatibility layer транслирует qmark placeholders `?` в `%s`, часть SQLite datetime expressions и `INSERT OR IGNORE`.
- Это хрупкая зона: не добавляй сложные SQLite-specific SQL конструкции без проверки PostgreSQL-пути.
- Не называй SQLite backup автоматически синхронизированной резервной копией PostgreSQL. В коде это fallback path, а не полноценная репликация.
- Upstash хранит дедупликационные ключи, недавние заголовки и distributed locks. Он не заменяет Neon/PostgreSQL.
- Не выполняй destructive SQL, truncate, reset, schema drop или migration на production без явного согласования.

### Основные таблицы (по storage implementation/migrations; перепроверяй актуальную схему)

- `published_news` — опубликованные новости и metadata публикации.
- `news_items` — архив/очередь новостей, source metadata, processing status, analysis JSON, retry count.
- `bot_stats` — ежедневные счётчики постов и ошибок.
- `recommendations` — направление, тикер, цена на входе, время, категория, confidence, source, horizon, итоговая цена, correctness/PnL/drawdown fields.
- `bot_meta` — служебные ключи/значения, например Telegram message metadata.
- `user_portfolios` — пользовательские позиции.
- `user_watchlists` — списки наблюдения.
- `user_alerts` — пользовательские price/smart alerts.
- Дополнительные таблицы могут быть в migration и последующих изменениях.

## 5.2 AI providers

| Провайдер | Использование в коде | Статус |
|---|---|---|
| Groq | AI analysis через Groq SDK; модели настраиваются environment variables, текущие defaults в config — `openai/gpt-oss-120b` и `openai/gpt-oss-20b` | Интеграция в коде; фактическая доступность ключа/квоты нужно проверить |
| Google Gemini | AI analysis через Gemini generateContent REST API; defaults в текущем config: `gemini-3.8-flash`, fallback `gemini-3.5-flash-lite` | Интеграция в коде; фактическая доступность ключа/квоты нужно проверить |
| OpenAI SDK | `openai` присутствует в requirements; наличие зависимости не доказывает использование OpenAI API в production | Не считать активным AI provider без проверки импортов/call sites и env |

AI architecture:
- structured JSON output;
- relevance gate / skip;
- categories: macro, earnings, geopolitics, corporate, central_bank, commodity, regulatory, bonds;
- impact: critical/high/medium/low;
- confidence;
- source reliability;
- affected assets;
- summary, impact, scenario, recommendation, risk;
- chart ticker / chart-needed fields;
- fallback between providers/models;
- process-local provider cooldowns;
- AI usage log with provider, model, latency, token counts, status and approximate cost where pricing mapping exists.

**Не утверждай, что Gemini всегда primary или Groq всегда primary:** текущая цепочка и комментарии менялись. Прочитай актуальный `modules/ai_analyzer.py` и config перед любым изменением порядка. Не считай оценку Groq cost полной стоимостью продукта; Gemini pricing may differ and must not be guessed.

## 5.3 News sources: RSS feeds

В текущем `config/config.py` задекларированы следующие RSS_FEEDS (20 источников):

1. Investing.com — `https://www.investing.com/rss/news.rss`
2. ForexLive — `https://www.forexlive.com/feed/news`
3. CNBC Markets — `https://www.cnbc.com/id/100003114/device/rss/rss.html`
4. WSJ Business — `https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml`
5. Bloomberg Markets — `https://feeds.bloomberg.com/markets/news.rss`
6. Bloomberg Politics — `https://feeds.bloomberg.com/politics/news.rss`
7. MarketWatch — `https://www.marketwatch.com/rss/topstories`
8. Financial Times — `https://www.ft.com/?format=rss`
9. Abnormal Returns — `https://abnormalreturns.com/feed`
10. Seeking Alpha — `https://seekingalpha.com/feed.xml`
11. AP Business — `https://flipboard.com/@associatedpress/business-and-finance-pbj3bpclz.rss`
12. Federal Reserve — `https://www.federalreserve.gov/feeds/press_all.xml`
13. European Central Bank — `https://www.ecb.europa.eu/rss/press.html`
14. IMF News — `https://www.imf.org/en/News/rss?language_id=1`
15. World Bank Blogs — `https://blogs.worldbank.org/feed`
16. US Energy Information Administration — `https://www.eia.gov/rss/todayinenergy.xml`
17. US Public Debt / TreasuryDirect — `https://www.treasurydirect.gov/rss/mspd.xml`
18. BIS — `https://www.bis.org/doclist/all_pressrels.rss`
19. BIS Data Releases — `https://data.bis.org/feed.xml`
20. US Treasury Auctions — `https://www.treasurydirect.gov/TA_WS/securities/announced/rss`

Дополнительно:
- Finnhub general news endpoint: `https://finnhub.io/api/v1/news`, category `general`, используется при наличии `FINNHUB_API_KEY`.
- `news_sources.py` использует concurrent bounded fetch, timeout, per-feed cooldown, host cooldown при 429, ETag/Last-Modified conditional requests, last-known-good in-memory cache, source diagnostics и corroborating-source metadata.
- RSS sources в config — это список настроенных endpoint-ов в коде. Это не подтверждение, что все они отвечают сегодня или что все публикации попадают в канал.
- Отдельно проверяй HTTP 200/304, parsing, freshness, source-level error rate, last success, duplicates, actual published count.
- Некоторые RSS могут иметь ограничения, изменять структуру или быть нестабильными. Не делай одну ленту single point of failure.

## 5.4 Market data / finance providers

| Provider | Роль/след в коде или конфиге | Как трактовать |
|---|---|---|
| Yahoo Finance / yfinance | Price/sparkline/chart data and recommendation entry/exit price paths | Используется в fallback/market data paths; задержка/coverage/limitations должны отображаться |
| Finnhub | General news ingestion; API key in config; дополнительные data use cases нужно проверять по call sites | News integration confirmed in `news_sources.py` |
| Finviz | Chart image fallback/source in `charting.py` | Внешний chart endpoint; возможны placeholders/rate limits; код проверяет размер изображения |
| Chart-IMG | API key config and chart-related implementation in `charting.py` | Проверить актуальный path/ключ/лимиты перед утверждением, что активен в production |
| Alpha Vantage | Optional env var in `config/config.py` and `render.yaml` | Наличие переменной не подтверждает активный call site; проверить поиск по коду |
| Twelve Data | Optional env var in config/Render | Наличие переменной не подтверждает активный call site; проверить поиск по коду |
| FRED | `FRED_API_KEY` config for macro/economic calendar | Проверить актуальный module/call site и фактическое подключение |
| CFTC | COT report data source described by product roadmap/modules | Проверить endpoint, schedule and freshness |
| SEC EDGAR | 13F filings described by roadmap/modules | Проверить current implementation, user-agent, rate policy and data fields |

Никакие данные не должны называться real-time без доказательства лицензии, режима доступа и фактической задержки.

## 5.5 Image / media providers

- RSS article embedded images — первичный кандидат, если доступен.
- Wikimedia Commons API — поиск изображений.
- Wikipedia PageImages API — fallback для изображений сущностей.
- Google Custom Search API (image search) — optional, требует `GOOGLE_CSE_API_KEY` и `GOOGLE_CSE_CX`.
- Pexels — optional, требует `PEXELS_API_KEY`.
- Pixabay — optional, требует `PIXABAY_API_KEY`.
- Pillow — создание брендированных fallback-карточек.
- Matplotlib — fallback chart rendering.

Не утверждай, что каждый API включён. Проверяй secrets presence, logs, call paths и фактический response.

## 5.6 Telegram integrations

- Telegram Bot API через `python-telegram-bot`.
- `BOT_TOKEN` — bot token (secret).
- `CHANNEL_ID` — канал публикаций.
- `GROUP_CHAT_ID` — опциональная forum group.
- `FORUM_TOPIC_IDS` — topic mapping.
- `ADMIN_USERNAME`, `ADMIN_ID` — admin routing.
- Telethon user API monitor — optional; требует `TG_API_ID`, `TG_API_HASH`, `TG_SESSION_STRING`, `TG_MONITOR_CHANNELS`.
- Отсутствие Telegram monitor env/config может отключать эту возможность, но это не должно ломать основной bot pipeline.

---

# 6. Environment variables и подключения

Список по `config/config.py`, `.env.example` и `render.yaml`. Он нужен Claude для понимания, какие подключения предусмотрены. **Не проси пользователя присылать значения секретов в чат и никогда не вставляй значения в код.**

## 6.1 Основные variables

### Telegram
- `BOT_TOKEN` — secret.
- `CHANNEL_ID` — destination channel.
- `GROUP_CHAT_ID` — optional forum group.
- `FORUM_TOPIC_IDS` — optional topic IDs/mapping.
- `ADMIN_USERNAME`, `ADMIN_ID` — admin identity/routing.
- `TG_API_ID`, `TG_API_HASH`, `TG_SESSION_STRING`, `TG_MONITOR_CHANNELS` — optional Telethon monitor.

### Database / cache
- `DATABASE_URL` — PostgreSQL DSN, secret; если пустой или не postgres URL, code path использует SQLite.
- `UPSTASH_REDIS_REST_URL` — Upstash REST URL.
- `UPSTASH_REDIS_REST_TOKEN` — secret.

### AI
- `GEMINI_API_KEY` (или supported aliases `GOOGLE_API_KEY`, `GOOGLE_GEMINI_API_KEY`) — secret.
- `GEMINI_MODEL`.
- `GEMINI_FALLBACK_MODEL`.
- `GROQ_API_KEY` — secret.
- `GROQ_MODEL`.
- `GROQ_FALLBACK_MODEL`.
- Additional model override envs are read in `modules/ai_analyzer.py`; inspect before changing.

### Image search
- `GOOGLE_CSE_API_KEY` — secret.
- `GOOGLE_CSE_CX`.
- `PEXELS_API_KEY` — secret, optional.
- `PIXABAY_API_KEY` — secret, optional.

### Market / macro data
- `FINNHUB_API_KEY` — secret.
- `ALPHA_VANTAGE_API_KEY` — optional.
- `TWELVE_DATA_API_KEY` — optional.
- `CHART_IMG_API_KEY` — optional.
- `FRED_API_KEY` — optional macro data key.

### Runtime
- `DB_PATH` currently defaults in code to `data/bot.db`; do not assume Render disk persistence.
- Render Blueprint uses Python runtime, `pip install -r requirements.txt`, `python main.py`, one free web service.
- Render environment variables in `render.yaml` use `sync: false` for secrets/configuration requiring Dashboard values.

## 6.2 How Claude should verify connections safely

1. Inspect source code to see whether a variable is actually consumed.
2. If Render MCP/CLI is available, inspect service configuration and **only list variable names / whether set**, never values.
3. Check logs for provider success/failure markers with secrets redacted.
4. For database, verify connection health and schema using read-only queries.
5. For Upstash, verify safe ping/read-only status if supported.
6. Do not create new API accounts or rotate keys unless user explicitly asks.
7. If a key is missing, report the exact variable name and where the owner can configure it; do not ask for the value in chat.

---

# 7. Runtime schedule and jobs

The current `modules/scheduler.py` defines APScheduler with timezone `Europe/Moscow` and job defaults:
- `misfire_grace_time=600`;
- `coalesce=True`;
- `max_instances=1`.

Scheduled jobs visible in code include:
- BREAKING polling every 2 minutes;
- HOURLY digest at minute 1;
- MORNING at 08:00 MSK;
- EVENING at 21:00 MSK;
- WEEKLY Sunday at 20:00 MSK;
- MONTHLY last day at 21:30 MSK;
- Tokyo session post 03:00 MSK;
- London session post 11:00 MSK;
- New York session post 17:30 MSK;
- recommendation tracking every hour;
- global market leaders daily 19:00;
- market pulse every 15 minutes;
- weekly economic calendar Monday 09:00;
- today's economic calendar 08:30;
- technical alerts every hour;
- Telegram monitor every 5 minutes;
- earnings digest daily 09:30;
- Earnings Today 08:00;
- Earnings This Week Monday 08:30;
- sector heatmap 23:30;
- COT report Friday 23:00;
- 13F digest Monday 10:00;
- user price alerts every 5 minutes;
- Market Snapshot every 4 hours;
- Screener breakouts 10:00;
- Screener top movers 23:00;
- Fear & Greed dashboard at 09:00 and 20:00;
- additional jobs may be defined later in the file — inspect full scheduler before changing.

**Do not assume these jobs all execute successfully in production.** Confirm scheduler startup, job registration, timezone behavior, missed runs, overlapping work and Render logs.

---

# 8. Product roadmap: what exists, what is desired

## 8.1 Current product maturity

Repository `ROADMAP.md` describes v1.0 as an analytical bot and labels a broad set of functions as implemented. The codebase contains corresponding modules and pipeline paths for many of them. However, there is no current production health check embedded in this document.

A careful current description is:

- A substantial Python Telegram bot exists.
- News ingestion, AI analysis, Telegram publishing, scheduling, persistence, chart/media handling and recommendation tracking are implemented in code.
- The repository also contains code/roadmap for market dashboards, portfolio/watchlist, alerts, fundamentals, peer comparisons, analyst data, COT/13F, screeners and other reports.
- Each user-facing capability still needs a current code-path + test + production verification before being called fully operational.
- Telegram Mini App and full web terminal are future product surfaces, not confirmed as deployed.
- Trade execution through Alpaca/IBKR is not confirmed as implemented.
- Real-time WebSocket / Level 2 / tick-by-tick feeds are not confirmed as implemented.

## 8.2 Immediate engineering priorities (from historical audit and current project direction)

### P0 — Establish production truth
- Verify actual Render service status, current deployed commit and recent deploy history.
- Verify Neon connection and database schema.
- Verify all scheduler jobs start and run.
- Verify Telegram publishing and admin notifications.
- Establish a repeatable post-deploy smoke test.
- Record actual provider availability without exposing secrets.

### P1 — News queue correctness and freshness
- Old archived news must never starve fresh high-value news.
- Separate live-news eligibility from archival storage.
- Apply bounded retry/backoff and maximum retry policies.
- Prioritize both freshness and materiality.
- Make retryable AI-provider failures remain retryable rather than permanently failed.
- Prevent stale cached RSS items from being republished as current events.
- Test 72-hour live-news eligibility policy and boundary conditions if still present in current branch.
- Keep source-level diagnostics: last success, response status, parse errors, freshness, cooldown.

### P2 — AI resilience and quality
- Explicit provider/model fallback policy.
- Differentiate 429 quota, daily quota, 5xx, timeout, malformed JSON and semantic validation failure.
- Backoff without blocking the event loop.
- Avoid repeated AI calls for same item.
- Validate JSON schema and mandatory fields.
- Store model/version and prompt version for each analysis.
- Do not treat multiple syndicated copies as independent confirmation.
- AI must distinguish verified facts from reported claims and hypotheses.
- Measure quality, not only successful API call count.

### P3 — RAM and runtime stability
Historical Render report found memory peaks close to the free instance limit (~99.3%). Treat this as a serious risk until fresh metrics prove otherwise.
- inspect memory growth across scheduled jobs;
- inspect Matplotlib figure cleanup and image buffers;
- inspect concurrent RSS fetch limits and caches;
- avoid unbounded in-memory lists/dicts;
- lazy-load heavy libraries;
- profile before optimizing;
- don't simply lower functionality without measurement.

### P4 — Publication quality
Historical report showed BREAKING dominated publication volume (~89% in the sampled four-day window). This is a quality problem to investigate:
- stricter significance thresholds;
- separate urgent events from routine company/news items;
- event-level deduplication;
- update existing event timeline instead of repeat posts;
- ensure a digest does not re-publish BREAKING items;
- monitor publication mix and source distribution.

### P5 — Recommendation evaluation integrity
Current baseline has direction-based recommendation checks, but this is not a full investment performance system.
Improve:
- immutable signal snapshot at publication;
- entry price source/time;
- exit/evaluation price source/time;
- horizon per category and explicit timezone;
- benchmark return;
- transaction cost/slippage assumptions;
- realized return and max adverse/favorable excursion where feasible;
- risk-adjusted metrics;
- separate direction accuracy from return/profitability;
- confidence calibration;
- open/unresolved/expired statuses;
- avoid counting signals with missing price data as failures or successes;
- avoid cherry-picking.
Historical sample (12–16 Nov 2026): 385 recommendations created; 168 checked (103 correct / 65 incorrect), 217 untested; 61.3% accuracy among checked; mean PnL +0.156%, median +0.379%. This is a dated, small and methodologically incomplete snapshot, not proof of predictive edge.

### P6 — User analytics and privacy
- collect only minimal telemetry needed to understand active users and feature adoption;
- measure commands/features, active users, cohorts and retention;
- don't store unnecessary personal data;
- define retention and access policy;
- don't infer total audience from partial tables such as watchlists/portfolios.

### P7 — Mini App foundations
Only after the backend contracts and core data quality are stable:
- define API boundary between Telegram bot, backend and frontend;
- design auth through Telegram WebApp initData validation (server-side);
- use typed request/response schemas;
- create mobile-first design system;
- interactive charting and portfolio views;
- ensure user data isolation and access control;
- add frontend tests and API contract tests;
- do not put provider secrets in frontend.

## 8.3 Longer-term roadmap ideas

These are strategic possibilities, not current implementation commitments:

1. Alpaca integration and paper trading; real order execution only after legal, security and risk review.
2. Interactive Brokers integration for broader market access.
3. Real-time WebSocket quotes and streaming alerts.
4. Level 2 order book and time & sales, subject to licensing and provider cost.
5. Supply chain / customer / supplier graph from SEC filings.
6. Institutional ownership, fund holdings and ownership changes.
7. Index membership and weights.
8. Options chain, Greeks, implied volatility, options strategies and unusual activity.
9. Alternative data: shipping, satellite imagery, social sentiment, job postings, app downloads, flight data — only where lawful, reliable, affordable and useful.
10. Full web platform and Telegram Mini App.
11. Shared identity, preferences, billing, analytics and AI orchestration for future TRIADA Group products.

Do not implement expensive or complex data sources before core accuracy, reliability and user value are established.

---

# 9. Design and user experience

## 9.1 Visual direction

- Apple Stocks / Apple-inspired clarity for charts and cards.
- Premium dark interface as a strong initial direction.
- Minimal visual noise, generous spacing, precise typography.
- Restrained green/red semantics for market movement.
- No decorative charts without useful data.
- Consistent numbers, currency, units, precision and timestamps.
- Strong information hierarchy: key metric → change → chart → context → detail.
- Avoid excessive emojis, dense blocks and random colors.
- Interface should feel like a professional tool, not a noisy signal channel.

## 9.2 Chart rules

- Never invent a price, percentage, chart point, volume or technical level.
- Show symbol, exchange where known, currency, interval and timestamp.
- Clearly label delayed or unavailable data.
- If provider fails, use fallback and log source; if no trustworthy data, show unavailable rather than fake chart.
- Charts must be readable on a phone.
- Always close Matplotlib figures and release buffers.
- Keep chart styles consistent across Telegram cards and future Mini App.

## 9.3 Analytical output quality

Every meaningful event analysis should answer, where data is available:
1. What happened? (facts)
2. When did it happen? (event time)
3. Which source confirms it? (source and URL)
4. What changed versus expectations? (consensus vs actual)
5. Which assets are affected, and why?
6. What is the transmission mechanism?
7. What is already priced in / what is unknown?
8. What is the base case and alternative scenario?
9. What catalysts are next?
10. What invalidates the thesis?
11. What is the timeframe?
12. What are the risks?
13. What data is missing?
14. How will the outcome be measured?

---

# 10. Known historical engineering changes and reports

This section is historical context. Verify current code before modifying or assuming live state.

## 10.1 PR #51 — merged

Earlier stability changes included:
- pending news order changed to oldest-first;
- news priority scoring changed to oldest-first;
- Groq TPD cooldown increased to 22 hours;
- other 429 cooldown set to 30 minutes.

Commit recorded in project history: `e7726ad201645ce3b7d6753ebe62d24b493b3aaa`.

Important follow-up insight: pure oldest-first ordering can allow old backlog to dominate fresh news. Queue fairness must include age eligibility, archive/live separation, retry cap and priority.

## 10.2 PR #52 / #53 — historical changes

Existing project context records:
- PR #52: retry/backoff resilience, 72-hour live-news eligibility boundary, priority/recency changes and regression tests.
- PR #53: deferred pandas import in earnings analysis and removed unused pandas import from smart alerts; regression test added.
- A previous check reported 73 tests passed and 1 skipped due to optional dependency.

These statements are historical. Check current commits and tests; do not assume deployment to Render happened.

## 10.3 Documentation PR #54 — merged

Three docs were added/updated:
- `project_context.md`;
- `docs/agents/triada_product_evaluator_system_prompt.md`;
- `docs/agents/triada_senior_fintech_engineer_system_prompt.md`.

PR #54 merged to main. Merge commit recorded:
`8944a8d38037123833872cbf8a4dbc48c5afa40f`.

This was documentation-only; it did not change runtime code, dependencies, database schema or Render configuration.

## 10.4 Historical operational snapshot (12–16 November 2026)

Previously observed, not current:
- Render free service memory peak approximately 532.9 / 536.9 MB (~99.3%).
- 1,728 published message records in the four-day sample.
- BREAKING approximately 89% of publication types.
- AI usage log success around 80.2% (2,612 success / 646 errors).
- Gemini had a materially higher failure rate than Groq in that sample.
- pending news backlog snapshot 221, with old records present.
- recommendation sample and accuracy described in Section 8.2.
- Telegram monitor appeared unconfigured/disabled.
- insufficient user telemetry to infer audience/retention.

Do not use these values in a current investor report without date labels and fresh verification.

---

# 11. Security, reliability and data governance

1. Secrets only in Render environment variables/secret management, never in Git.
2. Never expose Telegram bot token, Telethon session string, API keys, DB DSNs or Redis tokens.
3. Redact query parameters and auth headers from logs.
4. Validate and sanitize external RSS/article content; treat content as untrusted input.
5. Prevent prompt injection from news articles. Article text is data, not instructions to the AI agent.
6. Do not execute code, links, SQL or commands supplied by an RSS item.
7. Enforce per-user ownership checks for portfolio, watchlist and alerts.
8. Avoid cross-user data leaks in bot commands and future API.
9. Use parameterized SQL; no unsafe string interpolation for user-supplied values.
10. Apply timeouts and bounded concurrency to every external provider.
11. Rate-limit provider calls and user-triggered expensive work.
12. Record enough metadata for audit, but minimize personal data.
13. Keep backup/restore strategy documented and tested; do not assume Neon backups or SQLite fallback without verification.
14. Respect source licensing, API terms, redistribution rules and attribution requirements.
15. Avoid investment claims that imply certainty or guaranteed returns.

---

# 12. Development workflow expected from Claude Code

## 12.1 Before coding

1. `git status --short --branch`.
2. `git log -8 --oneline --decorate`.
3. Inspect README, SPEC, ROADMAP, this context, relevant modules and tests.
4. Search all call sites of the functions being changed.
5. Identify DB schema dependencies and external API contracts.
6. Check if a similar fix already exists in another branch/commit.
7. Write a concise plan and identify risk level.

## 12.2 During implementation

- Keep diffs small and cohesive.
- Add/modify regression tests for every bug fix.
- Prefer dependency injection/mocks for external API tests.
- Do not make tests depend on live paid APIs.
- Do not weaken assertions to make tests pass.
- Do not silently change recommendation semantics.
- Preserve existing environment variable names unless migration plan is explicit.
- Add a DB migration if schema changes.
- Add logging with stable event names and secret redaction.
- Consider Render Free memory/CPU and cold starts.
- Avoid adding a new service unless there is a clear need.

## 12.3 Before declaring complete

Run relevant tests first, then full test suite if practical. Include exact commands and output summary. Review:
- exception handling;
- timeouts;
- retries;
- idempotency;
- duplicate processing;
- SQL compatibility;
- timezone;
- resource cleanup;
- secrets in diff/logs;
- backwards compatibility.

## 12.4 Git and deployment

- Use a dedicated feature branch for non-trivial work.
- Do not push directly to `main` for risky changes.
- Create a PR with summary, motivation, tests, risks and rollout notes.
- Merge only when checks pass and change is reviewed.
- Deploy only when requested/appropriate.
- After deployment, verify Render deploy ID, deployed commit SHA, logs, service health, scheduler activity, database connectivity and Telegram delivery.
- A successful GitHub merge is not proof of successful production deployment.

---

# 13. Product and architecture decisions — do not silently reverse

1. TRIADA-INV focuses on global financial markets; Russian market instruments are excluded.
2. Product north star is “Bloomberg Terminal in Telegram” with Apple-inspired UX.
3. Public channel and personal bot have different jobs: public market radar vs personal intelligence terminal.
4. Telegram Mini App/web terminal is a future richer surface; do not claim it is already built.
5. PostgreSQL/Neon is the intended primary relational production storage when `DATABASE_URL` is configured; SQLite is fallback/local path.
6. Upstash Redis is for deduplication/cache/locks, not the primary relational database.
7. Prefer free/low-cost services initially; paid data requires approval.
8. Do not claim real-time data unless proven.
9. Recommendation performance must be measured honestly, not marketed from a weak sample.
10. News volume is not the success metric; relevance, freshness, evidence and usefulness are.
11. Preserve working functionality and avoid broad rewrites.
12. AI agents/roles (Apollo, Athena, Hermes, Argus) are strategic/product concepts; verify concrete implementations and responsibilities in current code before claiming they exist as autonomous production agents.

---

# 14. AI agent concepts within the TRIADA vision

The founder has discussed a multi-agent ecosystem. Treat the following as working role definitions, not proof of deployed agents:

- **Apollo:** analytical engine — structured market/company/event analysis, data interpretation and forecasts/scenarios.
- **Athena:** strategy/research — broader strategic reasoning, investment thesis, portfolio-level context and critique.
- **Hermes:** arbiter/orchestrator — consistency checks, conflict resolution, routing and final synthesis.
- **Argus:** monitoring/observation concept — market, event, source or risk surveillance; exact responsibility requires founder confirmation.

Agent design principles:
- specialized responsibilities;
- shared verified data context;
- explicit schemas and contracts;
- source traceability;
- no fabricated facts;
- critic/independent validation for high-impact conclusions;
- model/provider fallback;
- cost and latency budgets;
- reproducible prompt/version tracking;
- human override for consequential actions.

Do not create four agents just for branding. Each agent must provide a distinct measurable capability and must not multiply token cost without product value.

---

# 15. What to do first after loading this file

Claude Code should not immediately start implementing every roadmap item. Begin with a **read-only technical orientation and reality audit**.

Deliver:
1. Current Git branch, HEAD commit, worktree status.
2. Full repository map and architecture summary.
3. Inventory of all commands/features and their implementation locations.
4. Inventory of all API integrations: exact call sites, optional/required variables, active/fallback paths.
5. Exact RSS feed list and health/diagnostic approach.
6. Database audit: current adapter, migrations, tables, indexes, PostgreSQL/SQLite compatibility risks.
7. Scheduler job inventory and possible overlap/misfire risks.
8. Test inventory and current test results.
9. Render deployment model and what can/cannot be verified from available access.
10. List of discrepancies between README/SPEC/ROADMAP/context and source code.
11. Ranked engineering backlog with severity, impact, complexity and dependencies.
12. A recommended first implementation slice with tests and rollback strategy.

**Do not change files during this initial audit unless the founder explicitly asks.** First return the audit and a prioritized plan. Then implement one approved/clearly prioritized task at a time.

---

# 16. Source-of-truth references

Read these files in the repository before major work:
- `SPEC.md` — current intended technical behavior and architecture notes.
- `ROADMAP.md` — product features and planned phases; verify status against code.
- `project_context.md` — company/product strategy and historical project context.
- `docs/agents/triada_product_evaluator_system_prompt.md` — product/investment evaluator role.
- `docs/agents/triada_senior_fintech_engineer_system_prompt.md` — engineering standards.
- `render.yaml` — Render service blueprint.
- `.env.example` — variable names only; sample values are placeholders and must never be used as real credentials.
- `requirements.txt` — Python dependency declarations.
- `config/config.py` — runtime configuration and RSS list.
- `modules/db_compat.py`, `modules/storage.py`, `migrations/` — persistence behavior.
- `modules/news_sources.py`, `modules/ai_analyzer.py`, `modules/pipeline.py`, `modules/scheduler.py` — core news and AI pipeline.

Useful repository:
https://github.com/murphy2344/TRIADA-INV

---

# 17. Final instruction to Claude Code

Treat TRIADA-INV as a serious long-term fintech product, not a toy Telegram bot. The founder's ambition is to build a trusted financial intelligence terminal that can grow into a major product within TRIADA Group.

Your job is to protect the integrity of that ambition through engineering discipline:
- understand before changing;
- verify before claiming;
- measure before optimizing;
- make small changes with tests;
- preserve the existing system;
- keep infrastructure and API costs controlled;
- prioritize reliability and analytical trust;
- make the product easier to use without making the analysis shallow.

**Never confuse the founder's vision with shipped functionality. Never confuse code existing with production working. Never confuse an AI-generated opinion with verified financial research.**
