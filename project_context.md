# TRIADA Group / TRIADA-INV — Project Context & Ecosystem Passport

> **Document purpose:** canonical product, business, architecture and operating context for human collaborators and AI agents.
> **Status date:** 17 November 2026.
> **Repository:** `murphy2344/TRIADA-INV`.
> **Rule:** this document separates (A) facts confirmed by the repository/current project history, (B) the founder's stated strategic direction, and (C) proposals that still require validation. A roadmap item is not a shipped feature. A code path is not proof of healthy production behavior.

---

## 0. Executive summary

**TRIADA Group** is the umbrella identity and intended company/ecosystem. **TRIADA-INV** is its first major product direction: a global financial intelligence and investment-analysis platform, initially delivered through Telegram and designed to evolve into a richer Telegram Mini App/web terminal.

The central product ambition is:

> **“Bloomberg Terminal in Telegram” — institutional-style financial context and analytical workflows, made radically faster and simpler to access, understand and act on from a smartphone.**

This is a product ambition, not a claim that TRIADA currently has Bloomberg-equivalent data coverage, latency, licensing, execution infrastructure or institutional research quality.

The product must combine three qualities:
1. **Analytical depth:** relevant market data, fundamentals, technical context, catalysts, scenarios, risk and evidence.
2. **Trustworthiness:** every material number and recommendation is traceable to a source, timestamp, method and evaluation horizon.
3. **Exceptional usability:** a calm, minimal, premium interface that makes complex information immediately legible.

The current strategic transition is from “a bot that generates and publishes a lot of content” to “a financial intelligence system that produces timely, relevant, explainable and historically testable analysis.”

---

# PART I — COMPANY & PRODUCT STRATEGY

## 1. TRIADA Group: company identity

### 1.1 What is confirmed and what is not

The founder has described TRIADA Group as the broader company/umbrella behind a future ecosystem, with TRIADA-INV as a product within it. The full corporate charter, legal structure, official mission statement, registered business scope, final brand book and revenue model have not been supplied in the accessible project record.

Therefore, the following is a **strategic formulation derived from the founder's product vision**, suitable as a working draft. It must not be represented as an already approved legal or corporate statement.

### 1.2 Working philosophy

**Make sophisticated systems feel simple without making them simplistic.**

TRIADA should build products that:
- remove friction between a person and a complex body of information;
- turn fragmented data into coherent, useful decisions;
- privilege evidence, precision and clarity over volume and spectacle;
- make advanced capabilities accessible through thoughtful product design;
- treat reliability, privacy, transparency and consistency as product features;
- scale through reusable technology and a coherent ecosystem, not disconnected one-off tools.

### 1.3 Working mission

**To build an ecosystem of intelligent digital products that compresses the distance between complex information and confident, well-informed action.**

For TRIADA-INV, this means transforming global financial information into timely, verifiable market intelligence and useful personal workflows.

### 1.4 Working positioning

TRIADA Group: a technology/product company developing an integrated ecosystem of intelligent services.

TRIADA-INV: a global market intelligence and investment-analysis product combining news, market data, AI-assisted research, technical/fundamental analysis, portfolio context and alerts in a mobile-first experience.

Do not position TRIADA-INV as:
- a guaranteed-profit system;
- an oracle that predicts prices with certainty;
- a broker or exchange unless regulated execution capabilities are actually implemented;
- a Bloomberg replacement in terms of licensed data, institutional coverage or professional terminal infrastructure;
- an AI text generator whose output is treated as research without verification.

### 1.5 Relationship between TRIADA Group and TRIADA-INV

- **TRIADA Group** owns the long-term brand, product philosophy, shared technical standards and ecosystem strategy.
- **TRIADA-INV** is the initial vertical/product proving those standards in financial intelligence.
- Shared capabilities should eventually include identity, user preferences, notifications, analytics, access control, billing, design system, AI orchestration, auditability and data governance.
- TRIADA-INV should be architected as a product that can grow independently while reusing ecosystem-level services.
- Avoid premature microservices or abstractions: establish clean module boundaries and stable contracts first; extract shared services only when a second product genuinely needs them.

