# finance/management/commands/test_reports.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Test PDF/Excel report generation'

    def handle(self, *args, **options):
        from finance.reports.excel_report import generate_excel_report
        from finance.reports.pdf_report import generate_pdf_report

        user = User.objects.first()
        if not user:
            self.stdout.write(self.style.ERROR('No users found!'))
            return

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)

        self.stdout.write('Testing Excel report generation...')
        try:
            excel_buffer = generate_excel_report(user, start_date, end_date)
            self.stdout.write(self.style.SUCCESS('✅ Excel report generated successfully!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Excel error: {e}'))

        self.stdout.write('Testing PDF report generation...')
        try:
            pdf_buffer = generate_pdf_report(user, start_date, end_date)
            self.stdout.write(self.style.SUCCESS('✅ PDF report generated successfully!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ PDF error: {e}'))