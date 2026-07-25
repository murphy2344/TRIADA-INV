"""
AI-критик рекомендаций — использует Groq, но ДРУГУЮ модель чем основной
анализатор (llama-3.3-70b). Для критика берём gemma2-9b-it — другая
архитектура, другие веса → независимое мнение без самосогласия одной модели.

Вызывается ТОЛЬКО для BREAKING-новостей с impact_level == "high".
Groq free tier: ~14,400 запросов/день — этого с головой хватает.
Не нужен отдельный ключ — используем GROQ_API_KEY который уже в .env.
"""
import json
import logging
from groq import Groq
from config.config import GROQ_API_KEY

logger = logging.getLogger(__name__)

# Намеренно НЕ llama-3.3-70b-versatile (основная модель) — другая архитектура
CRITIC_MODEL = "gemma2-9b-it"

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
    """Возвращает мнение критика, либо None если Groq недоступен —
    в этом случае пайплайн публикует пост без второго мнения."""
    if not GROQ_API_KEY:
        return None

    prompt = (
        f"Новость: {summary}\n"
        f"Вывод первого аналитика: рекомендация \"{recommendation}\", "
        f"обоснование: {recommendation_text}\n\n"
        f"Проверь этот вывод и верни JSON строго по схеме."
    )

    try:
        client = Groq(api_key=GROQ_API_KEY)
        resp = client.chat.completions.create(
            model=CRITIC_MODEL,
            messages=[
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=256,
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content
        result = json.loads(text)
        logger.info(
            f"Critic (gemma2-9b-it): agree={result.get('agree')}, "
            f"rec={result.get('critic_recommendation')}"
        )
        return result
    except Exception as e:
        logger.error(f"Groq critic error: {e}")
        return None
