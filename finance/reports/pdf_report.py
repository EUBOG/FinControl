# finance/reports/pdf_report.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.units import inch
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Sum
import io


def generate_pdf_report(user, start_date, end_date, categories=None):
    """Генерация PDF отчета с графиками"""
    from finance.models import Transaction

    # Регистрируем шрифт
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
    main_font = 'DejaVuSans'

    # Получаем транзакции
    transactions = Transaction.objects.filter(
        user=user,
        date__gte=start_date,
        date__lte=end_date
    ).order_by('date')

    if categories:
        transactions = transactions.filter(category__name__in=categories)

    # Создание PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18,
        title=f"Финансовый отчет {start_date} - {end_date}",
        encoding='utf-8'
    )
    elements = []

    styles = getSampleStyleSheet()
    styles['Normal'].fontName = main_font
    styles['Heading1'].fontName = main_font
    styles['Heading2'].fontName = main_font
    styles['Heading3'].fontName = main_font

    # === ЗАГОЛОВОК ===
    title = Paragraph(f"Финансовый отчет", styles['Heading1'])
    elements.append(title)

    period = Paragraph(f"Период: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}",
                       styles['Heading2'])
    elements.append(period)

    elements.append(Spacer(1, 0.25 * inch))

    # === СВОДНАЯ ИНФОРМАЦИЯ ===
    total_income_result = transactions.filter(type='income').aggregate(Sum('amount'))['amount__sum']
    total_income = float(total_income_result) if total_income_result else 0.0

    total_expense_result = transactions.filter(type='expense').aggregate(Sum('amount'))['amount__sum']
    total_expense = float(total_expense_result) if total_expense_result else 0.0

    balance = total_income - total_expense

    summary_text = f"""
    <b>Сводная информация:</b><br/>
    • Общее количество операций: <b>{len(transactions)}</b><br/>
    • Доходы: <b>{total_income:.2f} руб.</b><br/>
    • Расходы: <b>{total_expense:.2f} руб.</b><br/>
    • Баланс: <b>{balance:.2f} руб.</b><br/>
    • Доходов: {transactions.filter(type='income').count()}<br/>
    • Расходов: {transactions.filter(type='expense').count()}<br/>
    """
    summary = Paragraph(summary_text, styles['Normal'])
    elements.append(summary)

    elements.append(Spacer(1, 0.3 * inch))

    # === АНАЛИЗ ПО КАТЕГОРИЯМ ===
    if transactions.filter(type='expense').exists():
        expense_categories = {}
        for transaction in transactions.filter(type='expense'):
            cat_name = transaction.category.name
            if cat_name not in expense_categories:
                expense_categories[cat_name] = 0.0
            expense_categories[cat_name] += float(transaction.amount)

        sorted_categories = sorted(expense_categories.items(), key=lambda x: x[1], reverse=True)

        cat_title = Paragraph("<b>Расходы по категориям:</b>", styles['Heading3'])
        elements.append(cat_title)

        cat_data = [['Категория', 'Сумма', 'Доля']]
        for category, amount in sorted_categories:
            percentage = (amount / total_expense * 100) if total_expense > 0 else 0
            cat_data.append([category, f"{amount:.2f} руб.", f"{percentage:.1f}%"])

        cat_table = Table(cat_data)
        cat_table.setStyle(TableStyle([
            # Заголовок таблицы
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), main_font),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

            # Данные таблицы - ВАЖНО: явно задаем цвета
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F2F2F2')),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),  # Черный текст для данных
            ('FONTNAME', (0, 1), (-1, -1), main_font),
            ('FONTSIZE', (0, 1), (-1, -1), 9),

            # Общие стили
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))

        elements.append(cat_table)
        elements.append(Spacer(1, 0.3 * inch))

    # === ДЕТАЛЬНЫЕ ДАННЫЕ ===
    if transactions.exists():
        details_title = Paragraph("<b>Детальные данные:</b>", styles['Heading3'])
        elements.append(details_title)

        display_transactions = transactions[:50]

        data = [['Дата', 'Тип', 'Категория', 'Сумма', 'Описание']]
        for transaction in display_transactions:
            data.append([
                transaction.date.strftime('%d.%m.%Y'),
                'Доход' if transaction.type == 'income' else 'Расход',
                transaction.category.name,
                f"{float(transaction.amount):.2f}",
                transaction.description or '-'
            ])

        if len(transactions) > 50:
            data.append(['...', f"и еще {len(transactions) - 50} операций", '', '', ''])

        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            # Заголовок таблицы
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), main_font),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),

            # Данные таблицы - ВАЖНО: явно задаем цвета
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),  # Черный текст для данных
            ('FONTNAME', (0, 1), (-1, -1), main_font),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F8F8')]),

            # Общие стили
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))

        elements.append(table)
    else:
        no_data = Paragraph("<b>Нет данных для отображения</b>", styles['Normal'])
        elements.append(no_data)

    # === ФУТЕР ===
    elements.append(Spacer(1, 0.2 * inch))
    footer = Paragraph(f"<i>Отчет сгенерирован: {timezone.now().strftime('%d.%m.%Y %H:%M')}</i>", styles['Normal'])
    elements.append(footer)

    # Генерация PDF
    doc.build(elements)
    buffer.seek(0)

    return buffer