import secrets
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .ai import moderate_text, parse_activity_text
from .forms import ActivityAssistForm, ActivityPostForm, ChatMessageForm
from .models import ActivityPost, CampusLocation, ChatMessage, Match, Swipe, UserProfile
from .services.chat import record_agreement
from .services.expiration import refresh_expired_records
from .services.matching import SwipeOutcome, handle_swipe


ANONYMOUS_SESSION_USERNAME_KEY = "plusone_anonymous_username"


def _anonymous_profile_defaults(username):
    code = username.removeprefix("anon_")[:4].upper()
    return {
        "display_name": f"Campus Guest {code}",
        "avatar_initial": code[:2] or "CG",
        "major": "",
        "year": "",
        "campus_area": "Campus",
        "interests": "",
    }


def create_anonymous_user():
    User = get_user_model()
    for _ in range(10):
        username = f"anon_{secrets.token_hex(4)}"
        if not User.objects.filter(username=username).exists():
            user = User(username=username)
            user.set_unusable_password()
            user.save()
            UserProfile.objects.create(user=user, **_anonymous_profile_defaults(username))
            return user
    raise RuntimeError("Could not allocate an anonymous Plus One identity.")


def ensure_user_profile(user):
    if user.username.startswith("anon_"):
        defaults = _anonymous_profile_defaults(user.username)
    else:
        defaults = {
            "display_name": user.get_full_name() or user.username,
            "avatar_initial": (user.username[:1] or "S").upper(),
        }
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults=defaults)
    if not profile.avatar_initial:
        profile.avatar_initial = (profile.display_name[:1] or user.username[:1] or "S").upper()
        profile.save(update_fields=["avatar_initial"])
    return profile


def ensure_anonymous_session(request):
    if request.user.is_authenticated:
        ensure_user_profile(request.user)
        return request.user

    username = request.session.get(ANONYMOUS_SESSION_USERNAME_KEY)
    User = get_user_model()
    user = User.objects.filter(username=username).first() if username else None
    if user is None:
        user = create_anonymous_user()
        request.session[ANONYMOUS_SESSION_USERNAME_KEY] = user.username

    login(request, user)
    return user


def _post_initial_from_ai(parsed):
    location = None
    if parsed.get("location_name"):
        location = CampusLocation.objects.filter(name__iexact=parsed["location_name"]).first()
        if not location:
            location = CampusLocation.objects.filter(name__icontains=parsed["location_name"]).first()
    if not location:
        location = CampusLocation.objects.first()

    start_time = timezone.localtime()
    if parsed.get("start_time"):
        try:
            start_time = timezone.datetime.fromisoformat(parsed["start_time"])
            if timezone.is_naive(start_time):
                start_time = timezone.make_aware(start_time, timezone.get_current_timezone())
        except ValueError:
            start_time = timezone.localtime() + timedelta(hours=1)

    return {
        "title": parsed.get("title", ""),
        "description": parsed.get("description", ""),
        "activity_type": parsed.get("activity_type", ActivityPost.ActivityType.OTHER),
        "location": location.id if location else None,
        "start_time": timezone.localtime(start_time).strftime("%Y-%m-%dT%H:%M"),
        "expire_minutes": parsed.get("expire_minutes", 45),
    }


def _post_form_preview(form):
    source = form.data if form.is_bound else form.initial
    location = None
    location_id = source.get("location")
    if location_id:
        location = CampusLocation.objects.filter(id=location_id).first()
    activity_type = source.get("activity_type") or ActivityPost.ActivityType.OTHER
    activity_label = dict(ActivityPost.ActivityType.choices).get(activity_type, "Other")
    return {
        "title": source.get("title") or "Your Plus One title",
        "description": source.get("description") or "The card preview updates as you edit the structured fields.",
        "activity_type": activity_type,
        "activity_label": activity_label,
        "location": location.name if location else "Campus location",
        "start_time": source.get("start_time") or "Start time",
        "expire_minutes": source.get("expire_minutes") or "45",
    }


