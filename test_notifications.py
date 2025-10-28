# test_notifications.py - СОЗДАЙТЕ в корне проекта (рядом с manage.py)
import os
import sys
import django

# Добавляем корневую папку проекта в Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def setup_django():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FinControl.settings')
    django.setup()


def test_notifications():
    setup_django()

    print("✅ Django настроен успешно!")

    # Теперь импортируем после настройки Django
    from finance.cron import send_daily_notifications, send_weekly_reports, send_monthly_reports

    print("Testing daily notifications...")
    send_daily_notifications()

    print("Testing weekly reports...")
    send_weekly_reports()

    print("Testing monthly reports...")
    send_monthly_reports()

    print("🎉 All tests completed!")


if __name__ == "__main__":
    test_notifications()