from datetime import datetime, timedelta

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie

from .llm import generate_chat_reply, get_llm_status
from .models import ActivityPost, ChatMessage, Match, Swipe


ACCENTS = {
    ActivityPost.FOOD: "#FFD95A",
    ActivityPost.SPORTS: "#FF4F93",
    ActivityPost.STUDY: "#12C6C1",
    ActivityPost.EXPLORE: "#6C63FF",
    ActivityPost.CLUB: "#111827",
}

def ensure_demo_data():
    now = timezone.now()
    if ActivityPost.objects.filter(expires_at__gt=now).count() >= 4:
        return

    samples = [
        {
            "title": "Lunch at Mensa?",
            "description": "Looking for someone to grab a quick plate before lecture.",
            "location": "Mensa Arcisstrasse",
            "activity_type": ActivityPost.FOOD,
            "host_alias": "Anonymous sophomore",
            "starts_at": now + timedelta(minutes=18),
            "expires_at": now + timedelta(minutes=26),
            "vibe_note": "prefers quick chat first",
        },
        {
            "title": "Basketball game",
            "description": "Going to the campus game and want a seat buddy.",
            "location": "Campus Sports Hall",
            "activity_type": ActivityPost.SPORTS,
            "host_alias": "Sports fan nearby",
            "starts_at": now + timedelta(minutes=44),
            "expires_at": now + timedelta(minutes=48),
            "vibe_note": "easygoing, no pressure",
        },
        {
            "title": "Library study sprint",
            "description": "One focused Pomodoro block before the database tutorial.",
            "location": "Library 2F",
            "activity_type": ActivityPost.STUDY,
            "host_alias": "Quiet study partner",
            "starts_at": now + timedelta(minutes=32),
            "expires_at": now + timedelta(minutes=41),
            "vibe_note": "low talk, high focus",
        },
        {
            "title": "Club fair lap",
            "description": "Exploring the booths and comparing which clubs are worth joining.",
            "location": "Main atrium",
            "activity_type": ActivityPost.CLUB,
            "host_alias": "Curious first-year",
            "starts_at": now + timedelta(minutes=55),
            "expires_at": now + timedelta(minutes=63),
            "vibe_note": "wants to discover something new",
        },
    ]

    for sample in samples:
        exists = ActivityPost.objects.filter(
            title=sample["title"],
            location=sample["location"],
            expires_at__gt=now,
        ).exists()
        if not exists:
            ActivityPost.objects.create(
                **sample,
                accent=ACCENTS[sample["activity_type"]],
            )


def post_payload(post):
    return {
        "id": post.id,
        "title": post.title,
        "description": post.description,
        "location": post.location,
        "activityType": post.activity_type,
        "activityLabel": post.get_activity_type_display(),
        "hostAlias": post.host_alias,
        "startsAt": post.starts_at.isoformat(),
        "startsLabel": post.starts_at.strftime("%H:%M"),
        "expiresAt": post.expires_at.isoformat(),
        "minutesLeft": post.minutes_left,
        "vibeNote": post.vibe_note,
        "accent": post.accent,
    }


@ensure_csrf_cookie
def discover(request):
    ensure_demo_data()
    posts = ActivityPost.objects.filter(expires_at__gt=timezone.now()).order_by("starts_at")
    return render(request, "matcher/discover.html", {"posts": [post_payload(post) for post in posts]})


def create_post(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        location = request.POST.get("location", "").strip()
        activity_type = request.POST.get("activity_type", ActivityPost.EXPLORE)
        starts_raw = request.POST.get("starts_at", "").strip()
        expires_after = int(request.POST.get("expires_after", "45") or 45)

        if not title or not location:
            messages.error(request, "Theme and location are required for the card.")
            return redirect("matcher:create")

        try:
            starts_at = timezone.make_aware(datetime.fromisoformat(starts_raw))
        except ValueError:
            starts_at = timezone.now() + timedelta(minutes=30)

        post = ActivityPost.objects.create(
            title=title,
            description=description or "Open to a quick vibe check before meeting.",
            location=location,
            activity_type=activity_type,
            host_alias="You",
            starts_at=starts_at,
            expires_at=timezone.now() + timedelta(minutes=expires_after),
            vibe_note=request.POST.get("vibe_note", "").strip() or "5-minute chat first",
            accent=ACCENTS.get(activity_type, "#12C6C1"),
        )
        messages.success(request, f"Published '{post.title}' as a swipeable Plus One card.")
        return redirect("matcher:dashboard")

    default_start = (timezone.now() + timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M")
    return render(
        request,
        "matcher/create.html",
        {
            "activity_types": ActivityPost.ACTIVITY_TYPES,
            "default_start": default_start,
        },
    )


def chat(request, match_id):
    match = get_object_or_404(Match, id=match_id)
    return render(request, "matcher/chat.html", {"match": match, "llm_status": get_llm_status()})


def dashboard(request):
    ensure_demo_data()
    active_posts = ActivityPost.objects.filter(expires_at__gt=timezone.now()).order_by("expires_at")
    matches = Match.objects.select_related("post").prefetch_related("messages")[:6]
    right_swipes = Swipe.objects.filter(direction=Swipe.RIGHT).count()
    return render(
        request,
        "matcher/dashboard.html",
        {
            "active_posts": active_posts,
            "matches": matches,
            "right_swipes": right_swipes,
        },
    )


@require_POST
def swipe(request):
    post = get_object_or_404(ActivityPost, id=request.POST.get("post_id"))
    direction = request.POST.get("direction")
    if direction not in {Swipe.LEFT, Swipe.RIGHT}:
        return JsonResponse({"ok": False, "error": "Invalid swipe direction."}, status=400)

    Swipe.objects.create(post=post, direction=direction)

    if direction == Swipe.LEFT:
        return JsonResponse({"ok": True, "matched": False})

    match = Match.objects.create(
        post=post,
        participant_alias="Anonymous plus one",
        chat_expires_at=timezone.now() + timedelta(minutes=5),
        host_agreed=True,
    )
    ChatMessage.objects.bulk_create(
        [
            ChatMessage(match=match, sender=ChatMessage.THEM, body="Hey, are you also heading from the library?"),
            ChatMessage(match=match, sender=ChatMessage.YOU, body="Yes. I can meet by the south entrance."),
        ]
    )
    return JsonResponse(
        {
            "ok": True,
            "matched": True,
            "matchId": match.id,
            "chatUrl": reverse("matcher:chat", args=[match.id]),
        }
    )


@require_POST
def send_message(request, match_id):
    match = get_object_or_404(Match, id=match_id)
    body = request.POST.get("body", "").strip()
    if not body:
        return JsonResponse({"ok": False, "error": "Message cannot be empty."}, status=400)

    user_message = ChatMessage.objects.create(match=match, sender=ChatMessage.YOU, body=body)
    llm_reply = generate_chat_reply(match, user_message.body)
    reply = ChatMessage.objects.create(match=match, sender=ChatMessage.THEM, body=llm_reply.text)
    return JsonResponse(
        {
            "ok": True,
            "llm": {
                "used": llm_reply.used_llm,
                "provider": llm_reply.provider,
                "error": llm_reply.error,
            },
            "messages": [
                {"sender": user_message.sender, "body": user_message.body},
                {"sender": reply.sender, "body": reply.body},
            ],
        }
    )


@require_POST
def agree_to_meet(request, match_id):
    match = get_object_or_404(Match, id=match_id)
    match.guest_agreed = True
    match.host_agreed = True
    match.save(update_fields=["guest_agreed", "host_agreed"])
    return JsonResponse({"ok": True, "ready": match.is_ready_to_meet})

# Create your views here.
