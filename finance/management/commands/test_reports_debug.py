# finance/management/commands/test_reports_debug.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Debug test for PDF/Excel report generation'

    def handle(self, *args, **options):
        try:
            from finance.reports.excel_report import generate_excel_report
            from finance.reports.pdf_report import generate_pdf_report
            from finance.models import Transaction

            user = User.objects.first()
            if not user:
                self.stdout.write(self.style.ERROR('❌ No users found! Create a user first.'))
                return

            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=7)

            self.stdout.write(f'Testing reports for user: {user.username}')
            self.stdout.write(f'Period: {start_date} to {end_date}')

            # Проверим данные
            transactions = Transaction.objects.filter(
                user=user,
                date__gte=start_date,
                date__lte=end_date
            )
            self.stdout.write(f'Found {transactions.count()} transactions')

            if transactions.exists():
                sample = transactions.first()
                self.stdout.write(f'Sample transaction: {sample.amount} ({type(sample.amount)})')

            # Тест Excel
            self.stdout.write('\n=== Testing Excel report ===')
            try:
                excel_buffer = generate_excel_report(user, start_date, end_date)
                self.stdout.write(self.style.SUCCESS('✅ Excel report generated successfully!'))

                # Сохраним файл для проверки
                with open('test_excel_report.xlsx', 'wb') as f:
                    f.write(excel_buffer.getvalue())
                self.stdout.write('💾 Excel report saved as: test_excel_report.xlsx')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Excel error: {e}'))
                import traceback
                self.stdout.write(traceback.format_exc())

            # Тест PDF
            self.stdout.write('\n=== Testing PDF report ===')
            try:
                pdf_buffer = generate_pdf_report(user, start_date, end_date)
                self.stdout.write(self.style.SUCCESS('✅ PDF report generated successfully!'))

                # Сохраним файл для проверки
                with open('test_pdf_report.pdf', 'wb') as f:
                    f.write(pdf_buffer.getvalue())
                self.stdout.write('💾 PDF report saved as: test_pdf_report.pdf')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ PDF error: {e}'))
                import traceback
                self.stdout.write(traceback.format_exc())

        except ImportError as e:
            self.stdout.write(self.style.ERROR(f'❌ Import error: {e}'))
            import traceback
            self.stdout.write(traceback.format_exc())