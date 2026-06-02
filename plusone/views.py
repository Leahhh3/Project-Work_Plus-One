from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .ai import generate_icebreaker, moderate_text, parse_activity_text
from .forms import ActivityAssistForm, ActivityPostForm, ChatMessageForm, UserProfileForm
from .models import ActivityPost, CampusLocation, ChatMessage, Match, Swipe, UserProfile


DEMO_USERS = {
    "demo_alex": {
        "display_name": "Alex Chen",
        "avatar_initial": "A",
        "major": "Computer Science",
        "year": "Sophomore",
        "campus_area": "North Campus",
        "interests": "basketball, lunch, study sprints",
    },
    "demo_blair": {
        "display_name": "Blair Morgan",
        "avatar_initial": "B",
        "major": "Design",
        "year": "Junior",
        "campus_area": "Central Campus",
        "interests": "club fairs, campus events, coffee",
    },
}


def ensure_demo_user(username="demo_alex"):
    User = get_user_model()
    data = DEMO_USERS.get(username, DEMO_USERS["demo_alex"])
    user, created = User.objects.get_or_create(username=username, defaults={"email": f"{username}@example.edu"})
    if created:
        user.set_password("plusone123")
        user.save()
    UserProfile.objects.get_or_create(user=user, defaults=data)
    return user


def ensure_user_profile(user):
    defaults = {
        "display_name": user.get_full_name() or user.username,
        "avatar_initial": (user.username[:1] or "S").upper(),
    }
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults=defaults)
    if not profile.avatar_initial:
        profile.avatar_initial = (profile.display_name[:1] or user.username[:1] or "S").upper()
        profile.save(update_fields=["avatar_initial"])
    return profile


def ensure_authenticated_demo(request):
    if not request.user.is_authenticated:
        login(request, ensure_demo_user())


def refresh_expired_records():
    now = timezone.now()
    ActivityPost.objects.filter(status=ActivityPost.Status.ACTIVE, expire_time__lte=now).update(status=ActivityPost.Status.EXPIRED)
    Match.objects.filter(status=Match.Status.CHATTING, chat_expires_at__lte=now).update(status=Match.Status.EXPIRED)


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
    ensure_authenticated_demo(request)
    refresh_expired_records()
    activity_type = request.GET.get("activity_type", "")
    location_id = request.GET.get("location", "")
    time_window = request.GET.get("time_window", "")
    matched_id = request.GET.get("matched")
    swiped_ids = Swipe.objects.filter(user=request.user).values_list("post_id", flat=True)
    posts = (
        ActivityPost.objects.active()
        .exclude(user=request.user)
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
        "demo_users": DEMO_USERS,
    }
    return render(request, "plusone/discover.html", context)


def about(request):
    ensure_authenticated_demo(request)
    return render(request, "plusone/about.html", {"demo_users": DEMO_USERS})


def login_demo(request):
    login(request, ensure_demo_user())
    return redirect(request.GET.get("next") or "discover")


def profile_setup(request):
    ensure_authenticated_demo(request)
    profile = ensure_user_profile(request.user)
    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Your campus profile is ready.")
            return redirect(request.GET.get("next") or "discover")
    else:
        form = UserProfileForm(instance=profile)
    return render(request, "plusone/profile_setup.html", {"form": form, "profile": profile, "demo_users": DEMO_USERS})


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
            "demo_users": DEMO_USERS,
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
        {"post": post, "existing_swipe": existing_swipe, "demo_users": DEMO_USERS},
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
        {"post": post, "post_form": form, "post_preview": _post_form_preview(form), "demo_users": DEMO_USERS},
    )


@login_required
def swipe_post(request, post_id):
    if request.method != "POST":
        return redirect("post_detail", post_id=post_id)
    refresh_expired_records()
    post = get_object_or_404(ActivityPost.objects.select_related("user", "location"), id=post_id)
    action = request.POST.get("action")
    if post.user_id == request.user.id:
        messages.error(request, "You cannot swipe on your own Plus One post.")
        return redirect("post_detail", post_id=post.id)
    if post.is_expired or post.status != ActivityPost.Status.ACTIVE:
        messages.error(request, "This post is no longer active.")
        return redirect("discover")
    if action not in [Swipe.Action.INTERESTED, Swipe.Action.PASS]:
        messages.error(request, "Unknown swipe action.")
        return redirect("post_detail", post_id=post.id)

    Swipe.objects.update_or_create(user=request.user, post=post, defaults={"action": action})
    if action == Swipe.Action.PASS:
        messages.info(request, "Skipped. The queue is ready for the next card.")
        return redirect("discover")

    match, created = Match.objects.get_or_create(
        post=post,
        swiper=request.user,
        defaults={
            "poster": post.user,
            "chat_expires_at": timezone.now() + timedelta(minutes=5),
        },
    )
    if created:
        post.status = ActivityPost.Status.MATCHED
        post.save(update_fields=["status", "updated_at"])
        icebreaker = generate_icebreaker(request.user, post)
        ChatMessage.objects.create(match=match, sender=None, message=icebreaker, is_system=True)
        messages.success(request, "It's a vibe. You have five minutes to chat.")
        return redirect(f"{reverse('discover')}?matched={match.id}")
    else:
        messages.info(request, "You already matched on this post.")
    return redirect("chat", match_id=match.id)


@login_required
def dashboard(request):
    refresh_expired_records()
    active_posts = (
        ActivityPost.objects.filter(user=request.user, status=ActivityPost.Status.ACTIVE, expire_time__gt=timezone.now())
        .select_related("location")
        .annotate(interested_count=Count("swipes", filter=Q(swipes__action=Swipe.Action.INTERESTED)))
    )
    expired_posts = ActivityPost.objects.filter(user=request.user).filter(Q(status=ActivityPost.Status.EXPIRED) | Q(expire_time__lte=timezone.now()))
    cancelled_posts = ActivityPost.objects.filter(user=request.user, status=ActivityPost.Status.CANCELLED).select_related("location")
    matches = Match.objects.filter(Q(poster=request.user) | Q(swiper=request.user)).select_related("post", "poster", "swiper", "post__location")
    return render(
        request,
        "plusone/dashboard.html",
        {
            "active_posts": active_posts,
            "interested_total": sum(post.interested_count for post in active_posts),
            "expired_posts": expired_posts,
            "cancelled_posts": cancelled_posts,
            "matches": matches,
            "demo_users": DEMO_USERS,
        },
    )


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
            moderation = moderate_text(request.user, text)
            ChatMessage.objects.create(
                match=match,
                sender=request.user,
                message=text,
                is_flagged=bool(moderation.get("flagged")),
            )
            if moderation.get("flagged"):
                messages.warning(request, f"Message sent but flagged for review: {moderation.get('reason', 'Safety check triggered.')}")
            return redirect("chat", match_id=match.id)

    if request.method == "POST" and request.POST.get("action") == "agree":
        if match.status == Match.Status.CHATTING:
            match.mark_agreed(request.user)
            messages.success(request, "Your agreement was recorded.")
        return redirect("chat", match_id=match.id)

    return render(
        request,
        "plusone/chat.html",
        {"match": match, "messages_list": match.messages.select_related("sender"), "form": form, "demo_users": DEMO_USERS},
    )


def switch_demo_user(request, username):
    user = ensure_demo_user(username)
    login(request, user)
    messages.success(request, f"Switched demo user to {user.profile.display_name if hasattr(user, 'profile') else user.username}.")
    return redirect(request.GET.get("next") or "discover")
