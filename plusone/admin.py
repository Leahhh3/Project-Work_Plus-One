from django.contrib import admin

from .models import ActivityPost, CampusLocation, ChatMessage, LLMLog, Match, Swipe, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "major", "year", "campus_area")
    search_fields = ("display_name", "user__username", "major", "campus_area")


@admin.register(CampusLocation)
class CampusLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "location_type", "area")
    list_filter = ("location_type", "area")
    search_fields = ("name", "area")


@admin.register(ActivityPost)
class ActivityPostAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "activity_type", "location", "start_time", "expire_time", "status")
    list_filter = ("activity_type", "status", "location")
    search_fields = ("title", "description", "user__username")


@admin.register(Swipe)
class SwipeAdmin(admin.ModelAdmin):
    list_display = ("user", "post", "action", "created_at")
    list_filter = ("action",)


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("post", "poster", "swiper", "status", "created_at", "chat_expires_at")
    list_filter = ("status",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("match", "sender", "is_system", "is_flagged", "created_at")
    list_filter = ("is_flagged", "is_system")
    search_fields = ("message",)


@admin.register(LLMLog)
class LLMLogAdmin(admin.ModelAdmin):
    list_display = ("task_type", "strategy", "model", "success", "latency_ms", "created_at")
    list_filter = ("task_type", "strategy", "success")
    search_fields = ("input_text", "output_text")
