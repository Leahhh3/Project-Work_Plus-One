from django.core.management.base import BaseCommand

from plusone.ai import rule_moderate_text, rule_parse_activity
from plusone.models import ActivityPost, CampusLocation


SAMPLES = [
    ("Tonight 7pm basketball game at the sports hall", ActivityPost.ActivityType.SPORTS, "Campus Sports Hall"),
    ("Lunch at mensa around 12:30", ActivityPost.ActivityType.FOOD, "North Dining Hall"),
    ("Study sprint in the library after class", ActivityPost.ActivityType.STUDY, "Main Library"),
    ("Explore the club fair at student center", ActivityPost.ActivityType.CLUB, "Student Center"),
    ("Walk around the campus quad tomorrow", ActivityPost.ActivityType.EXPLORE, "Campus Quad"),
    ("Coffee and homework in the library", ActivityPost.ActivityType.STUDY, "Main Library"),
    ("Dinner near the dining hall at 6pm", ActivityPost.ActivityType.FOOD, "North Dining Hall"),
    ("Go to the gym for a basketball pickup", ActivityPost.ActivityType.SPORTS, "Campus Sports Hall"),
    ("Check out booths at the club fair", ActivityPost.ActivityType.CLUB, "Student Center"),
    ("Quick campus walk at 5", ActivityPost.ActivityType.EXPLORE, "Campus Quad"),
    ("Meet for lunch before lecture", ActivityPost.ActivityType.FOOD, "North Dining Hall"),
    ("Library focus session tonight", ActivityPost.ActivityType.STUDY, "Main Library"),
    ("Watch the game tonight around seven", ActivityPost.ActivityType.SPORTS, "Campus Sports Hall"),
    ("Browse student organization booths", ActivityPost.ActivityType.CLUB, "Student Center"),
    ("Explore campus after class", ActivityPost.ActivityType.EXPLORE, "Campus Quad"),
]

SAFETY_SAMPLES = [
    ("Let's meet at the library entrance.", False),
    ("Send me your phone number and address.", True),
    ("I will bring a weapon.", True),
    ("Let's grab lunch before class.", False),
    ("Come alone in my room.", True),
]


class Command(BaseCommand):
    help = "Evaluate Plus One rule-based AI fallback on sample parsing and moderation cases."

    def handle(self, *args, **options):
        if not CampusLocation.objects.exists():
            self.stdout.write(self.style.WARNING("No campus locations found. Run python manage.py seed_demo first."))
            return

        correct_type = 0
        correct_location = 0
        for text, expected_type, expected_location in SAMPLES:
            result = rule_parse_activity(text)
            correct_type += result["activity_type"] == expected_type
            correct_location += result["location_name"] == expected_location

        safety_correct = 0
        for text, expected_flag in SAFETY_SAMPLES:
            result = rule_moderate_text(text)
            safety_correct += bool(result["flagged"]) == expected_flag

        rows = [
            ("Rule fallback activity type accuracy", f"{correct_type}/{len(SAMPLES)}"),
            ("Rule fallback location accuracy", f"{correct_location}/{len(SAMPLES)}"),
            ("Rule fallback safety accuracy", f"{safety_correct}/{len(SAFETY_SAMPLES)}"),
            ("LLM strategy", "Available at runtime when OPENAI_API_KEY is set; outputs are logged in LLMLog."),
        ]
        self.stdout.write("Plus One AI evaluation summary")
        self.stdout.write("-" * 36)
        for label, value in rows:
            self.stdout.write(f"{label}: {value}")
