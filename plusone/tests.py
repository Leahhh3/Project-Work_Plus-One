from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
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
                "description": "unsafe product text",
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

    def test_create_page_auto_starts_anonymous_session(self):
        response = self.client.get(reverse("create_post"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("create_post"))
        self.assertContains(response, "Create a temporary Plus One card.")
        self.assertTrue(get_user_model().objects.filter(username__startswith="anon_").exists())

    def test_anonymous_session_reuses_same_identity(self):
        User = get_user_model()

        self.client.get(reverse("home"))
        first_user_id = self.client.session["_auth_user_id"]
        self.client.get(reverse("discover"))
        second_user_id = self.client.session["_auth_user_id"]

        self.assertEqual(first_user_id, second_user_id)
        self.assertEqual(User.objects.filter(username__startswith="anon_").count(), 1)

    def test_home_redirects_to_discover_with_anonymous_session(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("discover"))
        self.assertTrue(get_user_model().objects.filter(username__startswith="anon_").exists())

    def test_reset_anonymous_identity_creates_fresh_session_user(self):
        User = get_user_model()

        self.client.get(reverse("home"))
        first_user_id = self.client.session["_auth_user_id"]
        response = self.client.post(reverse("reset_anonymous_identity"))
        second_user_id = self.client.session["_auth_user_id"]

        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(first_user_id, second_user_id)
        self.assertEqual(User.objects.filter(username__startswith="anon_").count(), 2)

    def test_profile_setup_enters_discover_without_collecting_profile_fields(self):
        response = self.client.post(reverse("profile_setup"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("discover"))
        profile = UserProfile.objects.get(user_id=self.client.session["_auth_user_id"])
        self.assertTrue(profile.display_name.startswith("Campus Guest "))

    def test_session_page_explains_anonymous_visibility_without_profile_fields(self):
        response = self.client.get(reverse("session"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You're anonymous here.")
        self.assertContains(response, "What others can see")
        self.assertContains(response, "What stays hidden")
        self.assertContains(response, "data-confirm-reset")
        self.assertNotContains(response, "Temporary name")
        self.assertTrue(get_user_model().objects.filter(username__startswith="anon_").exists())

    def test_anonymous_users_can_create_match_and_chat(self):
        User = get_user_model()
        creator = Client()
        swiper = Client()

        creator.get(reverse("home"))
        creator_user = User.objects.get(id=creator.session["_auth_user_id"])
        create_response = creator.post(
            reverse("create_post"),
            {
                "action": "publish",
                "title": "Anonymous coffee",
                "description": "Quick coffee before class.",
                "activity_type": ActivityPost.ActivityType.FOOD,
                "location": self.location.id,
                "start_time": (timezone.localtime() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                "expire_minutes": "30",
            },
        )
        self.assertEqual(create_response.status_code, 302)
        post = ActivityPost.objects.get(title="Anonymous coffee")
        self.assertEqual(post.user, creator_user)

        swiper.get(reverse("home"))
        swiper_user = User.objects.get(id=swiper.session["_auth_user_id"])
        swipe_response = swiper.post(reverse("swipe_post", args=[post.id]), {"action": Swipe.Action.INTERESTED})
        self.assertEqual(swipe_response.status_code, 302)

        match = Match.objects.get(post=post, swiper=swiper_user)
        chat_response = swiper.get(reverse("chat", args=[match.id]))
        self.assertEqual(chat_response.status_code, 200)
        self.assertContains(chat_response, "Anonymous vibe chat")

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

    def test_matched_post_does_not_create_second_match(self):
        other = get_user_model().objects.create_user(username="other", password="pass")

        self.client.force_login(self.swiper)
        self.client.post(reverse("swipe_post", args=[self.post.id]), {"action": Swipe.Action.INTERESTED})

        self.client.force_login(other)
        response = self.client.post(reverse("swipe_post", args=[self.post.id]), {"action": Swipe.Action.INTERESTED})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("discover"))
        self.assertEqual(Match.objects.filter(post=self.post).count(), 1)

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

    def test_agree_on_expired_chat_does_not_record_agreement(self):
        match = Match.objects.create(
            post=self.post,
            poster=self.poster,
            swiper=self.swiper,
            chat_expires_at=timezone.now() - timedelta(seconds=1),
        )

        self.client.force_login(self.swiper)
        response = self.client.post(reverse("chat", args=[match.id]), {"action": "agree"})

        match.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(match.status, Match.Status.EXPIRED)
        self.assertFalse(match.swiper_agreed)

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

    def test_single_agree_shows_waiting_state(self):
        match = Match.objects.create(
            post=self.post,
            poster=self.poster,
            swiper=self.swiper,
            chat_expires_at=timezone.now() + timedelta(minutes=5),
        )

        self.client.force_login(self.swiper)
        response = self.client.post(reverse("chat", args=[match.id]), {"action": "agree"}, follow=True)

        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.CHATTING)
        self.assertTrue(match.swiper_agreed)
        self.assertContains(response, "You agreed. Waiting for the other person.")
        self.assertNotContains(response, "You both agreed to meet.")

    def test_both_agree_shows_meet_handoff_and_closes_input(self):
        match = Match.objects.create(
            post=self.post,
            poster=self.poster,
            swiper=self.swiper,
            chat_expires_at=timezone.now() + timedelta(minutes=5),
        )
        match.mark_agreed(self.swiper)

        self.client.force_login(self.poster)
        response = self.client.post(reverse("chat", args=[match.id]), {"action": "agree"}, follow=True)

        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.AGREED)
        self.assertContains(response, "You both agreed to meet.")
        self.assertContains(response, self.post.location.name)
        self.assertContains(response, "Meet in a public place.")
        self.assertContains(response, "Back to Dashboard")
        self.assertNotContains(response, "Type fast... this chat expires soon.")

    def test_agreed_match_does_not_accept_new_message(self):
        match = Match.objects.create(
            post=self.post,
            poster=self.poster,
            swiper=self.swiper,
            status=Match.Status.AGREED,
            poster_agreed=True,
            swiper_agreed=True,
            chat_expires_at=timezone.now() + timedelta(minutes=5),
        )

        self.client.force_login(self.swiper)
        response = self.client.post(reverse("chat", args=[match.id]), {"action": "send", "message": "After agree"})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ChatMessage.objects.filter(match=match, message="After agree").exists())

    def test_chat_messages_endpoint_returns_messages_after_id(self):
        match = Match.objects.create(
            post=self.post,
            poster=self.poster,
            swiper=self.swiper,
            chat_expires_at=timezone.now() + timedelta(minutes=5),
        )
        first = ChatMessage.objects.create(match=match, sender=self.poster, message="First")
        second = ChatMessage.objects.create(match=match, sender=self.swiper, message="Second")

        self.client.force_login(self.poster)
        response = self.client.get(f"{reverse('chat_messages', args=[match.id])}?after={first.id}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual([message["id"] for message in data["messages"]], [second.id])
        self.assertEqual(data["messages"][0]["sender_label"], "Anonymous match")

    def test_chat_messages_endpoint_posts_message_json(self):
        match = Match.objects.create(
            post=self.post,
            poster=self.poster,
            swiper=self.swiper,
            chat_expires_at=timezone.now() + timedelta(minutes=5),
        )

        self.client.force_login(self.swiper)
        response = self.client.post(reverse("chat_messages", args=[match.id]), {"message": "See you there"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"]["message"], "See you there")
        self.assertEqual(data["message"]["sender_label"], "You")
        self.assertTrue(ChatMessage.objects.filter(match=match, sender=self.swiper, message="See you there").exists())

    def test_chat_messages_endpoint_reports_inactive_after_agreement(self):
        match = Match.objects.create(
            post=self.post,
            poster=self.poster,
            swiper=self.swiper,
            status=Match.Status.AGREED,
            poster_agreed=True,
            swiper_agreed=True,
            chat_expires_at=timezone.now() + timedelta(minutes=5),
        )

        self.client.force_login(self.poster)
        response = self.client.get(reverse("chat_messages", args=[match.id]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["chat_status"], Match.Status.AGREED)
        self.assertFalse(data["chat_active"])

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
        agreed_post = ActivityPost.objects.create(
            user=self.poster,
            title="Agreed handoff",
            description="Ready to meet",
            activity_type=ActivityPost.ActivityType.STUDY,
            location=self.location,
            start_time=timezone.now() + timedelta(hours=2),
            expire_time=timezone.now() + timedelta(minutes=45),
            status=ActivityPost.Status.MATCHED,
        )
        Match.objects.create(
            post=agreed_post,
            poster=self.poster,
            swiper=self.swiper,
            status=Match.Status.AGREED,
            poster_agreed=True,
            swiper_agreed=True,
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
        self.assertContains(response, "open chats")
        self.assertContains(response, "meet handoffs")
        self.assertNotContains(response, "students swiped right")

    def test_expire_records_command_marks_old_posts_and_chats(self):
        self.post.expire_time = timezone.now() - timedelta(minutes=1)
        self.post.save(update_fields=["expire_time"])
        match = Match.objects.create(
            post=self.post,
            poster=self.poster,
            swiper=self.swiper,
            chat_expires_at=timezone.now() - timedelta(seconds=1),
        )

        output = StringIO()
        call_command("expire_records", stdout=output)

        self.post.refresh_from_db()
        match.refresh_from_db()
        self.assertEqual(self.post.status, ActivityPost.Status.EXPIRED)
        self.assertEqual(match.status, Match.Status.EXPIRED)
        self.assertIn("Expired", output.getvalue())

    def test_cleanup_anonymous_sessions_dry_run_does_not_delete(self):
        User = get_user_model()
        old_user = User.objects.create_user(username="anon_old")
        old_user.date_joined = timezone.now() - timedelta(days=10)
        old_user.last_login = timezone.now() - timedelta(days=10)
        old_user.save(update_fields=["date_joined", "last_login"])

        output = StringIO()
        call_command("cleanup_anonymous_sessions", "--days", "7", stdout=output)

        self.assertTrue(User.objects.filter(username="anon_old").exists())
        self.assertIn("Dry run", output.getvalue())

    def test_cleanup_anonymous_sessions_commit_keeps_live_identity(self):
        User = get_user_model()
        stale_user = User.objects.create_user(username="anon_stale")
        stale_user.date_joined = timezone.now() - timedelta(days=10)
        stale_user.last_login = timezone.now() - timedelta(days=10)
        stale_user.save(update_fields=["date_joined", "last_login"])
        live_user = User.objects.create_user(username="anon_live")
        live_user.date_joined = timezone.now() - timedelta(days=10)
        live_user.last_login = timezone.now() - timedelta(days=10)
        live_user.save(update_fields=["date_joined", "last_login"])
        ActivityPost.objects.create(
            user=live_user,
            title="Live anonymous post",
            description="Still active",
            activity_type=ActivityPost.ActivityType.STUDY,
            location=self.location,
            start_time=timezone.now() + timedelta(hours=1),
            expire_time=timezone.now() + timedelta(minutes=30),
        )

        call_command("cleanup_anonymous_sessions", "--days", "7", "--commit", stdout=StringIO())

        self.assertFalse(User.objects.filter(username="anon_stale").exists())
        self.assertTrue(User.objects.filter(username="anon_live").exists())
