"""Independent AI critic for high-impact BREAKING recommendations."""
import json
import logging
import os
from urllib.parse import quote

import requests
from groq import Groq
from config.config import (
    GEMINI_API_KEY,
    GEMINI_FALLBACK_MODEL,
    GEMINI_MODEL,
    GROQ_API_KEY,
)

logger = logging.getLogger(__name__)

# Groq remains the fallback critic when Gemini is unavailable.
CRITIC_MODELS = [
    os.environ.get("GROQ_CRITIC_MODEL", "openai/gpt-oss-20b"),
    os.environ.get("GROQ_CRITIC_FALLBACK_MODEL", "openai/gpt-oss-120b"),
]
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
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
        "Проверь этот вывод и верни JSON строго по схеме."
    )


def _review_with_gemini(
    prompt: str,
    model: str,
) -> dict:
    response = requests.post(
        GEMINI_URL.format(model=quote(model, safe="")),
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "system_instruction": {
                "parts": [{"text": CRITIC_SYSTEM_PROMPT}]
            },
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json",
            },
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def review(summary: str, recommendation: str, recommendation_text: str) -> dict | None:
    if not GEMINI_API_KEY and not GROQ_API_KEY:
        return None
    prompt = _prompt(summary, recommendation, recommendation_text)

    if GEMINI_API_KEY:
        for model in dict.fromkeys([GEMINI_MODEL, GEMINI_FALLBACK_MODEL]):
            try:
                result = _review_with_gemini(prompt, model)
                logger.info(
                    "Critic (Gemini/%s): agree=%s, rec=%s",
                    model, result.get("agree"), result.get("critic_recommendation"),
                )
                return result
            except Exception as exc:
                logger.warning("Critic Gemini error (%s): %s", model, exc)

    if not GROQ_API_KEY:
        return None

    for model in dict.fromkeys([
        *CRITIC_MODELS,
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
    ]):
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
