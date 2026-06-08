from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from plusone.ai import generate_icebreaker
from plusone.models import ActivityPost, ChatMessage, Match, Swipe


class SwipeOutcome:
    OWN_POST = "own_post"
    INACTIVE_POST = "inactive_post"
    INVALID_ACTION = "invalid_action"
    PASSED = "passed"
    MATCH_CREATED = "match_created"
    MATCH_EXISTS = "match_exists"


@dataclass(frozen=True)
class SwipeResult:
    outcome: str
    post_id: int
    match_id: int | None = None


def handle_swipe(user, post_id, action):
    created_match = None

    with transaction.atomic():
        post = get_object_or_404(
            ActivityPost.objects.select_for_update().select_related("user", "location"),
            id=post_id,
        )
        if post.user_id == user.id:
            return SwipeResult(SwipeOutcome.OWN_POST, post.id)
        if post.is_expired or post.status != ActivityPost.Status.ACTIVE:
            return SwipeResult(SwipeOutcome.INACTIVE_POST, post.id)
        if action not in [Swipe.Action.INTERESTED, Swipe.Action.PASS]:
            return SwipeResult(SwipeOutcome.INVALID_ACTION, post.id)

        Swipe.objects.update_or_create(user=user, post=post, defaults={"action": action})
        if action == Swipe.Action.PASS:
            return SwipeResult(SwipeOutcome.PASSED, post.id)

        match, created = Match.objects.get_or_create(
            post=post,
            swiper=user,
            defaults={
                "poster": post.user,
                "chat_expires_at": timezone.now() + timedelta(minutes=5),
            },
        )
        if not created:
            return SwipeResult(SwipeOutcome.MATCH_EXISTS, post.id, match.id)

        post.status = ActivityPost.Status.MATCHED
        post.save(update_fields=["status", "updated_at"])
        created_match = match

    icebreaker = generate_icebreaker(user, post)
    ChatMessage.objects.create(match=created_match, sender=None, message=icebreaker, is_system=True)
    return SwipeResult(SwipeOutcome.MATCH_CREATED, post.id, created_match.id)
