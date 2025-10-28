# finance/views.py
from django.shortcuts import render, redirect, get_object_or_404 # Добавим get_object_or_404
from django.views.generic import CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Q # Импортируем Q для фильтрации
from django.http import HttpResponseRedirect
from .models import Transaction, Category, SavedReport # Импортируем SavedReport
from .forms import TransactionForm
import datetime
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from .models import SavedReport, Transaction
from .reports.excel_report import generate_excel_report
from .reports.pdf_report import generate_pdf_report
import json
from datetime import datetime, timedelta

def index(request):
    """
    Отображает главную страницу.
    """
    # Если нужно передать какие-то данные в шаблон, можно их получить здесь.
    # Например, количество зарегистрированных пользователей (если нужно показать).
    # context = {'some_data': ...}
    # return render(request, 'core/index.html', context)
    return render(request, 'finance/index.html')

class TransactionCreateView(LoginRequiredMixin, CreateView):

    """
    Представление для создания новой финансовой операции.
    Использует TransactionForm.
    Требует аутентификацию пользователя.
    """
    model = Transaction
    form_class = TransactionForm
    template_name = 'finance/transaction_form.html'
    success_url = reverse_lazy('finance:transaction_create')

    def dispatch(self, request, *args, **kwargs):
        print(f"DEBUG: TransactionCreateView.dispatch called for user: {request.user}, method: {request.method}")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """
        Метод вызывается, если форма валидна.
        Здесь мы можем добавить дополнительную логику перед сохранением.
        """
        # Привязываем текущего аутентифицированного пользователя к транзакции
        form.instance.user = self.request.user
        print(f"DEBUG: form.instance.user = {form.instance.user}")
        print(f"DEBUG: form.instance.amount = {form.instance.amount}")
        print(f"DEBUG: form.instance.date = {form.instance.date}")
        print(f"DEBUG: form.instance.type = {form.instance.type}")
        print(f"DEBUG: form.instance.category = {form.instance.category}")
        print(f"DEBUG: form.instance.description = {form.instance.description}")

        # Проверка даты в будущем и логика подтверждения
        future_date_flag = False
        if form.instance.date and form.instance.date > datetime.date.today():
            messages.warning(self.request, f"Вы указали дату в будущем ({form.instance.date}). Транзакция будет сохранена.")

        print("DEBUG: Before calling super().form_valid(form)")
        result = super().form_valid(form) # <-- Вызов сохранения
        print(f"DEBUG: super().form_valid(form) returned: {result}")
        print(f"DEBUG: Transaction ID after save: {form.instance.id}") # <-- Это должно вывести ID
        return result # <-- Вернём результат
        # return super().form_valid(form)

    def get_queryset(self):
        # ... (ваш существующий код get_queryset с фильтрацией) ...
        # (скопируйте сюда ваш текущий код get_queryset, включая логику фильтрации)
        print("DEBUG: get_queryset - ABSOLUTE START")
        print("DEBUG: About to get request.user")
        user = self.request.user
        print(f"DEBUG: Got request.user = {user}")
        print(f"DEBUG: Got request.user.id = {user.id}")

        queryset = Transaction.objects.filter(user=user).order_by('-date')
        print("DEBUG: Called filter, about to count")
        count = queryset.count()
        print(f"DEBUG: get_queryset found {count} transactions for user {user}")

        # Применяем фильтры, если они есть в GET-запросе
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        category_id = self.request.GET.get('category')

        if start_date:
            try:
                start_date_obj = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(date__gte=start_date_obj)
            except ValueError:
                pass

        if end_date:
            try:
                end_date_obj = datetime.datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(date__lte=end_date_obj)
            except ValueError:
                pass

        if category_id:
            try:
                queryset = queryset.filter(category_id=category_id)
            except (ValueError, TypeError):
                pass

        print("DEBUG: get_queryset - END")
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Явно получаем список транзакций через наш get_queryset
        transaction_list = self.get_queryset()
        context['object_list'] = transaction_list # Помещаем его в контекст под именем object_list
        print(f"DEBUG: get_context_data added {transaction_list.count()} transactions to object_list") # <-- Отладка

        # --- НОВОЕ: Добавляем сохранённые отчёты пользователя в контекст ---
        user_saved_reports = SavedReport.objects.filter(user=self.request.user)
        context['saved_reports'] = user_saved_reports
        # ---

        return context

    # --- НОВЫЕ МЕТОДЫ: Обработка сохранения и загрузки отчётов ---
    def post(self, request, *args, **kwargs):
        """
        Обрабатывает POST-запросы.
        Используется для сохранения отчёта.
        """
        # Проверяем, является ли запрос попыткой сохранить отчёт
        if 'save_report_name' in request.POST:
            report_name = request.POST.get('save_report_name').strip()
            if report_name:
                try:
                    # Получаем текущие параметры фильтрации из GET или POST (в данном случае из GET, как на странице)
                    # Мы не можем напрямую получить их из self.request.GET здесь, так как они не относятся к этому POST-запросу
                    # ВАЖНО: Нам нужно получить параметры, которые были *до* этого POST-запроса.
                    # Это немного tricky. В реальном приложении часто делают отдельный POST-запрос для сохранения.
                    # Но для MVP, предположим, что пользователь сначала применяет фильтры (GET-запрос),
                    # а затем нажимает кнопку "Сохранить", которая отправляет POST с именем.
                    # В этом случае, мы можем передать параметры фильтрации через hidden поля в форме или через JS.
                    # ПОПРОБУЕМ ПЕРЕДАТЬ ПАРАМЕТРЫ ИЗ URL, КОТОРЫЙ БЫЛ ДО НАЖАТИЯ "СОХРАНИТЬ".
                    # Это означает, что кнопка "Сохранить" должна отправлять *текущий* URL (с параметрами фильтрации) как часть данных.
                    # Это можно сделать с помощью JavaScript, отправляя параметры как hidden поля или через AJAX.
                    # ПОКА ЧТО, ПОПРОБУЕМ ПОЛУЧИТЬ ИХ ИЗ REFERER. Это менее надёжно, но может сработать для MVP.
                    # ЛУЧШЕ: Сделать отдельную кнопку/ссылку "Сохранить отчёт", которая передаёт параметры явно.
                    # НАПРИМЕР, ссылка может быть вида: <a href="?save_report=1&name=MyReport&...filters...">Сохранить</a>
                    # Тогда это будет GET-запрос. Или форма с POST.
                    # ПОЙДЁМ ПО ПРОСТОМУ: Сделаем отдельный GET-маршрут для сохранения.

                    # АЛЬТЕРНАТИВНЫЙ ПОДХОД (реализуем его): Добавим кнопку "Сохранить" как форму, которая отправляет GET-запрос
                    # с текущими параметрами фильтрации + новым параметром 'save_report_name'.
                    # Тогда нам нужно обработать GET-запрос с этим параметром.
                    # НО: Это будет GET-запрос, изменяющий данные (плохо по стандартам HTTP).
                    # ЛУЧШЕ: Использовать POST для сохранения.
                    # ИЗМЕНИМ ПОДХОД: Сделаем кнопку "Сохранить" как форму с POST.
                    # Эта форма будет отправлять 'save_report_name' и *текущие* параметры фильтрации.
                    # Мы можем передать их как hidden поля в той же форме фильтрации или отдельно.
                    # ВЫНЕСЕМ ЛОГИКУ В ОТДЕЛЬНОЕ ПРЕДСТАВЛЕНИЕ ИЛИ МЕТОД.
                    # ПОКА ЧТО, ПОПРОБУЕМ ВНУТРИ ЭТОГО КЛАССА.

                    # Получим параметры фильтрации из GET-запроса, который привёл к этой странице (referer)
                    # Это хрупкий способ, но для MVP может сработать.
                    # Более надёжно: передавать параметры через hidden поля формы или AJAX.
                    # Для простоты, будем считать, что пользователь сначала *применил* фильтры (GET-запрос к /transactions/ с параметрами),
                    # и *только потом* нажал кнопку "Сохранить" (POST-запрос).
                    # В этом случае, `self.request.GET` в методе `get` содержит фильтры.
                    # Но в методе `post` `self.request.GET` - это GET-параметры текущего запроса (обычно пустые для POST).
                    # Нам нужно передать параметры фильтрации в POST-запросе.
                    # Добавим hidden поля в форму фильтрации в шаблоне.

                    # В шаблоне transaction_form.html добавим hidden поля в форму фильтрации:
                    # <input type="hidden" name="current_start_date" value="{{ request.GET.start_date }}">
                    # <input type="hidden" name="current_end_date" value="{{ request.GET.end_date }}">
                    # <input type="hidden" name="current_category" value="{{ request.GET.category }}">

                    # Теперь получим параметры из POST
                    current_start_date = request.POST.get('current_start_date')
                    current_end_date = request.POST.get('current_end_date')
                    current_category = request.POST.get('current_category')

                    # Формируем словарь фильтров
                    filters_to_save = {}
                    if current_start_date:
                        filters_to_save['start_date'] = current_start_date
                    if current_end_date:
                        filters_to_save['end_date'] = current_end_date
                    if current_category:
                        filters_to_save['category'] = current_category

                    # Пытаемся создать или обновить отчёт
                    saved_report, created = SavedReport.objects.get_or_create(
                        user=request.user,
                        name=report_name,
                        defaults={'filters': filters_to_save}
                    )
                    if not created:
                        # Если отчёт с таким именем уже существует, обновляем его
                        saved_report.filters = filters_to_save
                        saved_report.save()

                    messages.success(request, f"Отчёт '{report_name}' успешно {'сохранён' if created else 'обновлён'}!")
                except Exception as e:
                    messages.error(request, f"Ошибка при сохранении отчёта: {e}")

            else:
                messages.error(request, "Название отчёта не может быть пустым.")

            # Возвращаемся на ту же страницу, чтобы увидеть обновлённый список сохранённых отчётов и сообщение
            # Сохраняем текущие параметры фильтрации, чтобы они не сбросились
            current_params = request.GET.urlencode()
            redirect_url = reverse_lazy('finance:transaction_create')
            if current_params:
                redirect_url += f'?{current_params}'
            return HttpResponseRedirect(redirect_url)

        # Если это не запрос на сохранение, обрабатываем как обычно (например, для формы транзакции)
        # Вызов super().post(...) не подходит напрямую, так как это CreateView.
        # Для формы добавления транзакции у нас есть form_valid и form_invalid.
        # POST-запросы, не связанные с формой транзакции (например, сохранение отчёта), обрабатываются выше.
        # Если форма транзакции отправляется, Django сам вызовет form_valid.
        # Этот метод `post` перехватывает все POST-запросы к этому URL.
        # Если ни одно из условий выше не сработало, возможно, это была форма транзакции.
        # В этом случае, просто вызываем стандартную логику CreateView.
        return super().post(request, *args, **kwargs)

