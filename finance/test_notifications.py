# finance/test_notifications.py
import os
import django
import asyncio


def setup_django():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FinControl.settings')
    django.setup()


def test_notifications():
    setup_django()

    from finance.cron import send_daily_notifications, send_weekly_reports, send_monthly_reports

    print("Testing daily notifications...")
    send_daily_notifications()

    print("Testing weekly reports...")
    send_weekly_reports()

    print("Testing monthly reports...")
    send_monthly_reports()

    print("All tests completed!")


if __name__ == "__main__":
    test_notifications()