from django.utils import timezone

from plusone.models import ActivityPost, Match


def refresh_expired_records():
    now = timezone.now()
    expired_posts = ActivityPost.objects.filter(
        status=ActivityPost.Status.ACTIVE,
        expire_time__lte=now,
    ).update(status=ActivityPost.Status.EXPIRED)
    expired_matches = Match.objects.filter(
        status=Match.Status.CHATTING,
        chat_expires_at__lte=now,
    ).update(status=Match.Status.EXPIRED)
    return {"posts": expired_posts, "matches": expired_matches}
