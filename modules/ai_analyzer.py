import json
import logging
import os
import re
import time
import threading
from urllib.parse import quote

import requests
from groq import Groq
from config.config import (
    GEMINI_API_KEY,
    GEMINI_FALLBACK_MODEL,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_FALLBACK_MODEL,
    GROQ_MODEL,
)

logger = logging.getLogger(__name__)
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)

# Keep the production chain short: one Gemini attempt, then two Groq models.
# A provider failure advances to the next model immediately; no hidden SDK retries.
PRIMARY_GEMINI_MODEL = os.getenv("TRIADA_AI_PRIMARY_MODEL", GEMINI_MODEL or "gemini-3.8-flash").strip()
PRIMARY_GROQ_MODEL = os.getenv("TRIADA_AI_FALLBACK_MODEL", GROQ_MODEL or "openai/gpt-oss-120b").strip()
SECONDARY_GROQ_MODEL = os.getenv("TRIADA_AI_LAST_RESORT_MODEL", GROQ_FALLBACK_MODEL or "openai/gpt-oss-20b").strip()

# Avoid repeatedly calling providers whose quota is already exhausted.
# Cooldowns are process-local and automatically expire; no external service needed.
_PROVIDER_COOLDOWNS: dict[tuple[str, str], float] = {}
_PROVIDER_COOLDOWN_LOCK = threading.Lock()


def _provider_is_cooling_down(provider: str, model: str) -> bool:
    key = (provider, model)
    now = time.monotonic()
    with _PROVIDER_COOLDOWN_LOCK:
        until = _PROVIDER_COOLDOWNS.get(key, 0.0)
        if until <= now:
            _PROVIDER_COOLDOWNS.pop(key, None)
            return False
        return True


def _set_provider_cooldown(provider: str, model: str, exc: Exception, code: str) -> None:
    message = str(exc).lower()
    if code == "429" or "429" in message or "rate limit" in message or "quota" in message:
        # Daily token quota errors should not be retried every news cycle.
        seconds = 6 * 60 * 60 if ("tokens per day" in message or "tpd" in message) else 10 * 60
    elif code == "503" or "503" in message or "service unavailable" in message:
        seconds = 2 * 60
    else:
        return
    key = (provider, model)
    with _PROVIDER_COOLDOWN_LOCK:
        _PROVIDER_COOLDOWNS[key] = time.monotonic() + seconds
    logger.warning(
        "AI_PROVIDER_COOLDOWN provider=%s model=%s seconds=%d error_code=%s",
        provider, model, seconds, code,
    )


SYSTEM_PROMPT = """You are a senior global financial markets analyst for TRIADA INVESTING.
Return ONLY valid JSON, with no markdown or text outside JSON.
If input is English, translate every user-facing field to Russian. Russian input stays Russian.

Skip sports, entertainment, crime, celebrity news, ordinary accidents and weather unless
there is a direct, specific financial-market impact. Skip corporate announcements without
concrete numbers, dates or market-relevant action. Unconfirmed information has confidence
<= 0.3 and source_reliability="rumor". Skip events older than 7 days. Never invent numbers.
If uncertain, use neutral and confidence below 0.5.

CATEGORIES: macro, earnings, geopolitics, corporate, central_bank, commodity, regulatory, bonds.
IMPACT: critical (>2%), high (1-2%), medium (0.5-1%), low (<0.5%).
TIMEFRAME: intraday, short (1-3d), medium (1-2w), long (1m+).
SIGNAL: long, short, neutral, volatility.

chart_needed is true only for a concrete publicly traded asset. Private companies such as
SpaceX, OpenAI, Anthropic and ByteDance never receive a related public ticker. Use
yfinance-compatible tickers such as BTC-USD, GC=F, CL=F, SI=F, ^GSPC, ^IXIC, ^DJI,
EURUSD=X, RUB=X, AAPL, TSLA, NVDA, MSFT, AMZN, GOOGL, META, JPM, XOM, BP, SHEL and GS.
General macro, politics and geopolitics without a concrete asset use chart_needed=false.
Always provide risk_ru. For central banks provide consensus versus actual when available.
For earnings provide EPS and revenue actual versus estimate when available."""

