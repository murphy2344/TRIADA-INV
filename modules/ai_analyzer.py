import json
import logging
from groq import Groq
from config.config import GROQ_API_KEY, GROQ_MODEL, GROQ_FALLBACK_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — старший финансовый аналитик инвестиционного дома TRIADA INVESTING.
Анализируй новости строго на русском языке. Исходный текст может быть на английском — ВСЕГДА переводи.
Отвечай ТОЛЬКО валидным JSON без markdown-блоков, без преамбулы, без объяснений.

ПРАВИЛО relevant:
- true ТОЛЬКО если новость реально и напрямую влияет на финансовые рынки:
  акции, валюты, сырьё, крипта, ставки ЦБ, инфляция, геополитика с прямым экономическим эффектом.
- Спорт, культура, развлечения, локальные события без экономического эффекта — ВСЕГДА relevant: false.
- ВАЖНО: происшествия, взрывы, преступления, аварии, теракты без атаки на конкретную
  экономическую инфраструктуру (нефтепровод, порт, биржу, завод) — ВСЕГДА relevant: false,
  ДАЖЕ ЕСЛИ кажется, что "это может повлиять на настроение рынка" или "инвесторы могут
  отреагировать на новостной фон". Такое расплывчатое обоснование ЗАПРЕЩЕНО использовать
  как причину для relevant: true — это признак того, что новость на самом деле нерелевантна.
  Пример: "Взрыв в жилом доме, пострадали люди" → relevant: false, даже если есть соблазн
  написать "может повлиять на курс доллара".
- Политические дебаты на социальные темы (права меньшинств, гражданские права, культурные
  вопросы) без объявленной конкретной экономической меры — ВСЕГДА relevant: false.
- Публичные выступления/митинги/речи политиков БЕЗ объявления конкретной экономической
  политики (тарифы, санкции, ставки, регулирование) — ВСЕГДА relevant: false.
- Если relevant: false — верни ТОЛЬКО {"relevant": false, "post_type": "skip"} и ничего больше.

ПРАВИЛО needs_chart и ticker:
- needs_chart: true ТОЛЬКО если новость про КОНКРЕТНЫЙ ПУБЛИЧНО ТОРГУЕМЫЙ актив с
  реальным биржевым тикером:
  Bitcoin/BTC → "BTC-USD", Ethereum → "ETH-USD", любая крипта → "BTC-USD"
  Золото/Gold → "GC=F", Нефть/Oil/Brent → "CL=F", Серебро → "SI=F"
  S&P 500 → "^GSPC", NASDAQ → "^IXIC", Dow Jones → "^DJI"
  EUR/USD → "EURUSD=X", Доллар/рубль → "RUB=X"
  Apple → "AAPL", Tesla → "TSLA", NVIDIA → "NVDA", Microsoft → "MSFT"
  Amazon → "AMZN", Google → "GOOGL", Meta → "META", JPMorgan → "JPM"
  Exxon → "XOM", BP → "BP", Shell → "SHEL", Goldman Sachs → "GS"
  Ставка ФРС / инфляция США → "^GSPC"
- КРИТИЧЕСКИ ВАЖНО: если новость про компанию БЕЗ публичного тикера (например SpaceX,
  OpenAI, Anthropic, ByteDance/TikTok, любая частная компания) — needs_chart ВСЕГДА false,
  ticker ВСЕГДА null. НЕ подставляй тикер связанного лица или похожей публичной компании
  (например, НЕЛЬЗЯ ставить TSLA для новости про SpaceX только потому что у них общий
  основатель Илон Маск — это два РАЗНЫХ юридических лица, разные новости требуют фото,
  а не график).
- needs_chart: false для политики, войны, санкций, ВВП страны, безработицы без конкретного тикера.

ПРАВИЛО subject_en: ВСЕГДА заполняй на английском для западных персон, компаний и событий.
Примеры: "Donald Trump", "Jerome Powell Federal Reserve", "Tesla Motors", "OPEC meeting",
"Kremlin Russia", "European Central Bank", "Goldman Sachs", "SpaceX Elon Musk"."""

ANALYSIS_SCHEMA = """{
  "relevant": true,
  "post_type": "urgent | hourly | market_move",
  "category": "person | company | geopolitics | market_move",
  "subject": "имя/название на русском для контекста",
  "subject_en": "name in English for photo search (Wikipedia/Google)",
  "title": "короткий заголовок на русском (макс 60 символов)",
  "summary": "суть новости на русском, максимум 5 предложений",
  "impact_level": "low | medium | high",
  "impact_text": "влияние на нефть, золото, доллар, фондовый рынок, валюты экспортёров, инфляцию — только релевантные",
  "affected_assets": ["актив1", "актив2"],
  "scenario": "возможный сценарий развития событий",
  "recommendation": "long | short | neutral",
  "recommendation_text": "обоснование рекомендации",
  "needs_chart": true,
  "ticker": "тикер или null"
}"""


def analyze(raw_text: str, category: str = "BREAKING") -> dict | None:
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY not set")
        return None

    client = Groq(api_key=GROQ_API_KEY)
    prompt = f"""Категория поста: {category}
Новость: {raw_text}

Верни JSON строго по схеме:
{ANALYSIS_SCHEMA}"""

    for model in [GROQ_MODEL, GROQ_FALLBACK_MODEL]:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1024,
                response_format={"type": "json_object"}
            )
            raw = response.choices[0].message.content
            result = json.loads(raw)
            logger.info(f"AI ({model}): relevant={result.get('relevant')}, title={result.get('title', '')[:40]}")
            return result
        except Exception as e:
            logger.error(f"Groq error ({model}): {e}")
            continue

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