### 1.6 Company principles

1. **Evidence before confidence.** No unsupported numbers, fabricated sources or invented market events.
2. **Signal over noise.** A smaller number of high-value insights is better than a flood of low-value alerts.
3. **Clarity over complexity.** Sophisticated internal logic; simple external experience.
4. **Reliability before expansion.** Stabilize core ingestion, storage, analysis and delivery before adding expensive features.
5. **Measured performance.** Every recommendation and feature must have observable outcomes.
6. **Modular growth.** New markets, data providers and products should plug into explicit contracts.
7. **Honest limitations.** Display data delay, coverage gaps, confidence and missing inputs.
8. **Capital discipline.** Prefer dependable free/low-cost providers initially; paid data/API services require explicit value justification and budget approval.

---

## 2. TRIADA-INV: Product Vision

### 2.1 Product definition

TRIADA-INV is intended to become a mobile-first global financial intelligence terminal for investors and traders. It should combine:
- global financial news collection and event detection;
- event interpretation and asset-impact mapping;
- market prices, charts and technical indicators;
- company fundamentals and peer comparisons;
- analyst expectations and institutional/ownership information where licensed/public data permits;
- macroeconomic, earnings, regulatory and geopolitical context;
- personalized watchlists, portfolios, alerts and research;
- recommendation tracking, backtesting and risk evaluation.

The product's value is not “AI writes a summary.” Its value is a connected analytical workflow:

**Event → verified facts → affected assets → market context → fundamental/technical setup → scenarios → risk → personalized relevance → observable outcome.**

### 2.2 Core value proposition

For an investor or trader:
- reduce the time required to understand what happened and why it may matter;
- identify which owned or watched assets are affected;
- distinguish material catalysts from routine news;
- see supporting data and counterarguments;
- understand what is known, unknown and delayed;
- review how previous recommendations performed;
- move from a public market overview to a personal portfolio decision context without searching across many disconnected tools.

### 2.3 “Bloomberg Terminal in Telegram”

This is the north-star metaphor for:
- breadth of market context;
- fast retrieval of useful financial information;
- connected news, assets, fundamentals, technicals and portfolio data;
- compact, actionable analytical output;
- access to sophisticated workflows from a smartphone.

It does **not** authorize:
- claiming Bloomberg data rights or equivalent coverage;
- presenting delayed/free quotes as real-time;
- claiming institutional-grade accuracy without validation;
- reproducing Bloomberg's proprietary interface or content;
- giving investment advice as guaranteed outcomes.

The target is **Bloomberg-inspired analytical utility with Apple-inspired interaction design**.

### 2.4 Product experience layers

**Layer A — Public intelligence feed**
- public Telegram channel/group as the market radar;
- global news and market briefings;
- concise event analysis;
- market pulse, sector and macro summaries;
- transparent source attribution and timestamps.

**Layer B — Personal Telegram bot**
- conversational command and notification interface;
- personal watchlist and portfolio;
- personalized alerts and news relevance;
- quick lookups, summaries and compact charts;
- feedback and guided access to deeper research.

**Layer C — Telegram Mini App / Web Terminal**
- richer dashboard for complex workflows;
- interactive charts, tables, filters and comparisons;
- portfolio and watchlist workspace;
- research pages and history;
- responsive, mobile-first layouts;
- bot remains the notification/command entry point; Mini App becomes the visual terminal for complex tasks.

**Layer D — Shared analytical platform**
- ingestion and normalized data layer;
- event/entity/asset graph;
- fundamental, technical, macro and risk engines;
- AI orchestration and critic/evaluation layer;
- recommendation ledger and backtesting;
- user identity, entitlements and product analytics.

The latter layers are target architecture, not all currently deployed.

---

## 3. Product architecture: two Telegram surfaces

### 3.1 Public group/channel — Global News Radar

**Purpose:** continuously monitor global markets and distribute relevant intelligence to the community.

