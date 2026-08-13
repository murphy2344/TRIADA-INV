import json
import logging
import time

from groq import Groq
from config.config import GROQ_API_KEY, GROQ_MODEL, GROQ_FALLBACK_MODEL

logger = logging.getLogger(__name__)
_PRIMARY_RATE_LIMITED_UNTIL = 0.0

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


def _normalize_result(result: dict, category: str) -> dict:
    """Map the new AI contract to the existing pipeline contract."""
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


def analyze(raw_text: str, category: str = "BREAKING") -> dict | None:
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY not set")
        return None

    global _PRIMARY_RATE_LIMITED_UNTIL
    client = Groq(api_key=GROQ_API_KEY, max_retries=0)
    prompt = f"""Категория поста: {category}
Новость: {raw_text}

Верни JSON строго по схеме:
{ANALYSIS_SCHEMA}"""
    models = [GROQ_MODEL, GROQ_FALLBACK_MODEL]
    if time.monotonic() < _PRIMARY_RATE_LIMITED_UNTIL:
        models = [GROQ_FALLBACK_MODEL]

    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1400,
                response_format={"type": "json_object"},
            )
            result = _normalize_result(
                json.loads(response.choices[0].message.content), category
            )
            logger.info(
                "AI (%s): relevant=%s, title=%s",
                model, result.get("relevant"), result.get("title", "")[:40],
            )
            return result
        except Exception as exc:
            if model == GROQ_MODEL and (
                "429" in str(exc) or "rate_limit" in str(exc).lower()
            ):
                _PRIMARY_RATE_LIMITED_UNTIL = time.monotonic() + 45 * 60
                logger.warning("Groq primary model rate-limited; using fallback")
            else:
                logger.error("Groq error (%s): %s", model, exc)
    return None


def analyze_batch(news_items: list, category: str = "HOURLY") -> list:
    results = []
    for item in news_items:
        text = f"{item['title']}. {item.get('summary', '')}"
        analysis = analyze(text, category)
        if analysis and analysis.get("relevant") is not False:
            analysis["_source"] = item["source"]
            analysis["_url"] = item["url"]
            analysis["_raw_title"] = item["title"]
            results.append(analysis)
    return results