from datetime import date

from django.core.management.base import BaseCommand

from apps.invoicing.services import run_daily_jobs


class Command(BaseCommand):
    help = (
        "Activate subscriptions that start today, run billing, close expired "
        "auto-close subscriptions and send overdue reminders. Schedule once a day."
    )

    def add_arguments(self, parser):
        parser.add_argument("--as-of", type=date.fromisoformat, default=None)

    def handle(self, *args, as_of=None, **options):
        result = run_daily_jobs(as_of)
        self.stdout.write(self.style.SUCCESS(f"Daily jobs done: {result}"))
