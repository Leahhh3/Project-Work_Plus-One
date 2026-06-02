from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .ai import parse_activity_text
from .models import ActivityPost, CampusLocation, ChatMessage, LLMLog, Match, Swipe, UserProfile


class PlusOneTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.poster = User.objects.create_user(username="poster", password="pass")
        self.swiper = User.objects.create_user(username="swiper", password="pass")
        self.location = CampusLocation.objects.create(
            name="Campus Sports Hall",
            location_type=CampusLocation.LocationType.SPORTS,
            area="Central Campus",
        )
        CampusLocation.objects.create(
            name="Main Library",
            location_type=CampusLocation.LocationType.STUDY,
            area="Library Quad",
        )
        self.post = ActivityPost.objects.create(
            user=self.poster,
            title="Basketball game tonight",
            description="Join for a campus game.",
            activity_type=ActivityPost.ActivityType.SPORTS,
            location=self.location,
            start_time=timezone.now() + timedelta(hours=1),
            expire_time=timezone.now() + timedelta(minutes=45),
        )

    def test_create_activity_post_saves_fields(self):
        self.client.force_login(self.poster)
        response = self.client.post(
            reverse("create_post"),
            {
                "action": "publish",
                "title": "Study sprint",
                "description": "Focused session.",
                "activity_type": ActivityPost.ActivityType.STUDY,
                "location": self.location.id,
                "start_time": (timezone.localtime() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                "expire_minutes": "30",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ActivityPost.objects.filter(title="Study sprint", user=self.poster).exists())

    def test_unsafe_post_is_flagged_and_not_published(self):
        self.client.force_login(self.poster)
        response = self.client.post(
            reverse("create_post"),
            {
                "action": "publish",
                "title": "Bring a weapon to the game",
                "description": "unsafe demo text",
                "activity_type": ActivityPost.ActivityType.SPORTS,
                "location": self.location.id,
                "start_time": (timezone.localtime() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                "expire_minutes": "30",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ActivityPost.objects.filter(title="Bring a weapon to the game").exists())
        self.assertTrue(LLMLog.objects.filter(task_type=LLMLog.TaskType.MODERATION, output_json__flagged=True).exists())

    def test_owner_can_edit_active_post(self):
        self.client.force_login(self.poster)
        response = self.client.post(
            reverse("edit_post", args=[self.post.id]),
            {
                "action": "save",
                "title": "Updated basketball run",
                "description": "Updated safe description.",
                "activity_type": ActivityPost.ActivityType.SPORTS,
                "location": self.location.id,
                "start_time": (timezone.localtime() + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M"),
                "expire_minutes": "40",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, "Updated basketball run")

    def test_non_owner_cannot_edit_post(self):
        self.client.force_login(self.swiper)
        response = self.client.get(reverse("edit_post", args=[self.post.id]))

        self.assertEqual(response.status_code, 403)

    def test_owner_can_cancel_active_post(self):
        self.client.force_login(self.poster)
        response = self.client.post(reverse("edit_post", args=[self.post.id]), {"action": "cancel"})

        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, ActivityPost.Status.CANCELLED)

    def test_create_page_auto_logs_in_demo_user(self):
        response = self.client.get(reverse("create_post"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("create_post"))
        self.assertContains(response, "Create a temporary Plus One card.")
        self.assertTrue(get_user_model().objects.filter(username="demo_alex").exists())

    def test_profile_setup_saves_avatar_profile(self):
        self.client.force_login(self.swiper)
        response = self.client.post(
            reverse("profile_setup"),
            {
                "display_name": "Leah",
                "avatar_initial": "L",
                "campus_area": "Central Campus",
                "major": "Informatics",
                "year": "Master",
                "interests": "basketball, lunch",
            },
        )

        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=self.swiper)
        self.assertEqual(profile.display_name, "Leah")
        self.assertEqual(profile.initial, "L")
        self.assertEqual(profile.campus_area, "Central Campus")

    def test_homepage_starts_avatar_setup_without_manual_login(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create your campus avatar.")
        self.assertContains(response, "Avatar name")
        self.assertTrue(get_user_model().objects.filter(username="demo_alex").exists())

    def test_expired_posts_do_not_appear_in_discovery(self):
        self.post.expire_time = timezone.now() - timedelta(minutes=1)
        self.post.save()
        self.client.force_login(self.swiper)
        response = self.client.get(reverse("discover"))
        self.assertNotContains(response, self.post.title)

    def test_user_cannot_swipe_own_post(self):
        self.client.force_login(self.poster)
        response = self.client.post(reverse("swipe_post", args=[self.post.id]), {"action": Swipe.Action.INTERESTED})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Swipe.objects.exists())
        self.assertFalse(Match.objects.exists())

    def test_pass_does_not_create_match(self):
        self.client.force_login(self.swiper)
        response = self.client.post(reverse("swipe_post", args=[self.post.id]), {"action": Swipe.Action.PASS})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Swipe.objects.filter(action=Swipe.Action.PASS).exists())
        self.assertFalse(Match.objects.exists())

    def test_interested_creates_match_when_post_active(self):
        self.client.force_login(self.swiper)
        response = self.client.post(reverse("swipe_post", args=[self.post.id]), {"action": Swipe.Action.INTERESTED})
        self.assertEqual(response.status_code, 302)
        self.assertIn("?matched=", response["Location"])
        self.assertTrue(Match.objects.filter(post=self.post, swiper=self.swiper).exists())
        self.assertTrue(ChatMessage.objects.filter(is_system=True).exists())

    def test_discover_shows_match_modal_for_participant(self):
        match = Match.objects.create(
            post=self.post,
            poster=self.poster,
            swiper=self.swiper,
            chat_expires_at=timezone.now() + timedelta(minutes=5),
        )
        self.client.force_login(self.swiper)
        response = self.client.get(f"{reverse('discover')}?matched={match.id}")

        self.assertContains(response, "It's a vibe.")
        self.assertContains(response, reverse("chat", args=[match.id]))

    def test_chat_accessible_only_to_participants(self):
        outsider = get_user_model().objects.create_user(username="outsider", password="pass")
        match = Match.objects.create(
            post=self.post,
            poster=self.poster,
            swiper=self.swiper,
            chat_expires_at=timezone.now() + timedelta(minutes=5),
        )
        self.client.force_login(outsider)
        response = self.client.get(reverse("chat", args=[match.id]))
        self.assertEqual(response.status_code, 403)

    def test_chat_expires_after_configured_time(self):
        match = Match.objects.create(
            post=self.post,
            poster=self.poster,
            swiper=self.swiper,
            chat_expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.client.force_login(self.swiper)
        self.client.get(reverse("chat", args=[match.id]))
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.EXPIRED)

    def test_expired_chat_does_not_accept_new_message(self):
        match = Match.objects.create(
            post=self.post,
            poster=self.poster,
            swiper=self.swiper,
            chat_expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.client.force_login(self.swiper)
        response = self.client.post(reverse("chat", args=[match.id]), {"action": "send", "message": "Still there?"})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ChatMessage.objects.filter(match=match, sender=self.swiper).exists())

    def test_chat_message_moderation_logs_and_flags_message(self):
        match = Match.objects.create(
            post=self.post,
            poster=self.poster,
            swiper=self.swiper,
            chat_expires_at=timezone.now() + timedelta(minutes=5),
        )
        self.client.force_login(self.swiper)
        response = self.client.post(reverse("chat", args=[match.id]), {"action": "send", "message": "Here is my phone number"})

        self.assertEqual(response.status_code, 302)
        message = ChatMessage.objects.get(match=match, sender=self.swiper)
        self.assertTrue(message.is_flagged)
        self.assertTrue(LLMLog.objects.filter(task_type=LLMLog.TaskType.MODERATION, output_json__flagged=True).exists())

    def test_llm_parser_logs_output_with_fallback(self):
        result = parse_activity_text(self.poster, "Tonight 7pm basketball game at the sports hall")
        self.assertEqual(result["activity_type"], ActivityPost.ActivityType.SPORTS)
        self.assertTrue(LLMLog.objects.filter(task_type=LLMLog.TaskType.PARSE_POST).exists())

    def test_dashboard_separates_active_matches_expired(self):
        expired = ActivityPost.objects.create(
            user=self.poster,
            title="Old lunch",
            description="Expired",
            activity_type=ActivityPost.ActivityType.FOOD,
            location=self.location,
            start_time=timezone.now() - timedelta(hours=2),
            expire_time=timezone.now() - timedelta(hours=1),
            status=ActivityPost.Status.EXPIRED,
        )
        Match.objects.create(
            post=self.post,
            poster=self.poster,
            swiper=self.swiper,
            chat_expires_at=timezone.now() + timedelta(minutes=5),
        )
        cancelled = ActivityPost.objects.create(
            user=self.poster,
            title="Cancelled coffee",
            description="Cancelled",
            activity_type=ActivityPost.ActivityType.FOOD,
            location=self.location,
            start_time=timezone.now() + timedelta(hours=2),
            expire_time=timezone.now() + timedelta(minutes=30),
            status=ActivityPost.Status.CANCELLED,
        )
        self.client.force_login(self.poster)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, self.post.title)
        self.assertContains(response, expired.title)
        self.assertContains(response, cancelled.title)