# --- НОВОЕ ПРЕДСТАВЛЕНИЕ: Загрузка отчёта ---
from django.http import JsonResponse # Импортируем для возврата JSON (может понадобиться для AJAX)

def load_saved_report(request, report_id):
    """
    Возвращает параметры фильтрации сохранённого отчёта в формате JSON.
    Используется для загрузки параметров через AJAX.
    """
    if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest': # Проверка на AJAX
        report = get_object_or_404(SavedReport, id=report_id, user=request.user)
        return JsonResponse(report.get_filters())
    else:
        # Возвращаем ошибку или редирект, если не AJAX или не GET
        return HttpResponseRedirect(reverse_lazy('finance:transaction_create'))

# Не забудьте добавить маршрут для load_saved_report в urls.py

@login_required
def report_builder(request):
    """Простая страница построителя отчетов"""
    return render(request, 'finance/report_builder.html')


@login_required
def create_report(request):
    """Создание отчета"""
    if request.method == 'POST':
        name = request.POST.get('name', 'Отчет')
        report_format = request.POST.get('format', 'pdf')
        period_type = request.POST.get('period_type', 'month')

        # Определение дат
        today = timezone.now().date()
        if period_type == 'day':
            start_date = today
            end_date = today
        elif period_type == 'week':
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif period_type == 'month':
            start_date = today.replace(day=1)
            end_date = today
        elif period_type == 'year':
            start_date = today.replace(month=1, day=1)
            end_date = today
        elif period_type == 'custom':
            start_date_str = request.POST.get('start_date')
            end_date_str = request.POST.get('end_date')
            if start_date_str:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            else:
                start_date = today
            if end_date_str:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            else:
                end_date = today
        else:
            start_date = today
            end_date = today

        try:
            if report_format == 'excel':
                from .reports.excel_report import generate_excel_report
                buffer = generate_excel_report(request.user, start_date, end_date)
                filename = f'report_{start_date}_{end_date}.xlsx'
                content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            else:  # pdf
                from .reports.pdf_report import generate_pdf_report
                buffer = generate_pdf_report(request.user, start_date, end_date)
                filename = f'report_{start_date}_{end_date}.pdf'
                content_type = 'application/pdf'

            response = HttpResponse(buffer.getvalue(), content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        except Exception as e:
            return HttpResponse(f"Ошибка генерации отчета: {str(e)}", status=500)

    return HttpResponse("Неверный запрос", status=400)


@login_required
def quick_reports(request):
    """Быстрые отчеты"""
    report_type = request.GET.get('type', 'month')
    format_type = request.GET.get('format', 'pdf')

    today = timezone.now().date()

    if report_type == 'day':
        start_date = today
        end_date = today
    elif report_type == 'week':
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    elif report_type == 'month':
        start_date = today.replace(day=1)
        end_date = today
    elif report_type == 'year':
        start_date = today.replace(month=1, day=1)
        end_date = today
    else:
        return HttpResponse("Неверный тип отчета", status=400)

    try:
        if format_type == 'excel':
            from .reports.excel_report import generate_excel_report
            buffer = generate_excel_report(request.user, start_date, end_date)
            filename = f'{report_type}_report.xlsx'
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:  # pdf
            from .reports.pdf_report import generate_pdf_report
            buffer = generate_pdf_report(request.user, start_date, end_date)
            filename = f'{report_type}_report.pdf'
            content_type = 'application/pdf'

        response = HttpResponse(buffer.getvalue(), content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        return HttpResponse(f"Ошибка генерации отчета: {str(e)}", status=500)