def _post_edit_initial(post):
    remaining_minutes = int(max(5, round((post.expire_time - timezone.now()).total_seconds() / 60)))
    return {
        "title": post.title,
        "description": post.description,
        "activity_type": post.activity_type,
        "location": post.location_id,
        "start_time": timezone.localtime(post.start_time).strftime("%Y-%m-%dT%H:%M"),
        "expire_minutes": remaining_minutes,
    }


def discover(request):
    ensure_anonymous_session(request)
    refresh_expired_records()
    activity_type = request.GET.get("activity_type", "")
    location_id = request.GET.get("location", "")
    time_window = request.GET.get("time_window", "")
    matched_id = request.GET.get("matched")
    swiped_ids = Swipe.objects.filter(user=request.user).values_list("post_id", flat=True)
    posts = (
        ActivityPost.objects.active()
        .exclude(id__in=swiped_ids)
        .select_related("user", "location")
    )
    if activity_type:
        posts = posts.filter(activity_type=activity_type)
    if location_id:
        posts = posts.filter(location_id=location_id)
    if time_window == "now":
        posts = posts.filter(start_time__lte=timezone.now() + timedelta(hours=2))
    if time_window == "today":
        posts = posts.filter(start_time__date=timezone.localdate())

    matched_match = None
    if matched_id:
        matched_match = (
            Match.objects.filter(id=matched_id)
            .filter(Q(poster=request.user) | Q(swiper=request.user))
            .select_related("post", "post__location")
            .first()
        )
    context = {
        "posts": posts,
        "activity_types": ActivityPost.ActivityType.choices,
        "locations": CampusLocation.objects.all(),
        "selected_activity_type": activity_type,
        "selected_location": location_id,
        "selected_time_window": time_window,
        "matched_match": matched_match,
    }
    return render(request, "plusone/discover.html", context)


def about(request):
    ensure_anonymous_session(request)
    return render(request, "plusone/about.html")


def home(request):
    ensure_anonymous_session(request)
    return redirect("discover")


def start_anonymous_session(request):
    ensure_anonymous_session(request)
    return redirect(request.GET.get("next") or "discover")


def reset_anonymous_identity(request):
    if request.method != "POST":
        return redirect("session")
    logout(request)
    user = create_anonymous_user()
    request.session[ANONYMOUS_SESSION_USERNAME_KEY] = user.username
    login(request, user)
    messages.success(request, "A fresh temporary identity is ready.")
    return redirect("session")


def profile_setup(request):
    ensure_anonymous_session(request)
    profile = ensure_user_profile(request.user)
    if request.method == "POST":
        messages.success(request, "Your temporary identity is active.")
        return redirect(request.GET.get("next") or "discover")
    return render(request, "plusone/profile_setup.html", {"profile": profile})