ANALYSIS_SCHEMA = """{
  "skip": false,
  "headline_ru": "Russian headline, 5-10 words",
  "category": "macro|earnings|geopolitics|corporate|central_bank|commodity|regulatory|bonds",
  "impact": "critical|high|medium|low",
  "confidence": 0.0,
  "source_reliability": "confirmed|partial|rumor",
  "assets": ["SPY", "QQQ", "AAPL"],
  "summary_ru": "2-3 factual sentences in Russian",
  "market_impact_ru": "Market effect in Russian",
  "scenario_ru": "Base and alternative scenario in Russian",
  "signal": "long|short|neutral|volatility",
  "timeframe": "intraday|short|medium|long",
  "rationale_ru": "Reason for the signal in Russian",
  "risk_ru": "Mandatory main risk in Russian",
  "chart_needed": true,
  "chart_ticker": "primary yfinance ticker or null",
  "historical_context": "Prior market reaction if known",
  "consensus": "expectation if applicable",
  "actual": "actual value if applicable"
}"""

# Approximate published Groq token prices, USD per 1M tokens. Gemini costs are
# deliberately not guessed: its price depends on model, tier, and current pricing.
GROQ_PRICE_PER_MILLION = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
}


def _normalize_result(result: dict, category: str) -> dict:
    """Map the AI contract to the existing pipeline contract."""
    if result.get("skip") is True:
        return {"relevant": False, "post_type": "skip"}

    ai_category = result.get("category", "macro")
    category_map = {
        "geopolitics": "geopolitics",
        "corporate": "company",
        "earnings": "company",
        "commodity": "market_move",
        "macro": "market_move",
        "central_bank": "geopolitics",
        "regulatory": "geopolitics",
        "bonds": "market_move",
    }
    ticker = result.get("chart_ticker")
    assets = result.get("assets") or []
    joined = " ".join(str(x).lower() for x in [ticker, *assets])
    if any(x in joined for x in ("btc", "eth", "crypto")):
        asset_class = "crypto"
    elif any(x in joined for x in ("gold", "gc=f", "wti", "oil", "cl=f", "si=f")):
        asset_class = "commodity"
    elif any(x in joined for x in ("usd", "eur", "rub", "forex", "currency")):
        asset_class = "forex"
    elif ticker:
        asset_class = "equity"
    elif ai_category in {"macro", "central_bank", "bonds"}:
        asset_class = "macro"
    else:
        asset_class = "none"

    impact = result.get("impact", "low")
    signal = result.get("signal", "neutral")
    return {
        "relevant": True,
        "post_type": "urgent" if category.upper() == "BREAKING" else "market_move",
        "category": category_map.get(ai_category, "market_move"),
        "ai_category": ai_category,
        "asset_class": asset_class,
        "subject": result.get("headline_ru", ""),
        "subject_en": result.get("headline_ru", ""),
        "title": result.get("headline_ru", ""),
        "summary": result.get("summary_ru", ""),
        "impact_level": "high" if impact == "critical" else impact,
        "impact_text": result.get("market_impact_ru", ""),
        "affected_assets": assets,
        "scenario": result.get("scenario_ru", ""),
        "recommendation": signal if signal in {"long", "short", "neutral"} else "neutral",
        "recommendation_text": result.get("rationale_ru", ""),
        "risk": result.get("risk_ru", ""),
        "confidence": result.get("confidence"),
        "source_reliability": result.get("source_reliability"),
        "timeframe": result.get("timeframe"),
        "needs_chart": bool(result.get("chart_needed") and ticker),
        "ticker": ticker,
    }


