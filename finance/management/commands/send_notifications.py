# finance/management/commands/send_notifications.py
import os
import django
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Send financial notifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            choices=['daily', 'weekly', 'monthly'],
            help='Type of notification to send'
        )

    def handle(self, *args, **options):
        # Настройка Django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FinControl.settings')
        django.setup()

        from finance.cron import send_daily_notifications, send_weekly_reports, send_monthly_reports

        notification_type = options['type']

        if notification_type == 'daily':
            self.stdout.write('Sending daily notifications...')
            send_daily_notifications()
        elif notification_type == 'weekly':
            self.stdout.write('Sending weekly reports...')
            send_weekly_reports()
        elif notification_type == 'monthly':
            self.stdout.write('Sending monthly reports...')
            send_monthly_reports()
        else:
            self.stdout.write('Please specify --type [daily|weekly|monthly]')