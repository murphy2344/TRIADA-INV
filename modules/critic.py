"""Independent AI critic for high-impact BREAKING recommendations."""
import json
import logging
import re
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

Верни компактный СТРОГО валидный JSON (без markdown и преамбулы).
Не добавляй рассуждения вне JSON. Поля:
{"agree":true,"critic_recommendation":"long|short|neutral","critic_note":"краткое пояснение по-русски, не более 2 предложений"}"""


def _parse_critic_result(raw_text: str) -> dict:
    """Parse and validate the critic contract before it reaches a published post."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        result = json.loads(text[start:end + 1])

    if not isinstance(result, dict):
        raise ValueError("Critic JSON must be an object")
    agree = result.get("agree")
    recommendation = str(result.get("critic_recommendation") or "").strip().lower()
    note = result.get("critic_note")
    if not isinstance(agree, bool):
        raise ValueError("Critic field 'agree' must be boolean")
    if recommendation not in {"long", "short", "neutral"}:
        raise ValueError("Critic field 'critic_recommendation' must be long, short, or neutral")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("Critic field 'critic_note' must be a non-empty string")
    return {
        "agree": agree,
        "critic_recommendation": recommendation,
        "critic_note": note.strip()[:600],
    }


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
                "maxOutputTokens": 512,
                "responseMimeType": "application/json",
            },
        },
        timeout=12,
    )
    response.raise_for_status()
    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_critic_result(text)


def review(summary: str, recommendation: str, recommendation_text: str) -> dict | None:
    if not GEMINI_API_KEY and not GROQ_API_KEY:
        return None
    prompt = _prompt(summary, recommendation, recommendation_text)

    if GEMINI_API_KEY:
        for model in dict.fromkeys([GEMINI_MODEL]):
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

    # At most two Groq attempts; don't retry the same models under aliases.
    groq_models = list(dict.fromkeys(
        model.strip()
        for model in CRITIC_MODELS[:2]
        if model and model.strip()
    ))
    for model in groq_models:
        try:
            client = Groq(api_key=GROQ_API_KEY, max_retries=0, timeout=12)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=512,
            )
            message = response.choices[0].message
            raw_content = message.content
            if not isinstance(raw_content, str) or not raw_content.strip():
                finish_reason = getattr(response.choices[0], "finish_reason", None)
                usage = getattr(response, "usage", None)
                completion_tokens = getattr(usage, "completion_tokens", None)
                logger.warning(
                    "Critic Groq empty content (%s): finish_reason=%s completion_tokens=%s",
                    model, finish_reason, completion_tokens,
                )
                raise ValueError(
                    f"Groq returned empty critic content (finish_reason={finish_reason})"
                )
            result = _parse_critic_result(raw_content)
            logger.info(
                "Critic (Groq/%s): agree=%s, rec=%s",
                model, result.get("agree"), result.get("critic_recommendation"),
            )
            return result
        except Exception as exc:
            logger.warning("Critic Groq error (%s): %s", model, exc)
    return None