def _usage_log(provider: str, model: str, started: float, usage: dict | None,
               status: str, attempt: int, error_code: str = "") -> None:
    elapsed_ms = round((time.monotonic() - started) * 1000)
    usage = usage or {}
    input_tokens = int(usage.get("promptTokenCount") or usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("candidatesTokenCount") or usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("totalTokenCount") or usage.get("total_tokens") or input_tokens + output_tokens)
    cost = None
    prices = GROQ_PRICE_PER_MILLION.get(model) if provider == "Groq" else None
    if prices and (input_tokens or output_tokens):
        cost = round((input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000, 8)
    logger.info(
        "AI_USAGE provider=%s model=%s status=%s attempt=%s latency_ms=%s "
        "input_tokens=%s output_tokens=%s total_tokens=%s estimated_cost_usd=%s error_code=%s",
        provider, model, status, attempt, elapsed_ms, input_tokens, output_tokens,
        total_tokens, cost if cost is not None else "n/a", error_code or "-",
    )


def _http_error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if response is not None:
        return str(getattr(response, "status_code", "HTTP_ERROR"))
    status = getattr(exc, "status_code", None)
    if status:
        return str(status)
    text = str(exc).lower()
    if "timeout" in text or "timed out" in text:
        return "TIMEOUT"
    if "rate_limit" in text or "rate limit" in text or "429" in text:
        return "429"
    return type(exc).__name__


def _analyze_gemini(prompt: str, category: str) -> dict | None:
    if not GEMINI_API_KEY or not PRIMARY_GEMINI_MODEL:
        return None
    started = time.monotonic()
    usage = {}
    try:
        response = requests.post(
            GEMINI_API_URL.format(model=quote(PRIMARY_GEMINI_MODEL, safe="")),
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 2500,
                    "responseMimeType": "application/json",
                },
            },
            timeout=18,
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usageMetadata") or {}
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        result = _normalize_result(json.loads(text), category)
        _usage_log("Gemini", PRIMARY_GEMINI_MODEL, started, usage, "success", 1)
        logger.info("AI_RESULT provider=Gemini model=%s relevant=%s", PRIMARY_GEMINI_MODEL, result.get("relevant"))
        return result
    except Exception as exc:
        code = _http_error_code(exc)
        _set_provider_cooldown("Gemini", PRIMARY_GEMINI_MODEL, exc, code)
        _usage_log("Gemini", PRIMARY_GEMINI_MODEL, started, usage, "error", 1, code)
        logger.warning("AI_FAILOVER provider=Gemini model=%s error_code=%s detail=%s",
                       PRIMARY_GEMINI_MODEL, code, str(exc)[:250])
        return None


def _parse_json_object(raw_text: str) -> dict:
    """Parse a JSON object even if a provider wraps it in Markdown or extra text."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^\`\`\`(?:json)?\\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\\s*\`\`\`$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(text[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("AI response JSON must be an object")
    return parsed


def _analyze_groq(prompt: str, category: str, model: str, attempt: int) -> dict | None:
    if not GROQ_API_KEY or not model:
        return None
    started = time.monotonic()
    usage = {}
    try:
        client = Groq(api_key=GROQ_API_KEY, max_retries=0, timeout=18)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + "\\nKeep every field concise; return one compact JSON object only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            # Give reasoning models enough completion budget to finish valid JSON.
            # Avoid provider-side constrained-JSON failures seen with gpt-oss models;
            # the response is still validated locally before it enters the pipeline.
            max_tokens=2500,
        )
        raw_usage = getattr(response, "usage", None)
        if raw_usage:
            usage = {
                "prompt_tokens": getattr(raw_usage, "prompt_tokens", 0),
                "completion_tokens": getattr(raw_usage, "completion_tokens", 0),
                "total_tokens": getattr(raw_usage, "total_tokens", 0),
            }
        raw_text = response.choices[0].message.content
        result = _normalize_result(_parse_json_object(raw_text), category)
        _usage_log("Groq", model, started, usage, "success", attempt)
        logger.info("AI_RESULT provider=Groq model=%s relevant=%s", model, result.get("relevant"))
        return result
    except Exception as exc:
        code = _http_error_code(exc)
        _set_provider_cooldown("Groq", model, exc, code)
        _usage_log("Groq", model, started, usage, "error", attempt, code)
        logger.warning("AI_FAILOVER provider=Groq model=%s error_code=%s detail=%s",
                       model, code, str(exc)[:250])
        return None


def _obviously_nonfinancial(text: str) -> bool:
    """Conservative zero-token gate for unmistakable non-market headlines."""
    lowered = (text or "").lower()
    finance_terms = (
        "stock", "shares", "market", "investor", "revenue", "earnings", "profit",
        "inflation", "rate", "fed", "ecb", "central bank", "bond", "oil", "gold",
        "bitcoin", "crypto", " доллар", "акци", "бирж", "рын", "инвест",
        "выруч", "прибыл", "инфляц", "ставк", "центробанк", "облигац", "нефт",
        "золот", "биткоин", "криптовалют", "рубл", "евро", "доллар", "пошлин",
        "санкц", "экспорт", "импорт", "gdp", "cpi", "pmi", "ipo", "merger",
    )
    nonmarket_terms = (
        "football match", "soccer match", "basketball game", "tennis match",
        "movie premiere", "celebrity wedding", "reality show",
        "футбольный матч", "баскетбольный матч", "теннисный матч",
        "премьера фильма", "свадьба актёра", "свадьба актера",
        "новый сезон сериала", "победил в матче", "результат матча",
    )
    return any(term in lowered for term in nonmarket_terms) and not any(
        term in lowered for term in finance_terms
    )


def analyze(raw_text: str, category: str = "BREAKING") -> dict | None:
    if _obviously_nonfinancial(raw_text):
        logger.info("AI_PREFILTER skipped obvious non-financial item category=%s", category)
        return {"relevant": False, "post_type": "skip"}

    if not GEMINI_API_KEY and not GROQ_API_KEY:
        logger.error("Neither GEMINI_API_KEY nor GROQ_API_KEY is set")
        return None

    prompt = f"""Категория поста: {category}
