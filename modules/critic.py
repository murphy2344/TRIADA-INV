"""
AI-критик рекомендаций. Использует ДРУГУЮ модель (Google Gemini), а не ту же
Groq/Llama, что и основной анализ — иначе критика получается слабой из-за
самосогласия одной модели с собой (та же проблема, что обсуждалась для
Pantheon/Apollo-Athena).

Вызывается ТОЛЬКО для срочных новостей с высоким влиянием (impact_level ==
high) — Gemini free tier ограничен (порядка 500 запросов/день на момент
написания), не тратим его на каждую новость почасового дайджеста.

Зависимости: только requests (уже есть в проекте) — отдельный SDK не нужен,
у Gemini обычный REST API.
"""
import json
import logging
import requests
from config.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

CRITIC_SYSTEM_PROMPT = """Ты — независимый риск-аналитик. Тебе присылают новость и вывод
другого аналитика (включая рекомендацию Лонг/Шорт/Нейтрально). Твоя задача — НЕ
соглашаться автоматически, а по-настоящему проверить логику: есть ли слабые места,
альтернативное объяснение, риски или контраргументы, которые первый аналитик мог упустить.

Отвечай СТРОГО валидным JSON, без markdown, без преамбулы:
{
  "agree": true/false,
  "critic_recommendation": "long | short | neutral",
  "critic_note": "краткое пояснение на русском, максимум 2 предложения — в чём согласен или не согласен"
}"""


def review(summary: str, recommendation: str, recommendation_text: str) -> dict | None:
    """Возвращает мнение критика, либо None если Gemini недоступен/не настроен —
    в этом случае пайплайн просто публикует пост без второго мнения, не блокируясь."""
    if not GEMINI_API_KEY:
        return None

    prompt = (
        f"Новость: {summary}\n"
        f"Вывод первого аналитика: рекомендация \"{recommendation}\", "
        f"обоснование: {recommendation_text}\n\n"
        f"Проверь этот вывод и верни JSON строго по схеме."
    )

    try:
        resp = requests.post(
            GEMINI_URL,
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": CRITIC_SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.4,
                    "responseMimeType": "application/json",
                },
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
        logger.info(
            f"Critic (Gemini): agree={result.get('agree')}, "
            f"rec={result.get('critic_recommendation')}"
        )
        return result
    except Exception as e:
        logger.error(f"Gemini critic error: {e}")
        return None