Current/repository-described behavior:
- global RSS news ingestion and Finnhub integration;
- scheduled breaking-news checks;
- hourly, morning, evening, weekly and monthly content;
- selected market dashboards and reports;
- AI relevance classification, categorization, summaries and potential impact;
- charts/media when a valid ticker or relevant asset is available;
- duplicate detection;
- recommendation record creation for eligible directional signals;
- optional independent AI critic for high-impact breaking items.

Expected future behavior:
- classify events by event type, geography, sector, asset and catalyst;
- detect the same underlying event across sources and languages;
- distinguish original reporting from syndicated copies;
- map an event to affected public companies, indices, commodities, FX and crypto;
- show evidence, source quality, timestamps, data freshness and confidence;
- avoid treating every article as breaking news;
- provide corrections/updates as an event evolves;
- link public event intelligence to each user's watchlist and portfolio in the personal bot.

### 3.2 Personal bot — Personal Intelligence Terminal

**Purpose:** make public intelligence and market data relevant to an individual user.

Repository roadmap describes:
- portfolio management;
- watchlists and news related to watched assets;
- price alerts and smart alerts;
- charts and statistics;
- ticker comparisons;
- backtesting;
- AI trade ideas based on indicators/momentum;
- fundamentals;
- peer comparisons;
- analyst information;
- interactive onboarding/help buttons;
- feedback to administrators.

Important status distinction: these capabilities are listed as implemented in ROADMAP.md, but each still requires current production smoke testing, provider validation and UX review before being treated as fully reliable.

Expected personal workflow:
1. User adds assets to watchlist or portfolio.
2. System stores canonical asset identifiers and user-specific context.
3. News events are mapped to those assets.
4. The user receives only relevant, deduplicated alerts.
5. Asset detail presents price/freshness, fundamentals, technical setup, catalysts and risk.
6. User can inspect source evidence and prior signals.
7. Outcomes are tracked against a defined benchmark and horizon.

### 3.3 Mini App / Web terminal

The Mini App is a strategic interface layer, not a replacement for the bot:
- bot: commands, alerts, reminders, quick answers and entry points;
- Mini App: interactive charts, portfolio views, screeners, comparison tables, detailed research and settings;
- web platform: potentially a broader desktop experience and future account/product surface.

Do not begin a large frontend rewrite until API contracts, data models, authentication and core workflows are stable.

---

## 4. Design code — Apple-level clarity

### 4.1 Design principle

**Complexity belongs in the analytical engine; clarity belongs in the interface.**

The product should feel precise, quiet, intentional and premium. Apple is a design reference for hierarchy, restraint, legibility and consistency—not a request to copy proprietary screens.

### 4.2 Visual principles
- minimal visual noise;
- clear hierarchy and generous spacing;
- short, information-dense but readable text;
- consistent typography and numeric alignment;
- carefully limited color semantics;
- charts with legible axes, units, timeframe and source;
- consistent asset identity, ticker, currency and timestamp;
- compact cards that work on narrow smartphone screens;
- predictable navigation and minimal interaction steps;
- accessible contrast and readable font sizes.

### 4.3 Existing repository design direction
The SPEC describes:
- Apple Stocks-inspired custom chart fallback and branded visuals;
- black background for self-rendered fallback graphics;
- green `#30D158` for positive movement and red `#FF453A` for negative movement;
- large price/percentage, thin sparkline and restrained visual treatment;
- a ticker chip only when a real quote was retrieved;
- monospaced numeric presentation for market pulse and key figures.

The external Finviz chart screenshot is explicitly treated differently in the existing specification. Do not assume all charts have already been migrated to a unified native design system.

### 4.4 UX acceptance criteria
A screen/card fails review if:
- the user cannot identify the asset, timeframe, price currency or timestamp;
- a number is shown without source or freshness context where material;
- color is the only indication of positive/negative status;
- a chart is decorative rather than decision-useful;
- the user must read a wall of text to find the conclusion;
- an alert does not explain why it fired;
- a recommendation hides invalidation conditions or downside risk;
- multiple cards repeat the same facts without adding value.

