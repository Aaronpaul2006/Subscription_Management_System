import time
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.invoicing.services import run_daily_jobs


class Command(BaseCommand):
    help = "Long-running scheduler: runs the daily jobs every day at --at (default 06:00)."

    def add_arguments(self, parser):
        parser.add_argument("--at", default="06:00", help="Local time HH:MM")
        parser.add_argument("--now", action="store_true", help="Also run once at start-up")

    def handle(self, *args, at="06:00", now=False, **options):
        hour, minute = (int(x) for x in at.split(":"))
        if now:
            self.stdout.write(f"{run_daily_jobs()}")
        while True:
            current = timezone.localtime()
            target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= current:
                target += timedelta(days=1)
            wait = (target - current).total_seconds()
            self.stdout.write(f"Next daily run at {target:%Y-%m-%d %H:%M} ({wait / 3600:.1f} h)")
            time.sleep(wait)
            started = datetime.now()
            result = run_daily_jobs()
            self.stdout.write(f"{started:%Y-%m-%d %H:%M} daily jobs: {result}")
