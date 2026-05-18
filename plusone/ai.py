import json
import os
import re
import time
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import ActivityPost, CampusLocation, LLMLog


UNSAFE_KEYWORDS = {
    "harass",
    "hate",
    "threat",
    "weapon",
    "drugs",
    "drunk",
    "address",
    "phone number",
    "password",
    "alone in my room",
}


def _save_log(user, task_type, input_text, output_json=None, output_text="", model="", strategy="rule_fallback", success=True, started_at=None):
    latency_ms = 0
    if started_at is not None:
        latency_ms = max(0, int((time.perf_counter() - started_at) * 1000))
    return LLMLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        task_type=task_type,
        input_text=input_text,
        output_json=output_json or {},
        output_text=output_text,
        model=model,
        strategy=strategy,
        success=success,
        latency_ms=latency_ms,
    )


def _first_location_for_keywords(text):
    lowered = text.lower()
    candidates = [
        (["sports", "basketball", "game", "gym"], "Campus Sports Hall"),
        (["library", "study", "sprint"], "Main Library"),
        (["lunch", "dinner", "food", "mensa", "dining"], "North Dining Hall"),
        (["club", "fair", "booth"], "Student Center"),
        (["quad", "walk", "explore"], "Campus Quad"),
    ]
    for keywords, name in candidates:
        if any(keyword in lowered for keyword in keywords):
            location = CampusLocation.objects.filter(name__icontains=name).first()
            if location:
                return location
    return CampusLocation.objects.first()


def _activity_type(text):
    lowered = text.lower()
    if any(word in lowered for word in ["lunch", "dinner", "food", "mensa", "dining", "coffee"]):
        return ActivityPost.ActivityType.FOOD
    if any(word in lowered for word in ["basketball", "game", "sports", "gym"]):
        return ActivityPost.ActivityType.SPORTS
    if any(word in lowered for word in ["study", "library", "sprint", "homework"]):
        return ActivityPost.ActivityType.STUDY
    if any(word in lowered for word in ["club", "fair", "booth"]):
        return ActivityPost.ActivityType.CLUB
    if any(word in lowered for word in ["explore", "walk", "tour"]):
        return ActivityPost.ActivityType.EXPLORE
    return ActivityPost.ActivityType.OTHER


def _parse_time(text):
    lowered = text.lower()
    now = timezone.localtime()
    base = now
    if "tomorrow" in lowered:
        base = now + timedelta(days=1)

    hour = minute = None
    match = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", lowered)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
    else:
        match = re.search(r"\b(1[0-2]|0?[1-9])\s*(am|pm)\b", lowered)
        if match:
            hour = int(match.group(1)) % 12
            if match.group(2) == "pm":
                hour += 12
            minute = 0
        else:
            match = re.search(r"\b(?:around|at|tonight|today)?\s*(1[0-2]|0?[1-9])\b", lowered)
            if match and any(word in lowered for word in ["tonight", "around", " at ", "game"]):
                hour = int(match.group(1))
                if "morning" not in lowered and hour < 12:
                    hour += 12
                minute = 0

    if hour is None:
        if "lunch" in lowered:
            hour, minute = 12, 30
        elif "dinner" in lowered:
            hour, minute = 18, 30
        elif "tonight" in lowered:
            hour, minute = 19, 0
        else:
            return now + timedelta(hours=1)

    parsed = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if parsed < now - timedelta(minutes=15):
        parsed += timedelta(days=1)
    return parsed


def _title_for(text, activity_type):
    lowered = text.lower()
    if "basketball" in lowered:
        return "Basketball game tonight"
    if activity_type == ActivityPost.ActivityType.FOOD:
        return "Meal buddy on campus"
    if activity_type == ActivityPost.ActivityType.STUDY:
        return "Study sprint"
    if activity_type == ActivityPost.ActivityType.CLUB:
        return "Explore the club fair"
    if activity_type == ActivityPost.ActivityType.EXPLORE:
        return "Campus walk"
    return text.strip().split(".")[0][:80] or "Quick campus plan"


def rule_parse_activity(text):
    activity_type = _activity_type(text)
    location = _first_location_for_keywords(text)
    start_time = _parse_time(text)
    return {
        "title": _title_for(text, activity_type),
        "description": text.strip(),
        "activity_type": activity_type,
        "location_name": location.name if location else "",
        "start_time": start_time.isoformat(),
        "expire_minutes": 45,
    }


def _openai_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None
    return OpenAI(api_key=api_key)


