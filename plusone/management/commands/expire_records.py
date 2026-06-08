from django.core.management.base import BaseCommand

from plusone.services.expiration import refresh_expired_records


class Command(BaseCommand):
    help = "Mark expired Plus One posts and chats without changing any other product state."

    def handle(self, *args, **options):
        counts = refresh_expired_records()
        self.stdout.write(
            self.style.SUCCESS(
                f"Expired {counts['posts']} post(s) and {counts['matches']} chat(s)."
            )
        )
