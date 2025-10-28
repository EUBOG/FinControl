# finance/management/commands/test_notifs.py
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Test financial notifications'

    def handle(self, *args, **options):
        from finance.cron import send_daily_notifications, send_weekly_reports, send_monthly_reports

        self.stdout.write('Testing daily notifications...')
        send_daily_notifications()

        self.stdout.write('Testing weekly reports...')
        send_weekly_reports()

        self.stdout.write('Testing monthly reports...')
        send_monthly_reports()

        self.stdout.write(self.style.SUCCESS('All tests completed!'))