---

# PART II — CURRENT TECHNICAL BASELINE

## 5. Repository and deployment

### 5.1 Source of truth
- GitHub repository: `murphy2344/TRIADA-INV`.
- Core application entry point: `main.py`.
- Main specification: `SPEC.md`.
- Product roadmap: `ROADMAP.md`.
- Runtime/infrastructure manifest: `render.yaml`.
- Python dependency manifest: `requirements.txt`.
- Environment variable template: `.env.example`.
- Main application modules: `modules/`.

The repository also contains Node/TypeScript workspace scaffolding and artifacts. The current bot runtime described by `render.yaml` is Python (`python main.py`). Do not mistake the presence of pnpm/TypeScript scaffolding for a deployed React Mini App or production TypeScript API.

### 5.2 Runtime and frameworks
Confirmed from repository manifests:
- Python runtime, minimum Python 3.11 in `pyproject.toml`;
- python-telegram-bot;
- Flask;
- APScheduler;
- feedparser;
- requests / aiohttp;
- pandas;
- matplotlib / mplfinance;
- yfinance;
- BeautifulSoup / lxml;
- psycopg PostgreSQL driver;
- optional Finnhub SDK;
- optional Telethon for Telegram user/API monitoring;
- Playwright is listed in requirements, although Render config notes Chromium is not required for chart generation.

### 5.3 Hosting
- Render service: `srv-d94l72kvikkc73ckoq40`.
- Render workspace: `tea-d94l4hu7r5hc73f9doq0`.
- Render configuration declares a Free plan and Python web service.
- Start command: `python main.py`.
- The production service has previously been observed as LIVE, but the latest deployment after recent merged changes must be re-verified before claiming current production health.
- Free Render filesystem is ephemeral. Do not treat local SQLite or session files as durable production storage.

### 5.4 Database and cache
- Neon project: `morning-haze-47816489`.
- Production branch referenced in project operations: `br-morning-mode-b5sxh6ie`.
- PostgreSQL/Neon is the intended durable relational store.
- SQLite compatibility/fallback remains in the codebase.
- Upstash Redis is used for deduplication/locking/cache-like functions where configured; SQLite fallback exists.
- Never place credentials, tokens, connection strings or private keys in documentation, prompts, commits or logs.

**Important migration decision:** the PostgreSQL cutover runbook states that historical SQLite records are intentionally not imported. PostgreSQL begins with a fresh schema and new records. Do not attempt to restore or import the old SQLite history unless the founder explicitly reverses that decision.

The migration runbook identifies seven application tables:
- `published_news`;
- `bot_stats`;
- `recommendations`;
- `bot_meta`;
- `user_portfolios`;
- `user_alerts`;
- `user_watchlists`.

The exact live schema must always be inspected before migrations or data changes.

### 5.5 AI providers
Repository configuration describes:
- Google Gemini as primary analysis provider;
- Groq as fallback provider;
- a separate critic path using a different model/role from the primary analyst;
- graceful degradation when optional critic credentials are absent.

Model names are configuration values and can change. Read the current environment/configuration; do not hard-code a stale model name into product assumptions.

### 5.6 Data and content sources
Sources described in code/spec/config include:
- global RSS feeds from financial/news publishers;
- Finnhub;
- Yahoo Finance/yfinance for selected market data/chart fallback;
- Finviz chart pages/screenshots;
- SEC filings / 13F data;
- CFTC COT reports;
- economic calendar sources;
- Wikimedia and optional Google Custom Search, Pexels and Pixabay for media;
- optional Alpha Vantage, Twelve Data and Chart-IMG integrations.

Source presence in code/config does not guarantee a working key, current access, legal reuse rights, sufficient rate limits, real-time delivery or production health. Each source must be checked for current availability, licensing, freshness, coverage and failure behavior.