Новость: {raw_text}

Верни JSON строго по схеме:
{ANALYSIS_SCHEMA}"""

    # Three bounded attempts, no nested SDK retries: Gemini -> Groq 120B -> Groq 20B.
    # If Gemini is not configured, the Groq models become attempts 1 and 2.
    if GEMINI_API_KEY:
        if _provider_is_cooling_down("Gemini", PRIMARY_GEMINI_MODEL):
            logger.info("AI_PROVIDER_SKIPPED provider=Gemini model=%s reason=cooldown", PRIMARY_GEMINI_MODEL)
        else:
            result = _analyze_gemini(prompt, category)
            if result is not None:
                return result

    groq_models = list(dict.fromkeys(
        model for model in (PRIMARY_GROQ_MODEL, SECONDARY_GROQ_MODEL)
        if model and model.strip()
    ))
    for attempt, model in enumerate(groq_models, start=2 if GEMINI_API_KEY else 1):
        if _provider_is_cooling_down("Groq", model):
            logger.info("AI_PROVIDER_SKIPPED provider=Groq model=%s reason=cooldown", model)
            continue
        result = _analyze_groq(prompt, category, model, attempt)
        if result is not None:
            return result

    logger.error("AI_EXHAUSTED category=%s providers_attempted=%s",
                 category, int(bool(GEMINI_API_KEY)) + len(groq_models))
    return None


def _title_key(title: str) -> str:
    title = (title or "").lower().strip()
    title = re.sub(r"https?://\S+", " ", title)
    title = re.sub(r"[^a-zа-яё0-9 ]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _title_tokens(title: str) -> set[str]:
    stop = {"это", "как", "что", "для", "при", "после", "перед", "the", "and", "with", "from"}
    return {word for word in _title_key(title).split() if len(word) > 2 and word not in stop}


def _is_local_duplicate(title: str, previous: list[tuple[str, set[str]]]) -> bool:
    key = _title_key(title)
    tokens = _title_tokens(title)
    if not key:
        return True
    for old_key, old_tokens in previous:
        if key == old_key:
            return True
        if tokens and old_tokens:
            overlap = len(tokens & old_tokens) / len(tokens | old_tokens)
            if overlap >= 0.82:
                return True
    return False


def analyze_batch(news_items: list, category: str = "HOURLY") -> list:
    results = []
    seen: list[tuple[str, set[str]]] = []
    for item in news_items:
        title = str(item.get("title") or "")
        if _is_local_duplicate(title, seen):
            logger.info("AI_PREFILTER skipped duplicate title=%s", title[:100])
            continue
        seen.append((_title_key(title), _title_tokens(title)))
        text = f"{title}. {item.get('summary', '')}"
        analysis = analyze(text, category)
        if analysis and analysis.get("relevant") is not False:
            analysis["_source"] = item.get("source", "")
            analysis["_url"] = item.get("url", "")
            analysis["_raw_title"] = title
            results.append(analysis)
    return results
