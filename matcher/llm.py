import json
import os
import random
from dataclasses import dataclass
from typing import Iterable
from urllib import error, request


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.2"

FALLBACK_REPLIES = [
    "That sounds good. Where should we meet?",
    "I am nearby and can head over now.",
    "Nice, I have about an hour free.",
    "Cool. I prefer a quick hello first.",
]

SYSTEM_PROMPT = """
You are the anonymous chat assistant inside Plus One, a campus app for matching
students around spontaneous platonic activities. Reply as the other student in
the match. Keep the tone friendly, casual, safe, and concise.

Rules:
- Stay under 25 words.
- Do not reveal real names or personal private details.
- Help the users decide whether and where to meet.
- Prefer concrete meeting logistics when useful.
- No flirting, pressure, or unsafe meetup suggestions.
""".strip()


@dataclass(frozen=True)
class LLMReply:
    text: str
    used_llm: bool
    provider: str
    error: str = ""


def get_llm_status():
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    return {
        "enabled": has_key,
        "provider": "OpenAI Responses API" if has_key else "Fallback demo replies",
        "model": os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        "missing": "" if has_key else "OPENAI_API_KEY",
    }


def generate_chat_reply(match, user_message):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _fallback_reply("OPENAI_API_KEY is not set.")

    prompt = _build_prompt(match, user_message)
    payload = {
        "model": os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        "instructions": SYSTEM_PROMPT,
        "input": prompt,
        "max_output_tokens": 80,
    }

    try:
        response_json = _post_openai(api_key, payload)
        text = _extract_output_text(response_json)
    except Exception as exc:
        return _fallback_reply(str(exc))

    if not text:
        return _fallback_reply("The LLM returned an empty response.")

    return LLMReply(
        text=_clean_reply(text),
        used_llm=True,
        provider=f"OpenAI/{payload['model']}",
    )


def _build_prompt(match, user_message):
    post = match.post
    history = _format_history(match.messages.all())
    return f"""
Activity:
- Title: {post.title}
- Type: {post.get_activity_type_display()}
- Location: {post.location}
- Starts at: {post.starts_at:%H:%M}
- Host note: {post.vibe_note or "quick vibe check first"}

Chat history:
{history}

Latest user message:
{user_message}

Reply as the anonymous plus one.
""".strip()


def _format_history(messages: Iterable):
    lines = []
    for message in messages:
        speaker = "User" if message.sender == "you" else "Other student"
        lines.append(f"{speaker}: {message.body}")
    return "\n".join(lines[-8:]) or "No previous messages."


def _post_openai(api_key, payload):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        OPENAI_RESPONSES_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error {exc.code}: {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI API connection error: {exc.reason}") from exc


def _extract_output_text(response_json):
    output = response_json.get("output", [])
    parts = []
    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                parts.append(content.get("text", ""))
    return " ".join(part.strip() for part in parts if part.strip()).strip()


def _clean_reply(text):
    text = " ".join(text.split())
    if len(text) <= 220:
        return text
    return text[:217].rstrip() + "..."


def _fallback_reply(error_message):
    return LLMReply(
        text=random.choice(FALLBACK_REPLIES),
        used_llm=False,
        provider="fallback",
        error=error_message,
    )