Twitter/X is deliberately not a default source because the project has avoided its paid API cost. Do not add a paid source without a clear business case and approval.

### 5.7 Core code modules
Current `modules/` includes:
- `news_sources.py` — news ingestion, source selection and priority;
- `ai_analyzer.py` — structured AI analysis and provider fallback;
- `critic.py` — independent critique;
- `pipeline.py` — processing/publication pipeline and track record integration;
- `storage.py` — relational persistence and compatibility;
- `dedup.py` — duplicate detection and optional Redis;
- `scheduler.py` — scheduled jobs;
- `formatter.py` — Telegram content formatting;
- `telegram_sender.py` — message delivery;
- `charting.py`, `media.py` — chart/media generation;
- `track_record.py`, `backtester.py` — recommendation evaluation/backtesting;
- `fundamentals.py`, `portfolio_analyzer.py`, `ticker_compare.py`;
- `market_snapshot.py`, `market_pulse.py`, `market_screener.py`;
- `fear_greed.py`, `sector_performance.py`, `sector_heatmap.py`;
- `econ_calendar.py`, `earnings.py`, `cot_report.py`, `filings_13f.py`;
- `technical_alerts.py`, `smart_alerts.py`, `alert_checker.py`;
- `user_commands.py`, `bot_commands.py`, `watchlist_news.py`, `telegram_monitor.py`.

Always inspect the current implementation before modifying a module. The file list is a map, not proof that every module is active in production.

---

## 6. Existing feature inventory and status discipline

### 6.1 Public/group capabilities listed as implemented in ROADMAP.md
- breaking news;
- hourly digest;
- morning/evening reviews;
- weekly/monthly summaries;
- Fear & Greed dashboard;
- earnings today/this week;
- sector performance/rotation;
- global market snapshot;
- screener/top movers/breakouts;
- COT report;
- 13F filings;
- economic calendar;
- technical alerts (including RSI/SMA);
- sector heatmap.

### 6.2 Personal bot capabilities listed as implemented in ROADMAP.md
- portfolio add/remove/analyze;
- price alerts and smart alerts;
- watchlists with news;
- charts and statistics;
- comparison of up to five tickers;
- long/short backtesting;
- AI trade ideas based on RSI/SMA/momentum;
- company fundamentals;
- peer comparisons;
- analyst information;
- interactive help/onboarding buttons;
- feedback to administrators.

### 6.3 Features explicitly still roadmap/planned
The existing ROADMAP lists, among others:
- Alpaca trading execution and paper trading;
- optional Interactive Brokers integration;
- real-time WebSocket quotes and Level 2 order book;
- supply-chain graph and ownership mapping;
- expanded options chain/Greeks/volatility strategies;
- advanced alternative data (shipping, satellite, social, flights, job postings);
- expanded portfolio risk metrics (VaR, Monte Carlo, drawdown, Sharpe/Sortino);
- factor analysis, pair trading and arbitrage;
- insider and short-interest analytics;
- advanced analyst accuracy tracking;
- premium/pro tiers, payments and referrals;
- expanded crypto, FX, European and Asian exchange coverage;
- deeper ML/predictive analytics;
- Telegram Mini App and richer web interface.

These are aspirations/plans, not current production guarantees. The roadmap's old dates, price points, user-count targets and API references must be revalidated before becoming execution commitments.

---

## 7. Analytical roles and module concepts

The project history has used or discussed AI/agent names including Apollo, Athena, Argus and Hermes. Their final service boundaries are not yet a fully verified, implemented multi-agent architecture. Treat the following as a **working role model**:

- **Apollo — Primary Research Analyst:** extracts structured facts, classifies events, maps affected assets and drafts evidence-based scenarios.
- **Athena — Independent Critic / Risk Reviewer:** challenges Apollo's reasoning, checks missing evidence, alternative explanations, contradictory facts, unsupported causality and risk.
- **Argus — Monitoring / Data Integrity concept:** watches sources, market events, freshness, anomalies, provider failures and changes requiring attention. This role needs formal confirmation before implementation.
- **Hermes — Delivery / Personalization concept:** routes validated intelligence into public posts, user watchlists, portfolios and alerts. This role needs formal confirmation before implementation.

