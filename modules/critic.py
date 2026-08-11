"""Independent AI critic for high-impact BREAKING recommendations.

Gemini is preferred when GEMINI_API_KEY is configured. Groq remains a
fallback, so the bot keeps working if Gemini is not configured or unavailable.
"""
import json
import logging
import requests
from groq import Groq
from config.config import GEMINI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

# Deliberately different from the main llama-3.3-70b model.
CRITIC_MODEL = "gemma2-9b-it"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

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
        f"Проверь этот вывод и верни JSON строго по схеме."
    )


def _parse(text: str) -> dict:
    return json.loads(text)


def _review_gemini(prompt: str) -> dict:
    resp = requests.post(
        GEMINI_URL,
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json",
        },
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
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _parse(text)


def _review_groq(prompt: str) -> dict:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured")
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
    return _parse(resp.choices[0].message.content)


def review(summary: str, recommendation: str, recommendation_text: str) -> dict | None:
    """Return the critic result, or None if no configured provider is available."""
    prompt = (
        _prompt(summary, recommendation, recommendation_text)
    )

    providers = []
    if GEMINI_API_KEY:
        providers.append(("Gemini", _review_gemini))
    if GROQ_API_KEY:
        providers.append(("Groq", _review_groq))
    if not providers:
        return None

    for name, provider in providers:
        try:
            result = provider(prompt)
            logger.info(
                "Critic (%s): agree=%s, rec=%s",
                name, result.get("agree"), result.get("critic_recommendation"),
            )
            return result
        except Exception as e:
            logger.warning("Critic %s error: %s", name, e)

    return None
