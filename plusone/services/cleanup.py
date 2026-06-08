from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from plusone.models import ActivityPost, Match


def stale_anonymous_users(days=7):
    cutoff = timezone.now() - timedelta(days=days)
    User = get_user_model()
    active_post = Q(
        activity_posts__status__in=[ActivityPost.Status.ACTIVE, ActivityPost.Status.MATCHED],
        activity_posts__expire_time__gt=timezone.now(),
    )
    active_posted_match = Q(
        posted_matches__status=Match.Status.CHATTING,
        posted_matches__chat_expires_at__gt=timezone.now(),
    )
    active_swiped_match = Q(
        swiped_matches__status=Match.Status.CHATTING,
        swiped_matches__chat_expires_at__gt=timezone.now(),
    )
    stale_identity = Q(last_login__lt=cutoff) | Q(last_login__isnull=True, date_joined__lt=cutoff)
    return (
        User.objects.filter(username__startswith="anon_")
        .filter(stale_identity)
        .exclude(active_post | active_posted_match | active_swiped_match)
        .distinct()
    )


def cleanup_anonymous_users(days=7, dry_run=True):
    users = stale_anonymous_users(days=days)
    count = users.count()
    if dry_run:
        return count
    users.delete()
    return count