These names should not become decorative labels. Each agent must have a bounded responsibility, explicit input/output schema, traceable evidence and measurable performance.

---

## 8. News and publishing specification

The current SPEC describes:
- BREAKING checks every two minutes;
- HOURLY digest at :01 each hour;
- MORNING at 08:00 Moscow time;
- EVENING at 21:00 Moscow time;
- WEEKLY on Sunday at 20:00 Moscow time;
- MONTHLY on the final day at 21:30 Moscow time;
- market-opening posts for Tokyo, London and New York at configured local/Moscow schedule times.

Current AI structured analysis fields described in SPEC:
- `relevant`;
- `post_type`;
- `category`;
- `subject`;
- `subject_en`;
- `title`;
- `summary`;
- `impact_level`;
- `impact_text`;
- `affected_assets`;
- `scenario`;
- `recommendation`;
- `recommendation_text`;
- `needs_chart`;
- `ticker`.

The `relevant` field is a strict filter. Irrelevant incidents, general social debates and statements without concrete economic/market implications should not become financial alerts.

Anti-duplicate design in SPEC:
1. headline/text similarity;
2. event/topic plus category/subject matching, including cross-source rephrasing.

The system must evolve from article-centric processing toward **event-centric intelligence**: multiple articles may describe one event, and one event may affect multiple assets.

### 8.1 News priority and age
A recent stability change introduced retry/backoff for failed news analysis and improved queue priority/recency handling. A 72-hour live-news cutoff is described in the PR. This behavior was merged but must be checked against the live database and Render logs after deployment.

Rules:
- old/archive news must not starve current news;
- queue processing must be bounded;
- transient provider failures must remain retryable;
- retries must be capped and scheduled with backoff;
- duplicate items must not generate repeated public posts;
- priority must consider both materiality and recency;
- do not silently discard important stories solely because one provider is unavailable.

---

## 9. Recommendation integrity and track record

### 9.1 Existing mechanism
SPEC describes saving an entry price when a directional recommendation (long/short) is published for a ticker, then checking price after a category-specific horizon. Examples include macro, earnings, geopolitics and central-bank event horizons.

This is a starting point, not a complete professional performance framework.

### 9.2 Known limitations
- Direction-only correctness is not equivalent to profitable performance.
- A price move without benchmark, transaction costs, slippage and risk is incomplete.
- Horizons differ by event type and must be explicitly defined.
- Neutral signals should be retained for analytical audit even if not included in directional accuracy.
- Unresolved/untested recommendations must remain visible as such.
- Confidence must be calibrated against observed outcomes.
- Avoid cherry-picking successful signals or silently changing the scoring method.
- Recommendation records need immutable entry context, source evidence, model/prompt version, timestamp, quote source and evaluation method.

### 9.3 Historical snapshot (12–16 November 2026 report)
The prior four-day operational review reported:
- 385 recommendations created in the window;
- 168 checked, 103 correct, 65 incorrect and 217 untested;
- 61.3% accuracy among checked recommendations;
- average confidence about 70.3%;
- mean PnL about +0.156%, median about +0.379%.

These values are a dated snapshot, not a validated long-term edge. They require semantic verification of the evaluator, larger samples, horizon segmentation, benchmark comparison, transaction-cost assumptions, drawdown and confidence calibration.

---

## 10. Current operational baseline and known issues

### 10.1 Dated operational snapshot (12–16 November 2026)
Prior review found:
- 1,728 published message records in the reporting window;
- 2,835 news items first seen during the cohort window;
- approximately 1,340 of those cohort items reached published status;
- the BREAKING publication type represented approximately 89% of published messages;
- AI usage logs showed about 80.2% success across providers in that window;
- Gemini had materially more failures than Groq in that sample;
- at least 2,000 AI_EXHAUSTED log events were observed (not necessarily unique news items);
- current pending collected backlog snapshot: 221, including historical items;
- Render memory reached approximately 532.9 MB of a 536.9 MB limit at one point (about 99.3%);
- CPU was not the primary infrastructure bottleneck in the sampled period;
- Telegram monitoring appeared unconfigured/disabled due to missing TG_* settings or channel configuration;
- available user feature telemetry was insufficient to infer total audience or retention.