@login_required
def create_post(request):
    refresh_expired_records()
    assist_form = ActivityAssistForm()
    initial = {"start_time": (timezone.localtime() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")}
    post_form = ActivityPostForm(initial=initial)
    parsed = None

    if request.method == "POST" and request.POST.get("action") == "assist":
        assist_form = ActivityAssistForm(request.POST)
        if assist_form.is_valid():
            parsed = parse_activity_text(request.user, assist_form.cleaned_data["raw_text"])
            post_form = ActivityPostForm(initial=_post_initial_from_ai(parsed))
            messages.success(request, "AI assistant drafted the activity card. Review it before publishing.")

    if request.method == "POST" and request.POST.get("action") == "publish":
        post_form = ActivityPostForm(request.POST)
        assist_form = ActivityAssistForm(initial={"raw_text": request.POST.get("raw_text", "")})
        if post_form.is_valid():
            moderation = moderate_text(request.user, f"{post_form.cleaned_data['title']} {post_form.cleaned_data['description']}")
            if moderation.get("flagged"):
                messages.error(request, f"Safety check flagged this post: {moderation.get('reason', 'Please revise it.')}")
            else:
                post = post_form.save_for_user(request.user)
                messages.success(request, "Your Plus One card is live.")
                return redirect("post_detail", post_id=post.id)

    return render(
        request,
        "plusone/create_post.html",
        {
            "assist_form": assist_form,
            "post_form": post_form,
            "parsed": parsed,
            "post_preview": _post_form_preview(post_form),
        },
    )


@login_required
def post_detail(request, post_id):
    refresh_expired_records()
    post = get_object_or_404(ActivityPost.objects.select_related("user", "location"), id=post_id)
    existing_swipe = Swipe.objects.filter(user=request.user, post=post).first()
    return render(
        request,
        "plusone/post_detail.html",
        {"post": post, "existing_swipe": existing_swipe},
    )


@login_required
def edit_post(request, post_id):
    refresh_expired_records()
    post = get_object_or_404(ActivityPost.objects.select_related("user", "location"), id=post_id)
    if post.user_id != request.user.id:
        return HttpResponseForbidden("Only the post owner can edit this Plus One.")
    if post.status != ActivityPost.Status.ACTIVE or post.is_expired:
        messages.error(request, "Only active, unexpired posts can be edited.")
        return redirect("dashboard")

    if request.method == "POST" and request.POST.get("action") == "cancel":
        post.status = ActivityPost.Status.CANCELLED
        post.save(update_fields=["status", "updated_at"])
        messages.info(request, "Your Plus One card was cancelled.")
        return redirect("dashboard")

    form = ActivityPostForm(initial=_post_edit_initial(post), instance=post)
    if request.method == "POST" and request.POST.get("action") == "save":
        form = ActivityPostForm(request.POST, instance=post)
        if form.is_valid():
            moderation = moderate_text(request.user, f"{form.cleaned_data['title']} {form.cleaned_data['description']}")
            if moderation.get("flagged"):
                messages.error(request, f"Safety check flagged this update: {moderation.get('reason', 'Please revise it.')}")
            else:
                form.save_for_user(request.user)
                messages.success(request, "Your Plus One card was updated.")
                return redirect("post_detail", post_id=post.id)

    return render(
        request,
        "plusone/edit_post.html",
        {"post": post, "post_form": form, "post_preview": _post_form_preview(form)},
    )


@login_required
def swipe_post(request, post_id):
    if request.method != "POST":
        return redirect("post_detail", post_id=post_id)
    refresh_expired_records()
    result = handle_swipe(request.user, post_id, request.POST.get("action"))
    if result.outcome == SwipeOutcome.OWN_POST:
        messages.error(request, "You cannot swipe on your own Plus One post.")
        return redirect("post_detail", post_id=result.post_id)
    if result.outcome == SwipeOutcome.INACTIVE_POST:
        messages.error(request, "This post is no longer active.")
        return redirect("discover")
    if result.outcome == SwipeOutcome.INVALID_ACTION:
        messages.error(request, "Unknown swipe action.")
        return redirect("post_detail", post_id=result.post_id)
    if result.outcome == SwipeOutcome.PASSED:
        messages.info(request, "Skipped. The queue is ready for the next card.")
        return redirect("discover")
    if result.outcome == SwipeOutcome.MATCH_CREATED:
        messages.success(request, "It's a vibe. You have five minutes to chat.")
        return redirect(f"{reverse('discover')}?matched={result.match_id}")
    messages.info(request, "You already matched on this post.")
    return redirect("chat", match_id=result.match_id)


@login_required
def dashboard(request):
    refresh_expired_records()
    active_posts = (
        ActivityPost.objects.filter(user=request.user, status=ActivityPost.Status.ACTIVE, expire_time__gt=timezone.now())
        .select_related("location")
    )
    expired_posts = ActivityPost.objects.filter(user=request.user).filter(Q(status=ActivityPost.Status.EXPIRED) | Q(expire_time__lte=timezone.now()))
    cancelled_posts = ActivityPost.objects.filter(user=request.user, status=ActivityPost.Status.CANCELLED).select_related("location")
    matches = Match.objects.filter(Q(poster=request.user) | Q(swiper=request.user)).select_related("post", "poster", "swiper", "post__location")
    open_chats_count = matches.filter(status=Match.Status.CHATTING).count()
    handoff_count = matches.filter(status=Match.Status.AGREED).count()
    return render(
        request,
        "plusone/dashboard.html",
        {
            "active_posts": active_posts,
            "open_chats_count": open_chats_count,
            "handoff_count": handoff_count,
            "expired_posts": expired_posts,
            "cancelled_posts": cancelled_posts,
            "matches": matches,
        },
    )


def _chat_message_payload(message, viewer):
    if message.is_system:
        sender_label = "Icebreaker"
        bubble_class = "system"
    elif message.sender_id == viewer.id:
        sender_label = "You"
        bubble_class = "mine"
    else:
        sender_label = "Anonymous match"
        bubble_class = "theirs"
    return {
        "id": message.id,
        "sender_label": sender_label,
        "bubble_class": bubble_class,
        "message": message.message,
        "created_at": timezone.localtime(message.created_at).strftime("%H:%M"),
        "is_flagged": message.is_flagged,
        "is_system": message.is_system,
    }


def _create_chat_message(match, user, text):
    moderation = moderate_text(user, text)
    message = ChatMessage.objects.create(
        match=match,
        sender=user,
        message=text,
        is_flagged=bool(moderation.get("flagged")),
    )
    return message, moderation


@login_required
def chat(request, match_id):
    refresh_expired_records()
    match = get_object_or_404(Match.objects.select_related("post", "poster", "swiper", "post__location"), id=match_id)
    if not match.is_participant(request.user):
        return HttpResponseForbidden("Only matched users can access this chat.")
    match.mark_chat_expired_if_needed()
    form = ChatMessageForm()

    if request.method == "POST" and request.POST.get("action") == "send":
        form = ChatMessageForm(request.POST)
        if match.status != Match.Status.CHATTING:
            messages.error(request, "This chat is no longer active.")
        elif form.is_valid():
            text = form.cleaned_data["message"]
            _, moderation = _create_chat_message(match, request.user, text)
            if moderation.get("flagged"):
                messages.warning(request, f"Message sent but flagged for review: {moderation.get('reason', 'Safety check triggered.')}")
            return redirect("chat", match_id=match.id)

    if request.method == "POST" and request.POST.get("action") == "agree":
        agreement = record_agreement(match.id, request.user)
        if agreement.recorded:
            messages.success(request, "Your agreement was recorded.")
        return redirect("chat", match_id=match.id)

    viewer_agreed = match.poster_agreed if request.user.id == match.poster_id else match.swiper_agreed
    other_agreed = match.swiper_agreed if request.user.id == match.poster_id else match.poster_agreed
    return render(
        request,
        "plusone/chat.html",
        {
            "match": match,
            "messages_list": match.messages.select_related("sender"),
            "form": form,
            "viewer_agreed": viewer_agreed,
            "other_agreed": other_agreed,
        },
    )


@login_required
def chat_messages(request, match_id):
    refresh_expired_records()
    match = get_object_or_404(Match.objects.select_related("post", "poster", "swiper"), id=match_id)
    if not match.is_participant(request.user):
        return HttpResponseForbidden("Only matched users can access this chat.")
    match.mark_chat_expired_if_needed()

    if request.method == "POST":
        form = ChatMessageForm(request.POST)
        if match.status != Match.Status.CHATTING:
            return JsonResponse({"ok": False, "error": "This chat is no longer active."}, status=409)
        if not form.is_valid():
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        message, moderation = _create_chat_message(match, request.user, form.cleaned_data["message"])
        return JsonResponse(
            {
                "ok": True,
                "message": _chat_message_payload(message, request.user),
                "flagged": bool(moderation.get("flagged")),
                "warning": moderation.get("reason", "") if moderation.get("flagged") else "",
            }
        )

    after_id = request.GET.get("after")
    message_qs = match.messages.select_related("sender")
    if after_id and after_id.isdigit():
        message_qs = message_qs.filter(id__gt=int(after_id))
    payload = [_chat_message_payload(message, request.user) for message in message_qs]
    return JsonResponse(
        {
            "ok": True,
            "messages": payload,
            "chat_status": match.status,
            "chat_active": match.status == Match.Status.CHATTING,
        }
    )