def parse_activity_text(user, text):
    started_at = time.perf_counter()
    model = getattr(settings, "PLUSONE_OPENAI_MODEL", "gpt-4o-mini")
    client = _openai_client()
    locations = list(CampusLocation.objects.values_list("name", flat=True))
    if client:
        try:
            response = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Parse a college activity request into JSON with keys: "
                            "title, description, activity_type, location_name, start_time, expire_minutes. "
                            f"Use one activity_type from {[choice[0] for choice in ActivityPost.ActivityType.choices]}. "
                            f"Prefer one location from {locations}. Use ISO 8601 for start_time."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
            )
            raw = response.choices[0].message.content or "{}"
            parsed = json.loads(raw)
            fallback = rule_parse_activity(text)
            merged = {**fallback, **{k: v for k, v in parsed.items() if v}}
            _save_log(user, LLMLog.TaskType.PARSE_POST, text, merged, raw, model, "openai", True, started_at)
            return merged
        except Exception as exc:
            parsed = rule_parse_activity(text)
            _save_log(user, LLMLog.TaskType.PARSE_POST, text, parsed, str(exc), model, "openai_failed_rule_fallback", False, started_at)
            return parsed

    parsed = rule_parse_activity(text)
    _save_log(user, LLMLog.TaskType.PARSE_POST, text, parsed, json.dumps(parsed), "", "rule_fallback", True, started_at)
    return parsed


def rule_generate_icebreaker(post):
    if post.activity_type == ActivityPost.ActivityType.SPORTS:
        return "Are you planning to watch the full game or just drop by for a bit?"
    if post.activity_type == ActivityPost.ActivityType.FOOD:
        return "Are you heading there now, or should we meet near the entrance first?"
    if post.activity_type == ActivityPost.ActivityType.STUDY:
        return "Do you prefer a quiet table or a quick planning check-in first?"
    if post.activity_type == ActivityPost.ActivityType.CLUB:
        return "Any booths you already want to visit first?"
    return "What would make this plan easy for you to join?"


def generate_icebreaker(user, post):
    started_at = time.perf_counter()
    prompt = f"{post.title} at {post.location.name}, type={post.activity_type}"
    model = getattr(settings, "PLUSONE_OPENAI_MODEL", "gpt-4o-mini")
    client = _openai_client()
    if client:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Write one friendly, platonic, short icebreaker for a five-minute campus meetup chat."},
                    {"role": "user", "content": prompt},
                ],
            )
            text = (response.choices[0].message.content or "").strip()[:240]
            _save_log(user, LLMLog.TaskType.ICEBREAKER, prompt, {}, text, model, "openai", True, started_at)
            return text
        except Exception as exc:
            text = rule_generate_icebreaker(post)
            _save_log(user, LLMLog.TaskType.ICEBREAKER, prompt, {}, str(exc), model, "openai_failed_rule_fallback", False, started_at)
            return text
    text = rule_generate_icebreaker(post)
    _save_log(user, LLMLog.TaskType.ICEBREAKER, prompt, {}, text, "", "rule_fallback", True, started_at)
    return text


def rule_moderate_text(text):
    lowered = text.lower()
    hits = [keyword for keyword in UNSAFE_KEYWORDS if keyword in lowered]
    return {
        "flagged": bool(hits),
        "categories": hits,
        "reason": "Matched demo safety keywords." if hits else "No demo safety keyword matched.",
    }


def moderate_text(user, text):
    started_at = time.perf_counter()
    model = getattr(settings, "PLUSONE_OPENAI_MODEL", "gpt-4o-mini")
    client = _openai_client()
    if client:
        try:
            response = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Return JSON: flagged boolean, categories array, reason string. Flag unsafe campus meetup content, harassment, personal information, or inappropriate text."},
                    {"role": "user", "content": text},
                ],
            )
            raw = response.choices[0].message.content or "{}"
            result = json.loads(raw)
            _save_log(user, LLMLog.TaskType.MODERATION, text, result, raw, model, "openai", True, started_at)
            return result
        except Exception as exc:
            result = rule_moderate_text(text)
            _save_log(user, LLMLog.TaskType.MODERATION, text, result, str(exc), model, "openai_failed_rule_fallback", False, started_at)
            return result
    result = rule_moderate_text(text)
    _save_log(user, LLMLog.TaskType.MODERATION, text, result, json.dumps(result), "", "rule_fallback", True, started_at)
    return result