These are historical observations from that report, not live metrics.

### 10.2 Main bottlenecks
1. **News quality:** excessive BREAKING volume; significance threshold and event deduplication need refinement.
2. **Timeliness:** old backlog and retries must not delay current high-value events.
3. **AI resilience:** Gemini 503/429/timeouts and Groq quota limits require provider-specific backoff, quota awareness and graceful fallback.
4. **Memory:** near-limit RAM usage risks process restarts/OOM on the current free instance.
5. **Evidence:** AI conclusions must be grounded in source facts and structured market data, not model recall.
6. **Recommendation validation:** current directional checks are too simple for institutional-quality claims.
7. **Observability:** insufficient telemetry for user activity, feature usage, delivery outcomes and retention.
8. **Production verification:** merged code and green CI do not prove Render production is running the intended commit or that scheduled jobs are healthy.

### 10.3 Recent stability work (November 2026)
- PR #52: retry/backoff resilience, 72-hour live-news eligibility boundary, priority/recency fixes and regression tests. Merged to main.
- PR #53: deferred pandas import in earnings analysis and removal of an unused pandas import from smart alerts; added regression test. Merged to main.
- Automated checks were reported green: 73 tests passed and 1 test skipped due to an optional dependency.
- Render rollout and post-deploy production verification were not conclusively established in the last captured operational sequence. Verify before stating these changes are live.

---

## 11. Current focus: trustworthy intelligence, not content volume

The governing product principle is:

> **TRIADA-INV must stop optimizing primarily for how many posts it can publish and start optimizing for how much reliable, timely, decision-useful intelligence it delivers.**

Priority order:
1. production health and safe deployment;
2. database correctness, queue fairness and event freshness;
3. AI provider resilience and cost/quota control;
4. news relevance, significance and event deduplication;
5. structured evidence and asset mapping;
6. recommendation evaluation and backtesting integrity;
7. RAM/CPU/latency observability;
8. privacy-conscious user analytics;
9. UX consistency and Mini App/API foundations;
10. advanced data and monetization only after core trust is established.

### 11.1 Mandatory analysis contract
Every material analysis should contain, where available:
- event identity and event time;
- source name, source URL/reference and retrieval time;
- primary facts separated from interpretation;
- affected assets and the mapping rationale;
- current quote, currency, exchange, timestamp and delay status;
- relevant fundamental metrics with period, units and source;
- technical levels/indicators with timeframe and calculation inputs;
- catalyst and expected mechanism of impact;
- base, upside and downside scenarios;
- invalidation conditions;
- risk factors and counterarguments;
- confidence with a defined meaning;
- missing data and uncertainty;
- evaluation horizon and later outcome record.

If required data is missing, say so. Do not fill gaps with invented numbers.

### 11.2 Global market scope
The product specification explicitly excludes:
- MOEX;
- IMOEX;
- RTS;
- Russian market instruments;
- RUB-denominated instruments;
- Russian market news feeds as product coverage.

Priority market expansion described in roadmap:
- United States;
- Europe;
- Asia;
- global commodities;
- FX;
- crypto.

Do not reintroduce excluded Russian markets through generic screeners, watchlists or source fallbacks.

---

# PART III — ENGINEERING RULES

## 12. Architecture principles for all future development

