from django.db import models
from django.utils import timezone


class ActivityPost(models.Model):
    FOOD = "food"
    SPORTS = "sports"
    STUDY = "study"
    EXPLORE = "explore"
    CLUB = "club"

    ACTIVITY_TYPES = [
        (FOOD, "Food"),
        (SPORTS, "Sports"),
        (STUDY, "Study"),
        (EXPLORE, "Explore"),
        (CLUB, "Club fair"),
    ]

    title = models.CharField(max_length=90)
    description = models.TextField(max_length=240)
    location = models.CharField(max_length=90)
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    host_alias = models.CharField(max_length=60, default="Anonymous student")
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    vibe_note = models.CharField(max_length=120, blank=True)
    accent = models.CharField(max_length=7, default="#12C6C1")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at", "-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_active(self):
        return self.expires_at > timezone.now()

    @property
    def minutes_left(self):
        remaining = self.expires_at - timezone.now()
        return max(0, int(remaining.total_seconds() // 60))


class Swipe(models.Model):
    LEFT = "left"
    RIGHT = "right"
    DIRECTIONS = [(LEFT, "Left"), (RIGHT, "Right")]

    post = models.ForeignKey(ActivityPost, on_delete=models.CASCADE, related_name="swipes")
    swiper_alias = models.CharField(max_length=60, default="You")
    direction = models.CharField(max_length=10, choices=DIRECTIONS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.swiper_alias} swiped {self.direction} on {self.post}"


class Match(models.Model):
    post = models.ForeignKey(ActivityPost, on_delete=models.CASCADE, related_name="matches")
    participant_alias = models.CharField(max_length=60, default="Anonymous plus one")
    chat_expires_at = models.DateTimeField()
    host_agreed = models.BooleanField(default=False)
    guest_agreed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Match for {self.post}"

    @property
    def seconds_left(self):
        remaining = self.chat_expires_at - timezone.now()
        return max(0, int(remaining.total_seconds()))

    @property
    def is_ready_to_meet(self):
        return self.host_agreed and self.guest_agreed


class ChatMessage(models.Model):
    YOU = "you"
    THEM = "them"
    SENDERS = [(YOU, "You"), (THEM, "Them")]

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="messages")
    sender = models.CharField(max_length=10, choices=SENDERS)
    body = models.CharField(max_length=240)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender}: {self.body[:40]}"
