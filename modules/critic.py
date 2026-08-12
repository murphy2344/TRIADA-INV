"""Independent Groq critic for high-impact BREAKING recommendations."""
import json
import logging
import os

from groq import Groq
from config.config import GROQ_API_KEY

logger = logging.getLogger(__name__)

# gemma2-9b-it was decommissioned by Groq. Keep the default on a model that
# is already used successfully by the main analyzer, with a second fallback.
CRITIC_MODELS = [
    os.environ.get("GROQ_CRITIC_MODEL", "llama-3.1-8b-instant"),
    os.environ.get("GROQ_CRITIC_FALLBACK_MODEL", "llama-3.3-70b-versatile"),
]

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


def _prompt(summary: str, recommendation: str, recommendation_text: str) -> str:
    return (
        f"Новость: {summary}\n"
        f"Вывод первого аналитика: рекомендация \"{recommendation}\", "
        f"обоснование: {recommendation_text}\n\n"
        "Проверь этот вывод и верни JSON строго по схеме."
    )


def review(summary: str, recommendation: str, recommendation_text: str) -> dict | None:
    if not GROQ_API_KEY:
        return None
    prompt = _prompt(summary, recommendation, recommendation_text)
    for model in dict.fromkeys(CRITIC_MODELS):
        try:
            client = Groq(api_key=GROQ_API_KEY)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=256,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            logger.info(
                "Critic (Groq/%s): agree=%s, rec=%s",
                model, result.get("agree"), result.get("critic_recommendation"),
            )
            return result
        except Exception as exc:
            logger.warning("Critic Groq error (%s): %s", model, exc)
    return None