1. **Inspect before editing.** Read current code, tests, schemas, config and deployment manifests.
2. **Preserve existing behavior.** Avoid rewrites when a focused change is safer.
3. **One source of truth per domain.** Canonical asset IDs, normalized events, quote records and recommendation records.
4. **Provider adapters.** External APIs must sit behind adapters with timeout, retry, rate-limit, freshness and schema validation.
5. **No blocking the pipeline.** A single provider outage must not take down unrelated sources or core bot delivery.
6. **Idempotency.** Repeated scheduled jobs, retries and webhooks must not duplicate posts, trades or recommendation records.
7. **Explicit status transitions.** Collected, queued, analyzed, published, skipped, retryable failure and terminal failure must be distinct.
8. **UTC internally.** Store timestamps in UTC; convert only at presentation boundaries.
9. **Typed/validated outputs.** AI output must be schema-validated and rejected or repaired safely if invalid.
10. **Auditability.** Store source, model/provider, prompt/schema version, timestamps and decision metadata.
11. **Observability.** Structured logs and metrics for each stage; no secrets or personal data in logs.
12. **Resource limits.** Bound queues, concurrency, caches, article text, image sizes and in-memory collections.
13. **Graceful degradation.** Missing optional providers must reduce capability, not crash the product.
14. **No hidden paid dependency.** Check pricing/quotas before introducing a provider.
15. **Tests before merge.** Add regression tests for changed behavior; run offline tests and relevant integration checks.
16. **Deploy safely.** Never claim production success until the deployment status, commit SHA, startup and post-deploy behavior are checked.
17. **No destructive data operations without explicit approval.** No dropping tables, deleting records, rotating secrets, broad IP allowlists or schema resets as incidental cleanup.

## 13. Data integrity rules

- Every price must have instrument, currency, exchange/venue if applicable, timestamp, source and freshness.
- Every fundamental metric must have units, fiscal period, reporting currency, source and retrieval timestamp.
- Corporate actions, splits and currency conversions must be accounted for before calculating returns.
- Never compare ratios from mismatched fiscal periods without flagging the mismatch.
- Distinguish missing, zero, null, stale and provider-error states.
- Keep raw source evidence or a reproducible reference where legally permissible.
- Preserve historical snapshots used by recommendations so future backtests do not use revised data unknowingly.
- Use point-in-time data for backtesting to avoid look-ahead bias.
- Separate observed facts, model inference and user-facing recommendation.

## 14. Security, privacy and compliance

- Secrets only in Render/hosting secret environment variables or a dedicated secret manager.
- Never print bot tokens, API keys, database URLs, Telegram session strings or user credentials.
- Encrypt user broker credentials if trading integrations are ever approved; use least privilege and scoped tokens.
- Do not enable trade execution by default. It requires a separate security, compliance, consent and risk-control review.
- Treat portfolio/watchlist data as private user data.
- Add authentication and authorization before exposing user-specific data through a web API/Mini App.
- Follow data-provider terms, redistribution rights and market-data licensing.
- Make it clear when quotes are delayed or indicative.
- Do not market signals as guaranteed returns or personalized regulated advice without appropriate legal review.

## 15. Definition of done

A change is complete only when:
- implementation is committed;
- tests covering the changed path pass;
- migrations are reviewed and safe;
- error and fallback paths are tested;
- provider limits and free-tier impact are understood;
- CI checks are green;
- deployment status and deployed commit are verified if production deployment is intended;
- post-deploy logs/metrics show expected behavior;
- user-facing claims match observed behavior;
- documentation and this passport are updated where architecture/status changed.

## 16. North-star metrics

Do not optimize a single vanity metric. Track:
- high-significance event precision and recall;
- median and p95 event-to-alert latency;
- percentage of published items with verifiable source evidence;
- duplicate-event rate;
- stale-news publication rate;
- AI structured-output validity rate;
- provider success rate, cooldown time and token/cost usage;
- recommendation performance by horizon and asset class;
- benchmark-relative return, drawdown and risk-adjusted results;
- confidence calibration;
- RAM peak and restart/OOM rate;
- delivery success and alert usefulness;
- active users, feature adoption, retention and notification opt-out rate.

**Final standard:** TRIADA-INV should be trusted because its information is traceable, its uncertainty is explicit, its outcomes are measured and its interface makes the evidence easy to understand.
