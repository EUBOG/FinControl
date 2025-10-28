# finance/management/commands/test_reports_simple.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Simple test for PDF/Excel report generation'

    def handle(self, *args, **options):
        # Простой тест без сложных импортов
        try:
            from finance.reports.excel_report import generate_excel_report
            from finance.reports.pdf_report import generate_pdf_report

            user = User.objects.first()
            if not user:
                self.stdout.write(self.style.ERROR('❌ No users found! Create a user first.'))
                return

            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=7)  # За последние 7 дней

            self.stdout.write(f'Testing reports for user: {user.username}')
            self.stdout.write(f'Period: {start_date} to {end_date}')

            # Тест Excel
            self.stdout.write('Testing Excel report...')
            try:
                excel_buffer = generate_excel_report(user, start_date, end_date)
                self.stdout.write(self.style.SUCCESS('✅ Excel report generated!'))

                # Сохраним файл для проверки
                with open('test_excel_report.xlsx', 'wb') as f:
                    f.write(excel_buffer.getvalue())
                self.stdout.write('💾 Excel report saved as: test_excel_report.xlsx')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Excel error: {e}'))

            # Тест PDF
            self.stdout.write('Testing PDF report...')
            try:
                pdf_buffer = generate_pdf_report(user, start_date, end_date)
                self.stdout.write(self.style.SUCCESS('✅ PDF report generated!'))

                # Сохраним файл для проверки
                with open('test_pdf_report.pdf', 'wb') as f:
                    f.write(pdf_buffer.getvalue())
                self.stdout.write('💾 PDF report saved as: test_pdf_report.pdf')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ PDF error: {e}'))

        except ImportError as e:
            self.stdout.write(self.style.ERROR(f'❌ Import error: {e}'))
            self.stdout.write('Make sure all required packages are installed:')
            self.stdout.write('pip install openpyxl reportlab')