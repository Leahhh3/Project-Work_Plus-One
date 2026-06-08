from django.core.management.base import BaseCommand

from plusone.services.cleanup import cleanup_anonymous_users


class Command(BaseCommand):
    help = "Delete stale anonymous identities that no longer have active posts or chats."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7, help="Minimum stale age in days.")
        parser.add_argument("--commit", action="store_true", help="Actually delete matching users.")

    def handle(self, *args, **options):
        count = cleanup_anonymous_users(days=options["days"], dry_run=not options["commit"])
        if options["commit"]:
            self.stdout.write(self.style.SUCCESS(f"Deleted {count} stale anonymous record(s)."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run: {count} stale anonymous user(s) would be deleted. Use --commit to apply."
                )
            )
