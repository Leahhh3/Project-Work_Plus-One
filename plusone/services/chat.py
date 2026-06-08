from dataclasses import dataclass

from django.db import transaction
from django.shortcuts import get_object_or_404

from plusone.models import Match


@dataclass(frozen=True)
class AgreementResult:
    recorded: bool
    match_id: int


def record_agreement(match_id, user):
    with transaction.atomic():
        match = get_object_or_404(
            Match.objects.select_for_update().select_related("post", "poster", "swiper", "post__location"),
            id=match_id,
        )
        if not match.is_participant(user):
            return AgreementResult(False, match.id)

        match.mark_chat_expired_if_needed()
        if match.status != Match.Status.CHATTING:
            return AgreementResult(False, match.id)

        match.mark_agreed(user)
        return AgreementResult(True, match.id)
