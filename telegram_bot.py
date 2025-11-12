# telegram_bot.py
import os
import django

# путь к настройкам Django-проекта
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FinControl.settings')

# Инициализация Django
django.setup()
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime, timedelta # Для работы с датами
import re
from asgiref.sync import sync_to_async
from decouple import config
import matplotlib.pyplot as plt # <-- Добавляем импорт matplotlib
import io # <-- Добавляем импорт io для работы с байтами
import tempfile # <-- Добавляем импорт tempfile для создания временных файлов

# Теперь можно импортировать модели Django
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models import Sum, Q # Для агрегации (суммы) и фильтрации
from finance.models import Transaction, Category, UserConsent

# Получаем токен бота из переменной окружения (например, из файла .env)
BOT_TOKEN = config('BOT_TOKEN')

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Определение состояний для месяца, недели и дня
class MonthInput(StatesGroup):
    waiting_for_month = State()

class DayInput(StatesGroup):
    waiting_for_day = State()

class WeekInput(StatesGroup):
    waiting_for_week_start = State()

# Определим состояния для ввода транзакции через FSM (Finite State Machine)
class TransactionStates(StatesGroup):
    waiting_for_type = State()
    waiting_for_amount = State()
    waiting_for_date = State()
    waiting_for_category = State()
    waiting_for_description = State()

# Добавляем вспомогательные функции парсинга дат
def parse_day(date_str: str):
    """Парсит строку вида '21.10.2025' → date(2025, 10, 21)"""
    return datetime.strptime(date_str, '%d.%m.%Y').date()

def parse_month(month_str: str):
    """Парсит строку вида '10.2025' → (start_date, end_date) месяца"""
    parts = month_str.split('.')
    if len(parts) != 2:
        raise ValueError("Неверный формат месяца")
    month, year = int(parts[0]), int(parts[1])
    if not (1 <= month <= 12):
        raise ValueError("Месяц должен быть от 01 до 12")
    start = datetime(year, month, 1).date()
    # Последний день месяца
    if month == 12:
        end = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        end = datetime(year, month + 1, 1).date() - timedelta(days=1)
    return start, end

def parse_year(year_str: str):
    """Парсит '2025' → (start_date, end_date) года"""
    year = int(year_str)
    start = datetime(year, 1, 1).date()
    end = datetime(year, 12, 31).date()
    return start, end

# Добавляем функцию годового графика
def generate_yearly_chart(transactions_list):
    """
    Генерирует график доходов/расходов по месяцам за год.
    transactions_list: Список транзакций за год.
    Возвращает байтовый объект с изображением.
    """
    from collections import defaultdict

    income_by_month = defaultdict(float)
    expense_by_month = defaultdict(float)

    for t in transactions_list:
        month_key = t.date.strftime('%m.%Y')  # Например: '10.2025'
        if t.type == 'income':
            income_by_month[month_key] += float(t.amount)
        elif t.type == 'expense':
            expense_by_month[month_key] += float(t.amount)

    # Сортируем месяцы по дате
    all_months = sorted(set(income_by_month.keys()) | set(expense_by_month.keys()),
                        key=lambda x: datetime.strptime(x, '%m.%Y'))

    income_values = [income_by_month[m] for m in all_months]
    expense_values = [expense_by_month[m] for m in all_months]

    plt.figure(figsize=(12, 6))
    plt.plot(all_months, income_values, label='Доходы', marker='o')
    plt.plot(all_months, expense_values, label='Расходы', marker='s')
    plt.title('Доходы и расходы по месяцам за год')
    plt.xlabel('Месяц')
    plt.ylabel('Сумма')
    plt.legend()
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()

    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150)
    img_buffer.seek(0)
    plt.close()
    return img_buffer

# Декоратор для проверки согласия. Будем его вызывать в начале каждого обработчика, требующего доступ.
async def check_consent_or_block(message_or_callback, state: FSMContext = None):
    # Получаем пользователя
    if isinstance(message_or_callback, types.Message):
        user_id = message_or_callback.from_user.id
        username = message_or_callback.from_user.username
    else:
        user_id = message_or_callback.from_user.id
        username = message_or_callback.from_user.username

    user = await get_or_create_django_user(user_id, username)
    has_consent = await is_consent_valid(user)

    if not has_consent:
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(
                "🔒 Для доступа к FinControl необходимо дать согласие на обработку персональных данных.\n"
                "Нажмите кнопку «Дать согласие...»."
            )
        else:
            await message_or_callback.answer(
                "Требуется согласие на обработку персональных данных.",
                show_alert=True
            )
        if state:
            await state.clear()
        return False
    return True

# --- Вспомогательные функции для работы с пользователями и транзакциями ---
# Оборачиваем синхронные функции ORM в sync_to_async

@sync_to_async
def get_or_create_consent(user):
    consent, created = UserConsent.objects.get_or_create(user=user)
    return consent

@sync_to_async
def grant_consent(user):
    from django.utils import timezone
    consent = UserConsent.objects.get(user=user)
    consent.given_at = timezone.now()
    consent.revoked_at = None
    consent.save()

@sync_to_async
def revoke_consent(user):
    from django.utils import timezone
    print(f"[DEBUG] revoke_consent called for user: {user.username}")
    try:
        consent = UserConsent.objects.get(user=user)
        print(f"[DEBUG] Found consent: given_at={consent.given_at}, revoked_at={consent.revoked_at}")
        if consent.given_at is not None and consent.revoked_at is None:
            consent.revoked_at = timezone.now()
            consent.save()
            print(f"[DEBUG] Consent revoked at: {consent.revoked_at}")
            return True
        else:
            print("[DEBUG] No active consent to revoke")
            return False
    except UserConsent.DoesNotExist:
        print("[DEBUG] UserConsent does not exist")
        return False
    except Exception as e:
        print(f"[ERROR] Exception in revoke_consent: {e}")
        return False

@sync_to_async
def is_consent_valid(user):
    try:
        consent = UserConsent.objects.get(user=user)
        return consent.is_valid
    except UserConsent.DoesNotExist:
        return False

@sync_to_async
def get_expenses_for_user_and_period(user, start_date, end_date):
    #Получить расходы (только type='expense') для пользователя в диапазоне дат.
    return Transaction.objects.filter(
        user=user,
        type='expense', # Только расходы
        date__gte=start_date,
        date__lte=end_date
    )

@sync_to_async
def get_or_create_django_user(telegram_id: int, username: str = None):
    """
    Находит или создает Django User, связанный с Telegram ID.
    Для MVP можно использовать username, если он есть.
    Если username нет, можно создать уникальный на основе telegram_id.
    """
    # Попробуем найти пользователя по username (если он есть и уникален)
    if username:
        try:
            user = User.objects.get(username=username)
            # TODO: Связать telegram_id с этим пользователем, если связи нет
            # Для простоты MVP, предположим, что username уникален и его хватает.
            # В реальном проекте создайте промежуточную модель Profile или UserTelegramID.
            return user
        except User.DoesNotExist:
            # Пользователь с таким username не найден, создаём нового
            # Используем username, если он есть, иначе генерируем
            user_username = username or f"tg_user_{telegram_id}"
            user = User.objects.create_user(username=user_username)
            # TODO: Сохранить telegram_id в Profile или UserTelegramID
            return user
    else:
        # Если username нет, ищем по telegram_id или создаём с уникальным именем
        # В MVP без промежуточной модели сложно. Пока используем только username или уникальное имя.
        # Попробуем найти по Telegram ID в профиле (нужно будет создать модель Profile).
        # Для MVP: создадим уникальное имя.
        user_username = f"tg_user_{telegram_id}"
        try:
            user = User.objects.get(username=user_username)
            return user
        except User.DoesNotExist:
            user = User.objects.create_user(username=user_username)
            return user

@sync_to_async
def get_transactions_for_user_and_date(user, date):
    """Получить транзакции для пользователя за конкретную дату."""
    return Transaction.objects.filter(user=user, date=date)

@sync_to_async
def get_transactions_for_user_and_date_range(user, start_date, end_date):
    """Получить транзакции для пользователя в диапазоне дат."""
    return Transaction.objects.filter(
        user=user,
        date__gte=start_date,
        date__lte=end_date
    )

@sync_to_async
def get_transactions_for_user_and_week(user, start_of_week, end_of_week):
    """Получить транзакции для пользователя за неделю."""
    return Transaction.objects.filter(
        user=user,
        date__gte=start_of_week,
        date__lte=end_of_week
    )

@sync_to_async
def get_transactions_for_user_and_category(user, category):
    """Получить транзакции для пользователя по категории."""
    return Transaction.objects.filter(user=user, category=category)

@sync_to_async
def get_category_by_name(name):
    """Получить категорию по имени."""
    return Category.objects.get(name=name)

# Функция create_transaction
@sync_to_async
def create_transaction(user, amount, date, type, category_id, description):
    category = Category.objects.get(id=category_id)
    return Transaction.objects.create(
        user=user,
        amount=amount,
        date=date,
        type=type,
        category=category,
        description=description
    )

# --- Функции генерации графиков ---
# Эти функции будут синхронными, но вызываться из асинхронных обработчиков через sync_to_async



def generate_weekly_chart(transactions_list):
    """
    Генерирует график доходов/расходов за неделю.
    transactions_list: Список объектов Transaction за неделю.
    Возвращает путь к файлу изображения или байтовый объект.
    """
    # Подготовка данных
    # Группируем по дате и типу
    from collections import defaultdict
    income_by_day = defaultdict(float)
    expense_by_day = defaultdict(float)

    # Теперь итерируемся по списку, а не по QuerySet
    for t in transactions_list:
        date_str = t.date.strftime('%d.%m') # Форматируем дату для подписи
        if t.type == 'income':
            income_by_day[date_str] += float(t.amount)
        elif t.type == 'expense':
            expense_by_day[date_str] += float(t.amount)

    # Сортируем дни по дате
    all_dates = sorted(set(income_by_day.keys()) | set(expense_by_day.keys()))

    # Подготавливаем списки для графика
    income_values = [income_by_day[date] for date in all_dates]
    expense_values = [expense_by_day[date] for date in all_dates]

    # Создание графика
    plt.figure(figsize=(10, 6))
    plt.plot(all_dates, income_values, label='Доходы', marker='o')
    plt.plot(all_dates, expense_values, label='Расходы', marker='s')
    plt.title('Доходы и расходы за неделю')
    plt.xlabel('Дата')
    plt.ylabel('Сумма')
    plt.legend()
    plt.grid(True)
    plt.xticks(rotation=45) # Поворот подписей оси X для лучшей читаемости
    plt.tight_layout() # Улучшает расположение элементов

    # Сохраняем график в байтовый объект
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150)
    img_buffer.seek(0) # Перемещаем указатель в начало буфера
    plt.close() # Закрываем фигуру, чтобы освободить память

    return img_buffer

def generate_monthly_chart(transactions_list):
    """
    Генерирует график доходов/расходов за месяц.
    transactions_list: Список объектов Transaction за месяц.
    Возвращает байтовый объект с изображением графика.
    """
    from collections import defaultdict
    from datetime import datetime

    # Подготовка данных
    # Группируем по дню месяца (1-31) и типу
    income_by_day = defaultdict(float)
    expense_by_day = defaultdict(float)

    for t in transactions_list:
        # Используем день месяца (1-31) как ключ для группировки
        day_key = t.date.strftime('%d.%m') # Форматируем как день.месяц для подписи
        if t.type == 'income':
            income_by_day[day_key] += float(t.amount)
        elif t.type == 'expense':
            expense_by_day[day_key] += float(t.amount)

    # Сортируем дни по дате (в пределах месяца)
    all_dates = sorted(set(income_by_day.keys()) | set(expense_by_day.keys()))

    # Подготавливаем списки для графика
    income_values = [income_by_day[date] for date in all_dates]
    expense_values = [expense_by_day[date] for date in all_dates]

    # Создание графика
    plt.figure(figsize=(12, 6)) # Шире для месяцев
    plt.plot(all_dates, income_values, label='Доходы', marker='o', linestyle='-', linewidth=1)
    plt.plot(all_dates, expense_values, label='Расходы', marker='s', linestyle='-', linewidth=1)
    plt.title('Доходы и расходы за месяц')
    plt.xlabel('Дата')
    plt.ylabel('Сумма')
    plt.legend()
    plt.grid(True)
    plt.xticks(rotation=45) # Поворот подписей оси X для лучшей читаемости
    plt.tight_layout() # Улучшает расположение элементов

    # Сохраняем график в байтовый буфер
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150)
    img_buffer.seek(0) # Перемещаем указатель в начало буфера
    plt.close() # Закрываем фигуру, чтобы освободить память

    return img_buffer

def generate_category_pie_chart(expenses_list):
    """
    Генерирует круговую диаграмму расходов по категориям.
    expenses_list: Список объектов Transaction (только расходы).
    Возвращает байтовый объект с изображением диаграммы.
    """
    from collections import defaultdict
    # Подготовка данных
    # Группируем расходы по категориям
    expenses_by_category = defaultdict(float)

    for t in expenses_list:
        category_name = t.category.name
        expenses_by_category[category_name] += float(t.amount)

    # Подготавливаем списки для диаграммы
    categories = list(expenses_by_category.keys())
    values = list(expenses_by_category.values())

    if not categories:
        # Если нет данных, создадим диаграмму с сообщением
        plt.figure(figsize=(8, 8))
        plt.text(0.5, 0.5, 'Нет данных для отображения', horizontalalignment='center', verticalalignment='center', fontsize=14)
        plt.axis('off') # Скрываем оси
    else:
        # Создание круговой диаграммы
        plt.figure(figsize=(8, 8))
        # autopct='%1.1f%%' добавляет проценты на сегменты
        # startangle=140 поворачивает диаграмму
        plt.pie(values, labels=categories, autopct='%1.1f%%', startangle=140)
        plt.title('Расходы по категориям')

    # Сохраняем диаграмму в байтовый буфер
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150)
    img_buffer.seek(0) # Перемещаем указатель в начало буфера
    plt.close() # Закрываем фигуру, чтобы освободить память

    return img_buffer

def generate_advice(transactions_list):
    """
    Генерирует простой совет или предупреждение на основе списка транзакций.
    transactions_list: Список объектов Transaction.
    Возвращает строку с советом или None, если совет не применим.
    """
    if not transactions_list:
        return None

    total_expense = sum(float(t.amount) for t in transactions_list if t.type == 'expense')
    total_income = sum(float(t.amount) for t in transactions_list if t.type == 'income')
    balance = total_income - total_expense

    advice_parts = []

    # Пример 1: Предупреждение о низком балансе
    if balance < 0:
        advice_parts.append("⚠️ Внимание: Ваш баланс отрицательный! Рассмотрите возможность пересмотра расходов.")

    # Пример 2: Простое сравнение доходов и расходов
    if total_expense > total_income * 0.8: # Если расходы > 80% доходов
        advice_parts.append("💡 Постарайтесь сократить расходы. Они составляют более 80% от доходов.")

    # Пример 3: Найти самую "дорогую" категорию расходов
    from collections import defaultdict
    expenses_by_category = defaultdict(float)
    for t in transactions_list:
        if t.type == 'expense':
            expenses_by_category[t.category.name] += float(t.amount)

    if expenses_by_category:
        most_expensive_category = max(expenses_by_category, key=expenses_by_category.get)
        most_expensive_amount = expenses_by_category[most_expensive_category]
        advice_parts.append(f"📊 Самая большая статья расходов за период: '{most_expensive_category}' ({most_expensive_amount:.2f}).")

    # Пример 4: Проверить, есть ли аномально высокие траты за один день
    daily_expenses = defaultdict(float)
    for t in transactions_list:
        if t.type == 'expense':
            day_key = t.date
            daily_expenses[day_key] += float(t.amount)

    if daily_expenses:
        max_daily_expense = max(daily_expenses.values())
        # Простая эвристика: если максимальная дневная трата больше средней дневной в 3 раза
        avg_daily_expense = sum(daily_expenses.values()) / len(daily_expenses) if daily_expenses else 0
        if avg_daily_expense > 0 and max_daily_expense > avg_daily_expense * 3:
            expensive_day = [day for day, amount in daily_expenses.items() if amount == max_daily_expense][0]
            advice_parts.append(f"⚠️ Аномалия: {expensive_day.strftime('%d.%m.%Y')} вы потратили {max_daily_expense:.2f}, что намного больше среднего дневного расхода ({avg_daily_expense:.2f}). Проверьте, что это была одноразовая покупка.")

    if advice_parts:
        return "\n".join(advice_parts)
    else:
        return "Всё в порядке! У вас здоровая финансовая активность."

    return None # Если не нужно возвращать "всё в порядке", просто return ""


# --- Обработчики команд ---

# Обработчик «Дать согласие...»
@dp.message(lambda msg: msg.text == "Дать согласие на обработку персональных данных")
async def send_consent_request(message: types.Message):
    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)
    consent = await get_or_create_consent(user)
    if consent.is_valid:
        await message.answer("✅ Вы уже дали согласие на обработку персональных данных.")
        return

    # Отправляем PDF
    pdf_path = os.path.join(settings.MEDIA_ROOT, 'consent', 'privacy_policy.pdf')
    if not os.path.exists(pdf_path):
        await message.answer("❌ Документ с политикой недоступен. Обратитесь к администратору.")
        return

    await message.answer_document(
        document=types.FSInputFile(pdf_path),
        caption="📄 Ознакомьтесь с Политикой обработки персональных данных."
    )

    # Вместо inline-кнопки — просто инструкция
    await message.answer(
        "Чтобы подтвердить согласие, отправьте сообщение:\n"
        "<code>Я даю согласие на обработку персональных данных</code>",
        parse_mode="HTML"
    )

# Подтверждение согласия
@dp.message(lambda msg: msg.text == "Я даю согласие на обработку персональных данных")
async def handle_consent_grant(message: types.Message):
    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)
    consent = await get_or_create_consent(user)
    if consent.is_valid:
        await message.answer("✅ Согласие уже получено!")
        return

    await grant_consent(user)
    # Возвращаем основную клавиатуру
    main_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Дать согласие на обработку персональных данных"), KeyboardButton(text="Отозвать согласия на обработку персональных данных")],
            [KeyboardButton(text="Записать финансовую транзакцию")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        "✅ Согласие получено! Теперь вы можете пользоваться FinControl.",
        reply_markup=main_keyboard
    )

# Глобальная переменная для отслеживания состояния (альтернатива FSM)
user_pending_revoke = set()

# Обработчик «Отозвать согласие...»
@dp.message(lambda msg: msg.text == "Отозвать согласие на обработку персональных данных")
async def revoke_consent_request(message: types.Message):
    # Добавляем проверку согласия
    if not await check_consent_or_block(message):
        return

    user_id = message.from_user.id
    user = await get_or_create_django_user(user_id, message.from_user.username)
    consent = await get_or_create_consent(user)

    if not consent.is_valid:
        await message.answer("ℹ️ У вас нет активного согласия на обработку персональных данных.")
        return

    # Запоминаем пользователя
    user_pending_revoke.add(user_id)

    # Временная клавиатура
    temp_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚠️ Подтвердить отзыв согласия")],
            [KeyboardButton(text="❌ Отменить отзыв")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(
        "Вы уверены, что хотите отозвать согласие на обработку персональных данных?\n"
        "⚠️ После этого вы потеряете доступ ко всем функциям FinControl.",
        reply_markup=temp_keyboard
    )

# Обработчик подтверждения отзыва согласия
@dp.message(lambda msg: msg.text == "⚠️ Подтвердить отзыв согласия")
async def handle_revoke_confirmation(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_pending_revoke:
        await message.answer("❌ Нет активного запроса на отзыв согласия.")
        return

    user_pending_revoke.discard(user_id)
    user = await get_or_create_django_user(user_id, message.from_user.username)

    # Исправляем вызов функции
    await revoke_consent(user)

    # Возвращаем основную клавиатуру
    main_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Дать согласие на обработку персональных данных")],
            [KeyboardButton(text="Отзыв согласия на обработку персональных данных")],
            [KeyboardButton(text="Записать финансовую транзакцию")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "🛑 Согласие отозвано. Доступ к FinControl заблокирован.",
        reply_markup=main_keyboard
    )

# Обработчик отмены отзыва согласия
@dp.message(lambda msg: msg.text == "❌ Отменить отзыв")
async def handle_revoke_cancellation(message: types.Message):
    user_id = message.from_user.id
    user_pending_revoke.discard(user_id)

    # Возвращаем основную клавиатуру
    main_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Дать согласие на обработку персональных данных")],
            [KeyboardButton(text="Отзыв согласия на обработку персональных данных")],
            [KeyboardButton(text="Записать финансовую транзакцию")]
        ],
        resize_keyboard=True
    )

    await message.answer("✅ Отзыв согласия отменён.", reply_markup=main_keyboard)


# Обработчик команды /start
@dp.message(Command(commands=['start']))
async def send_welcome(message: types.Message, state: FSMContext):
    # Сначала создаём пользователя и проверяем статус согласия
    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)
    has_consent = await is_consent_valid(user)

    # Reply-клавиатура: только согласие и добавление транзакции
    button_consent = KeyboardButton(text="Дать согласие на обработку персональных данных")
    button_unconsent = KeyboardButton(text="Отозвать согласие на обработку персональных данных")
    button_finances = KeyboardButton(text="Записать финансовую транзакцию")

    reply_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [button_consent, button_unconsent],
            [button_finances]
        ],
        resize_keyboard=True,
        one_time_keyboard=False  # Клавиатура остаётся видимой
    )

    # Приветственное сообщение в зависимости от статуса согласия
    if has_consent:
        welcome_text = "Привет! Я бот для FinControl. Используйте кнопки под этим сообщением для статистики. Больше инструкций по команде /help."
    else:
        welcome_text = "🔒 Для доступа к FinControl необходимо дать согласие на обработку персональных данных."

    await message.answer(welcome_text, reply_markup=reply_keyboard)

    # Inline-кнопки для статистики
    if has_consent:
        inline_builder = InlineKeyboardBuilder()
        inline_builder.button(text="📆 Стат_день", callback_data="stat:day")
        inline_builder.button(text="📅 Стат_неделя", callback_data="stat:week")
        inline_builder.button(text="📊 Стат_месяц", callback_data="stat:month")
        inline_builder.adjust(3)  # 3 кнопки в строке

        await message.answer(
            "Выберите период для анализа:",
            reply_markup=inline_builder.as_markup()  # это inline-кнопки под сообщением
        )

# Обработчик кнопки stat_month
@dp.callback_query(lambda c: c.data == "stat:month")
async def handle_stat_month(callback: CallbackQuery, state: FSMContext):
    if not await check_consent_or_block(callback, state):
        return
    await callback.answer()
    today = datetime.now().date()
    current_month = today.strftime("%m.%Y")
    first_day_this_month = today.replace(day=1)
    last_day_prev_month = first_day_this_month - timedelta(days=1)
    prev_month = last_day_prev_month.strftime("%m.%Y")

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Текущий месяц", callback_data=f"graph_month:{current_month}")
    builder.button(text="⬅️ Прошлый месяц", callback_data=f"graph_month:{prev_month}")
    builder.button(text="✏️ Ввести вручную", callback_data="graph_month:enter")
    builder.button(text="↩️ Назад", callback_data="stat:back_to_main")
    builder.adjust(1)

    await callback.message.edit_text(
        "📊 Выберите месяц для отчёта:",
        reply_markup=builder.as_markup()
    )

# Обработчик кнопки stat_day
@dp.callback_query(lambda c: c.data == "stat:day")
async def handle_stat_day(callback: CallbackQuery, state: FSMContext):
    if not await check_consent_or_block(callback, state):
        return
    await callback.answer()
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Сегодня", callback_data=f"graph_day:{today.strftime('%d.%m.%Y')}")
    builder.button(text="⬅️ Вчера", callback_data=f"graph_day:{yesterday.strftime('%d.%m.%Y')}")
    builder.button(text="✏️ Ввести дату", callback_data="graph_day:enter")
    builder.button(text="↩️ Назад", callback_data="stat:back_to_main")
    builder.adjust(1)

    await callback.message.edit_text(
        "📆 Выберите день для отчёта:",
        reply_markup=builder.as_markup()
    )

# Обработчик кнопки stat_week
@dp.callback_query(lambda c: c.data == "stat:week")
async def handle_stat_week(callback: CallbackQuery, state: FSMContext):
    if not await check_consent_or_block(callback, state):
        return
    await callback.answer()
    today = datetime.now().date()
    # Текущая неделя (с понедельника)
    start_this_week = today - timedelta(days=today.weekday())
    # Прошлая неделя
    start_last_week = start_this_week - timedelta(weeks=1)
    end_last_week = start_last_week + timedelta(days=6)

    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Текущая неделя",
        callback_data=f"graph_week_range:{start_this_week.strftime('%d.%m.%Y')}:{today.strftime('%d.%m.%Y')}"
    )
    builder.button(
        text="⬅️ Прошлая неделя",
        callback_data=f"graph_week_range:{start_last_week.strftime('%d.%m.%Y')}:{end_last_week.strftime('%d.%m.%Y')}"
    )
    builder.button(text="✏️ Ввести неделю", callback_data="graph_week:enter")
    builder.button(text="↩️ Назад", callback_data="stat:back_to_main")
    builder.adjust(1)

    await callback.message.edit_text(
        "📅 Выберите неделю для отчёта:",
        reply_markup=builder.as_markup()
    )

# Обработчик возврата в main_stat_menu
@dp.callback_query(lambda c: c.data == "stat:back_to_main")
async def back_to_main_stat_menu(callback: CallbackQuery, state: FSMContext):
    if not await check_consent_or_block(callback, state):
        return
    await callback.answer()
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="📆 Стат_день", callback_data="stat:day")
    inline_builder.button(text="📅 Стат_неделя", callback_data="stat:week")
    inline_builder.button(text="📊 Стат_месяц", callback_data="stat:month")
    inline_builder.adjust(3)

    await callback.message.edit_text(
        "Выберите период для анализа:",
        reply_markup=inline_builder.as_markup()
    )

# Обработчик нажатия на Reply-кнопку «Записать финансовую транзакцию»
@dp.message(lambda msg: msg.text == "Записать финансовую транзакцию")
async def start_transaction_flow(message: types.Message, state: FSMContext):
    if not await check_consent_or_block(message, state):
        return
    # Создаём inline-кнопки для выбора типа
    builder = InlineKeyboardBuilder()
    builder.button(text="Доход 💰", callback_data="txn_type:income")
    builder.button(text="Расход 💸", callback_data="txn_type:expense")
    builder.adjust(2)

    await message.answer("Выберите тип транзакции:", reply_markup=builder.as_markup())
    await state.set_state(TransactionStates.waiting_for_type)

# Обработчик выбора типа транзакции
@dp.callback_query(lambda c: c.data.startswith("txn_type:"), TransactionStates.waiting_for_type)
async def process_type(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    txn_type = callback.data.split(":", 1)[1]
    await state.update_data(transaction_type=txn_type)
    await callback.message.edit_text(f"Тип выбран: {'Доход' if txn_type == 'income' else 'Расход'}")

    await callback.message.answer("Введите сумму транзакции (например, 500.75):")
    await state.set_state(TransactionStates.waiting_for_amount)

# Обработчик суммы транзакции
@dp.message(TransactionStates.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")
    except ValueError:
        await message.answer("❌ Неверная сумма. Введите положительное число (например, 100 или 499.99):")
        return

    await state.update_data(amount=amount)
    await message.answer(
        "Введите дату транзакции в формате <b>ДД.ММ.ГГГГ</b> (например, <code>21.10.2025</code>):",
        parse_mode="HTML"
    )
    await state.set_state(TransactionStates.waiting_for_date)

# Обработчик даты транзакции
@dp.message(TransactionStates.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    date_str = message.text.strip()
    try:
        parsed_date = datetime.strptime(date_str, '%d.%m.%Y').date()
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты.\n"
            "Пожалуйста, используйте <b>ДД.ММ.ГГГГ</b> (например, <code>15.03.2025</code>).",
            parse_mode="HTML"
        )
        return

    await state.update_data(date=parsed_date)

    # Получаем список категорий из БД
    categories = await sync_to_async(list)(Category.objects.all())
    if not categories:
        await message.answer("❌ В системе нет категорий. Обратитесь к администратору.")
        await state.clear()
        return

    # Создаём inline-кнопки по 2 в ряд
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat.name, callback_data=f"txn_category:{cat.id}")
    builder.adjust(2)

    await message.answer("Выберите категорию:", reply_markup=builder.as_markup())
    await state.set_state(TransactionStates.waiting_for_category)

# Обработчик категории транзакции
@dp.callback_query(lambda c: c.data.startswith("txn_category:"), TransactionStates.waiting_for_category)
async def process_category(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    category_id = int(callback.data.split(":", 1)[1])
    category = await sync_to_async(Category.objects.get)(id=category_id)
    await state.update_data(category_id=category.id, category_name=category.name)
    await callback.message.edit_text(f"Категория выбрана: {category.name}")

    await callback.message.answer(
        "Введите описание транзакции (можно оставить пустым — просто отправьте точку или пропустите):"
    )
    await state.set_state(TransactionStates.waiting_for_description)

# Обработчик описания транзакции и сохранение транзакции
@dp.message(TransactionStates.waiting_for_description)
async def process_description_and_save(message: types.Message, state: FSMContext):
    description = message.text.strip()
    if description in {".", "-", "—", ""}:
        description = ""

    # Получаем все данные
    data = await state.get_data()
    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)

    try:
        # Создаём транзакцию
        transaction = await create_transaction(
            user=user,
            amount=data['amount'],
            date=data['date'],
            type=data['transaction_type'],
            category_id=data['category_id'],  # передаём ID
            description=description
        )
        await message.answer(
            f"✅ Транзакция успешно добавлена!\n\n"
            f"Тип: {'Доход' if data['transaction_type'] == 'income' else 'Расход'}\n"
            f"Сумма: {data['amount']:.2f}\n"
            f"Дата: {data['date'].strftime('%d.%m.%Y')}\n"
            f"Категория: {data['category_name']}\n"
            f"Описание: {description or '—'}"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при сохранении: {e}")

    await state.clear()

# === ДЕНЬ === Обработчик ввода дня
@dp.callback_query(lambda c: c.data == "graph_day:enter")
async def request_day_input(callback: CallbackQuery, state: FSMContext):
    if not await check_consent_or_block(callback, state):
        return
    await callback.answer()
    await callback.message.answer(
        "Введите дату в формате <b>ДД.ММ.ГГГГ</b> (например, <code>21.10.2025</code>):",
        parse_mode="HTML"
    )
    await state.set_state(DayInput.waiting_for_day)


@dp.message(DayInput.waiting_for_day)
async def process_day_input(message: types.Message, state: FSMContext):
    if not await check_consent_or_block(message, state):
        return
    date_str = message.text.strip()
    try:
        target_date = parse_day(date_str)
    except Exception:
        await message.answer(
            "❌ Неверный формат.\n"
            "Пожалуйста, введите дату как <b>ДД.ММ.ГГГГ</b> (например, <code>15.03.2025</code>).",
            parse_mode="HTML"
        )
        return

    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)
    transactions = await get_transactions_for_user_and_date(user, target_date)
    transactions_list = await sync_to_async(list)(transactions)

    if not transactions_list:
        await message.answer(f"📭 Нет транзакций за {target_date.strftime('%d.%m.%Y')}.")
    else:
        expenses = [t for t in transactions_list if t.type == 'expense']
        chart_buffer = await sync_to_async(generate_category_pie_chart)(expenses or [])
        await message.answer_photo(
            photo=types.BufferedInputFile(chart_buffer.read(), filename=f"day_{target_date}.png"),
            caption=f"📊 Отчёт за {target_date.strftime('%d.%m.%Y')}"
        )
        advice = await sync_to_async(generate_advice)(transactions_list)
        if advice:
            await message.answer(advice)

    await state.clear()


# === НЕДЕЛЯ === Обработчик ввода недели
@dp.callback_query(lambda c: c.data == "graph_week:enter")
async def request_week_input(callback: CallbackQuery, state: FSMContext):
    if not await check_consent_or_block(callback, state):
        return
    await callback.answer()
    await callback.message.answer(
        "Введите дату <b>понедельника</b> недели в формате <b>ДД.ММ.ГГГГ</b>:\n"
        "(например, <code>21.10.2025</code> — неделя с 21 по 27 октября)",
        parse_mode="HTML"
    )
    await state.set_state(WeekInput.waiting_for_week_start)


@dp.message(WeekInput.waiting_for_week_start)
async def process_week_input(message: types.Message, state: FSMContext):
    if not await check_consent_or_block(message, state):
        return
    date_str = message.text.strip()
    try:
        start_date = parse_day(date_str)
        # Проверим, что это понедельник
        if start_date.weekday() != 0:
            await message.answer(
                "⚠️ Указан не понедельник. Неделя всегда начинается с понедельника.\n"
                "Пожалуйста, введите дату понедельника (например, 21.10.2025)."
            )
            return
        end_date = start_date + timedelta(days=6)
    except Exception:
        await message.answer(
            "❌ Неверный формат.\n"
            "Введите дату понедельника как <b>ДД.ММ.ГГГГ</b>.",
            parse_mode="HTML"
        )
        return

    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)
    transactions = await get_transactions_for_user_and_date_range(user, start_date, end_date)
    transactions_list = await sync_to_async(list)(transactions)

    if not transactions_list:
        await message.answer(f"📭 Нет транзакций за неделю с {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')}.")
    else:
        chart_buffer = await sync_to_async(generate_weekly_chart)(transactions_list)
        await message.answer_photo(
            photo=types.BufferedInputFile(chart_buffer.read(), filename=f"week_{start_date}.png"),
            caption=f"📈 Отчёт за неделю\n{start_date.strftime('%d.%m.%Y')} – {end_date.strftime('%d.%m.%Y')}"
        )
        advice = await sync_to_async(generate_advice)(transactions_list)
        if advice:
            await message.answer(advice)

    await state.clear()

# Обработчик send_today_stats
@dp.message(Command(commands=['today']))
async def send_today_stats(message: types.Message, state: FSMContext):
    if not await check_consent_or_block(message, state):
        return
    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)
    today = datetime.now().date()
    transactions = await get_transactions_for_user_and_date(user, today)

    total_expense = await sync_to_async(
        lambda: transactions.filter(type='expense').aggregate(Sum('amount'))['amount__sum'] or 0
    )()
    total_income = await sync_to_async(
        lambda: transactions.filter(type='income').aggregate(Sum('amount'))['amount__sum'] or 0
    )()

    response_text = f"Статистика за сегодня ({today.strftime('%d.%m.%Y')}):\n"
    response_text += f"Доходы: {total_income:.2f}\n"
    response_text += f"Расходы: {total_expense:.2f}\n"
    response_text += f"Баланс: {total_income - total_expense:.2f}"

    await message.reply(response_text)

# Статистика за неделю
@dp.message(Command(commands=['week']))
async def send_week_stats(message: types.Message, state: FSMContext):
    if not await check_consent_or_block(message, state):
        return
    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)
    today = datetime.now().date()
    # Начало недели (понедельник)
    start_of_week = today - timedelta(days=today.weekday())
    # Конец недели (включительно сегодня)
    end_of_week = today

    transactions = await get_transactions_for_user_and_week(user, start_of_week, end_of_week)

    total_expense = await sync_to_async(
        lambda: transactions.filter(type='expense').aggregate(Sum('amount'))['amount__sum'] or 0
    )()
    total_income = await sync_to_async(
        lambda: transactions.filter(type='income').aggregate(Sum('amount'))['amount__sum'] or 0
    )()

    response_text = f"Статистика за неделю ({start_of_week.strftime('%d.%m.%Y')} - {end_of_week.strftime('%d.%m.%Y')}):\n"
    response_text += f"Доходы: {total_income:.2f}\n"
    response_text += f"Расходы: {total_expense:.2f}\n"
    response_text += f"Баланс: {total_income - total_expense:.2f}"

    await message.reply(response_text)

# Для вызова в send_week_stats
@sync_to_async
def get_transactions_for_user_and_week(user, start_of_week, end_of_week):
    """Получить транзакции для пользователя за неделю."""
    return Transaction.objects.filter(
        user=user,
        date__gte=start_of_week,
        date__lte=end_of_week
    )

# Статистика по категории
@dp.message(Command(commands=['category']))
async def send_category_stats(message: types.Message, state: FSMContext):
    if not await check_consent_or_block(message, state):
        return
    # Команда /category food
    command_args = message.text.split(maxsplit=1)
    if len(command_args) < 2:
        await message.reply("Пожалуйста, укажите категорию. Пример: /category еда")
        return

    category_name = command_args[1].strip().capitalize() # Приводим к стандартному формату
    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)

    try:
        category = await get_category_by_name(category_name)
    except Category.DoesNotExist:
        await message.reply(f"Категория '{category_name}' не найдена.")
        return

    # Фильтруем транзакции по пользователю и категории за всё время (можно добавить фильтр по дате)
    # Пока за всё время для простоты
    transactions = await get_transactions_for_user_and_category(user, category)

    total_expense = await sync_to_async(
        lambda: transactions.filter(type='expense').aggregate(Sum('amount'))['amount__sum'] or 0
    )()
    total_income = await sync_to_async(
        lambda: transactions.filter(type='income').aggregate(Sum('amount'))['amount__sum'] or 0
    )()

    response_text = f"Статистика по категории '{category_name}':\n"
    response_text += f"Доходы: {total_income:.2f}\n"
    response_text += f"Расходы: {total_expense:.2f}\n"
    response_text += f"Баланс: {total_income - total_expense:.2f}"

    await message.reply(response_text)

# Обработчик кнопки "Стат_месяц"
@dp.message(lambda msg: msg.text == "Стат_месяц")
async def stat_month_menu(message: types.Message):
    today = datetime.now().date()
    current_month = today.strftime("%m.%Y")
    first_day_this_month = today.replace(day=1)
    last_day_prev_month = first_day_this_month - timedelta(days=1)
    prev_month = last_day_prev_month.strftime("%m.%Y")

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Текущий месяц", callback_data=f"graph_month:{current_month}")
    builder.button(text="⬅️ Прошлый месяц", callback_data=f"graph_month:{prev_month}")
    builder.button(text="📅 Ввести вручную", callback_data="graph_month:enter")
    builder.adjust(1)

    await message.answer("📊 Выберите месяц для отчёта:", reply_markup=builder.as_markup())

# Обработчик callback для «ввести вручную»
@dp.callback_query(lambda c: c.data == "graph_month:enter")
async def request_month_input(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "Введите месяц в формате <b>ММ.ГГГГ</b> (например, <code>10.2025</code>):",
        parse_mode="HTML"
    )
    await state.set_state(MonthInput.waiting_for_month)

# Обработчик выбора месяца через кнопки
@dp.callback_query(lambda c: c.data.startswith("graph_month:") and c.data != "graph_month:enter")
async def handle_predefined_month(callback: CallbackQuery):
    await callback.answer()
    month_str = callback.data.split(":", 1)[1]
    try:
        start_date, end_date = parse_month(month_str)
    except Exception:
        await callback.message.answer("Ошибка: неверный формат месяца.")
        return

    user = await get_or_create_django_user(callback.from_user.id, callback.from_user.username)
    transactions = await get_transactions_for_user_and_date_range(user, start_date, end_date)
    transactions_list = await sync_to_async(list)(transactions)

    if not transactions_list:
        await callback.message.answer(f"📭 Нет транзакций за {month_str}.")
        return

    chart_buffer = await sync_to_async(generate_monthly_chart)(transactions_list)
    await callback.message.answer_photo(
        photo=types.BufferedInputFile(chart_buffer.read(), filename=f"month_{month_str}.png"),
        caption=f"📈 Отчёт за {month_str}"
    )

    advice = await sync_to_async(generate_advice)(transactions_list)
    if advice:
        await callback.message.answer(advice)

# Обработчик текстового ввода месяца в состоянии
@dp.message(MonthInput.waiting_for_month)
async def process_month_input(message: types.Message, state: FSMContext):
    month_str = message.text.strip()
    try:
        start_date, end_date = parse_month(month_str)
    except Exception:
        await message.answer(
            "❌ Неверный формат.\n"
            "Пожалуйста, введите месяц как <b>ММ.ГГГГ</b> (например, <code>03.2025</code>).",
            parse_mode="HTML"
        )
        return  # Остаёмся в том же состоянии — ждём правильный ввод

    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)
    transactions = await get_transactions_for_user_and_date_range(user, start_date, end_date)
    transactions_list = await sync_to_async(list)(transactions)

    if not transactions_list:
        await message.answer(f"📭 Нет транзакций за {month_str}.")
    else:
        chart_buffer = await sync_to_async(generate_monthly_chart)(transactions_list)
        await message.answer_photo(
            photo=types.BufferedInputFile(chart_buffer.read(), filename=f"month_{month_str}.png"),
            caption=f"📈 Отчёт за {month_str}"
        )
        advice = await sync_to_async(generate_advice)(transactions_list)
        if advice:
            await message.answer(advice)

    await state.clear()  # Выходим из состояния

# Добавить транзакцию
@dp.message(Command(commands=['add']))
async def add_transaction(message: types.Message, state: FSMContext):
    if not await check_consent_or_block(message, state):
        return
    # Команда /add expense 500 21.10.2025 Транспорт Обед в McDonald's
    command_args = message.text.split(maxsplit=5) # Разбиваем на максимум 6 частей
    if len(command_args) < 6:
        await message.reply("Неверный формат. Пример: /add expense 500 21.10.2025 Транспорт Поездка на обед")
        return

    transaction_type = command_args[1].lower()
    try:
        amount = float(command_args[2])
    except ValueError:
        await message.reply("Сумма должна быть числом.")
        return

    date_str = command_args[3]  # Новая часть - строка даты
    category_name = command_args[4].capitalize() # Приводим к стандартному формату
    description = command_args[5] if len(command_args) > 5 else "" # Описание может быть пустым

    # Получаем пользователя
    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)

    # Проверяем тип операции
    if transaction_type not in ['income', 'expense']:
        await message.reply("Тип операции должен быть 'income' или 'expense'.")
        return

    # Парсим дату
    try:
        # Определяем формат даты DD.MM.YYYY
        parsed_date = datetime.strptime(date_str, '%d.%m.%Y').date()
    except ValueError:
        await message.reply("Неверный формат даты. Используйте формат ДД.ММ.ГГГГ (например, 21.10.2025).")
        return

    # Находим категорию
    try:
        category = await get_category_by_name(category_name)
    except Category.DoesNotExist:
        await message.reply(f"Категория '{category_name}' не найдена.")
        return

    # Создаём транзакцию
    try:
        await create_transaction(
            user=user,
            amount=amount,
            date=parsed_date, # <-- Передаём parsed_date вместо datetime.now().date()
            type=transaction_type,
            category_id=category.id,
            description=description
        )
        await message.reply(
            f"Транзакция '{transaction_type} {amount} {parsed_date.strftime('%d.%m.%Y')} {category.name}' успешно добавлена.")
    except Exception as e:
        await message.reply(f"Ошибка при добавлении транзакции: {e}")

# График за неделю
@dp.message(Command(commands=['graph_week']))
async def send_weekly_graph(message: types.Message, state: FSMContext):
    if not await check_consent_or_block(message, state):
        return

    """
    Отправляет пользователю график доходов/расходов за неделю.
    """
    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)
    today = datetime.now().date()
    # Начало недели (понедельник)
    start_of_week = today - timedelta(days=today.weekday())
    # Конец недели (включительно сегодня)
    end_of_week = today

    # Получаем QuerySet и *выполняем* его с помощью sync_to_async
    transactions_queryset = await get_transactions_for_user_and_week(user, start_of_week, end_of_week)
    # Теперь нужно получить список объектов, выполнив запрос
    # Оборачиваем .list() в sync_to_async
    transactions_list = await sync_to_async(list)(transactions_queryset)

    if not transactions_list: # Проверяем длину списка, а не QuerySet
        await message.reply("За эту неделю нет транзакций для отображения графика.")
        return

    # Передаём *список* объектов в синхронную функцию
    # Оборачиваем вызов generate_weekly_chart в sync_to_async
    chart_buffer = await sync_to_async(generate_weekly_chart)(transactions_list)

    # Отправляем изображение
    await message.answer_photo(photo=types.BufferedInputFile(chart_buffer.read(), filename="weekly_chart.png"))

    # Генерируем и отправляем совет
    advice_text = await sync_to_async(generate_advice)(transactions_list)
    if advice_text:
        await message.answer(advice_text)

@dp.message(Command(commands=['graph_month']))
async def send_monthly_graph(message: types.Message, state: FSMContext):
    if not await check_consent_or_block(message, state):
        return
    """
    Отправляет пользователю график доходов/расходов за текущий месяц.
    """
    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)
    today = datetime.now().date()
    # Начало месяца
    start_of_month = today.replace(day=1)
    # Конец месяца - это сегодня
    end_of_month = today

    # Получаем QuerySet и *выполняем* его
    transactions_queryset = await get_transactions_for_user_and_date_range(user, start_of_month, end_of_month)
    transactions_list = await sync_to_async(list)(transactions_queryset)

    if not transactions_list: # Проверяем длину списка
        await message.reply("За этот месяц нет транзакций для отображения графика.")
        return

    # Передаём *список* объектов в синхронную функцию
    chart_buffer = await sync_to_async(generate_monthly_chart)(transactions_list)

    # Отправляем изображение
    await message.answer_photo(photo=types.BufferedInputFile(chart_buffer.read(), filename="monthly_chart.png"))

    # Генерируем и отправляем совет
    advice_text = await sync_to_async(generate_advice)(transactions_list)
    if advice_text:
        await message.answer(advice_text)

# Обработчик callback_query для месяцев
@dp.callback_query(lambda c: c.data.startswith("graph_month:"))
async def handle_month_selection(callback: CallbackQuery):
    await callback.answer()  # Убираем "часики" на кнопке

    data = callback.data
    user = await get_or_create_django_user(callback.from_user.id, callback.from_user.username)

    if data == "graph_month:custom":
        # Запрашиваем ввод от пользователя
        await callback.message.answer("Введите месяц в формате ММ.ГГГГ (например, 10.2025):")
        # Устанавливаем состояние (но без FSM — просто ждём следующее сообщение)
        # Для простоты будем обрабатывать следующее сообщение как ввод месяца
        # → реализуем это через флаг в контексте или просто обработчиком текста
        # Но так как у нас нет FSM, сделаем временный костыль: запомним, что ждём месяц
        # В реальном проекте используйте FSM (aiogram.fsm), но для MVP — так:
        # Мы создадим глобальный словарь (не для продакшена!) или лучше — обработчик текста с проверкой
        # Однако: проще создать отдельную команду-заглушку. Но давай сделаем правильно — через FSM.

        # ⚠️ ВРЕМЕННОЕ РЕШЕНИЕ БЕЗ FSM:
        # Мы просто скажем пользователю использовать команду
        await callback.message.answer(
            "Пока что введите команду вручную:\n"
            "<code>/graph_month_full 10.2025</code>",
            parse_mode="HTML"
        )
        return

    # Извлекаем месяц.ГГГГ
    month_str = data.split(":", 1)[1]
    try:
        start_date, end_date = parse_month(month_str)
    except Exception:
        await callback.message.answer("Ошибка: неверный формат месяца.")
        return

    transactions = await get_transactions_for_user_and_date_range(user, start_date, end_date)
    transactions_list = await sync_to_async(list)(transactions)

    if not transactions_list:
        await callback.message.answer(f"Нет транзакций за {month_str}.")
        return

    chart_buffer = await sync_to_async(generate_monthly_chart)(transactions_list)
    await callback.message.answer_photo(
        photo=types.BufferedInputFile(chart_buffer.read(), filename=f"month_{month_str}.png"),
        caption=f"📈 График за {month_str}"
    )

    advice = await sync_to_async(generate_advice)(transactions_list)
    if advice:
        await callback.message.answer(advice)


# Обработчик predefined_day
@dp.callback_query(lambda c: c.data.startswith("graph_day:") and c.data != "graph_day:enter")
async def handle_predefined_day(callback: CallbackQuery):
    await callback.answer()
    date_str = callback.data.split(":", 1)[1]
    try:
        target_date = parse_day(date_str)
    except Exception:
        await callback.message.answer("Ошибка: неверный формат даты.")
        return

    user = await get_or_create_django_user(callback.from_user.id, callback.from_user.username)
    transactions = await get_transactions_for_user_and_date(user, target_date)
    transactions_list = await sync_to_async(list)(transactions)

    if not transactions_list:
        await callback.message.answer(f"📭 Нет транзакций за {target_date.strftime('%d.%m.%Y')}.")
        return

    expenses = [t for t in transactions_list if t.type == 'expense']
    chart_buffer = await sync_to_async(generate_category_pie_chart)(expenses or [])
    await callback.message.answer_photo(
        photo=types.BufferedInputFile(chart_buffer.read(), filename=f"day_{target_date}.png"),
        caption=f"📊 Отчёт за {target_date.strftime('%d.%m.%Y')}"
    )
    advice = await sync_to_async(generate_advice)(transactions_list)
    if advice:
        await callback.message.answer(advice)

# Обработчик predefined_week
@dp.callback_query(lambda c: c.data.startswith("graph_week_range:"))
async def handle_predefined_week(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.message.answer("Ошибка: неверный формат недели.")
        return

    try:
        start_date = parse_day(parts[1])
        end_date = parse_day(parts[2])
    except Exception:
        await callback.message.answer("Ошибка: неверный формат даты.")
        return

    user = await get_or_create_django_user(callback.from_user.id, callback.from_user.username)
    transactions = await get_transactions_for_user_and_date_range(user, start_date, end_date)
    transactions_list = await sync_to_async(list)(transactions)

    if not transactions_list:
        await callback.message.answer(
            f"📭 Нет транзакций за неделю с {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')}."
        )
        return

    chart_buffer = await sync_to_async(generate_weekly_chart)(transactions_list)
    await callback.message.answer_photo(
        photo=types.BufferedInputFile(chart_buffer.read(), filename=f"week_{start_date}.png"),
        caption=f"📈 Отчёт за неделю\n{start_date.strftime('%d.%m.%Y')} – {end_date.strftime('%d.%m.%Y')}"
    )
    advice = await sync_to_async(generate_advice)(transactions_list)
    if advice:
        await callback.message.answer(advice)

# Обработка ...
@dp.message(Command(commands=['graph_day']))
async def send_daily_graph(message: types.Message, state: FSMContext):
    if not await check_consent_or_block(message, state):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Укажите дату в формате ДД.ММ.ГГГГ. Пример: /graph_day 21.10.2025")
        return

    date_str = parts[1].strip()
    try:
        target_date = parse_day(date_str)
    except ValueError:
        await message.reply("Неверный формат даты. Используйте ДД.ММ.ГГГГ (например, 21.10.2025).")
        return

    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)
    transactions = await get_transactions_for_user_and_date(user, target_date)
    transactions_list = await sync_to_async(list)(transactions)

    if not transactions_list:
        await message.reply(f"Нет транзакций за {target_date.strftime('%d.%m.%Y')}.")
        return

    # Для одного дня используем круговую диаграмму по категориям (только расходы)
    expenses_only = [t for t in transactions_list if t.type == 'expense']
    if expenses_only:
        chart_buffer = await sync_to_async(generate_category_pie_chart)(expenses_only)
        caption = f"Расходы по категориям за {target_date.strftime('%d.%m.%Y')}"
    else:
        # Если нет расходов — генерируем пустую диаграмму
        chart_buffer = await sync_to_async(generate_category_pie_chart)([])
        caption = f"Нет расходов за {target_date.strftime('%d.%m.%Y')}"

    await message.answer_photo(
        photo=types.BufferedInputFile(chart_buffer.read(), filename=f"day_{target_date}.png"),
        caption=caption
    )

    # Совет на основе всех транзакций за день
    advice = await sync_to_async(generate_advice)(transactions_list)
    if advice:
        await message.answer(advice)


@dp.message(Command(commands=['graph_month_full']))
async def send_monthly_graph_custom(message: types.Message, state: FSMContext):
    if not await check_consent_or_block(message, state):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Укажите месяц в формате ММ.ГГГГ. Пример: /graph_month_full 10.2025")
        return

    month_str = parts[1].strip()
    try:
        start_date, end_date = parse_month(month_str)
    except Exception as e:
        await message.reply("Неверный формат. Используйте ММ.ГГГГ (например, 10.2025).")
        return

    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)
    transactions = await get_transactions_for_user_and_date_range(user, start_date, end_date)
    transactions_list = await sync_to_async(list)(transactions)

    if not transactions_list:
        await message.reply(f"Нет транзакций за {month_str}.")
        return

    chart_buffer = await sync_to_async(generate_monthly_chart)(transactions_list)
    await message.answer_photo(
        photo=types.BufferedInputFile(chart_buffer.read(), filename=f"month_{month_str}.png"),
        caption=f"График доходов и расходов за {month_str}"
    )

    advice = await sync_to_async(generate_advice)(transactions_list)
    if advice:
        await message.answer(advice)


@dp.message(Command(commands=['graph_year']))
async def send_yearly_graph(message: types.Message, state: FSMContext):
    if not await check_consent_or_block(message, state):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Укажите год. Пример: /graph_year 2025")
        return

    year_str = parts[1].strip()
    try:
        start_date, end_date = parse_year(year_str)
    except Exception:
        await message.reply("Неверный формат года. Используйте ГГГГ (например, 2025).")
        return

    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)
    transactions = await get_transactions_for_user_and_date_range(user, start_date, end_date)
    transactions_list = await sync_to_async(list)(transactions)

    if not transactions_list:
        await message.reply(f"Нет транзакций за {year_str} год.")
        return

    chart_buffer = await sync_to_async(generate_yearly_chart)(transactions_list)
    await message.answer_photo(
        photo=types.BufferedInputFile(chart_buffer.read(), filename=f"year_{year_str}.png"),
        caption=f"График доходов и расходов по месяцам за {year_str} год"
    )

    advice = await sync_to_async(generate_advice)(transactions_list)
    if advice:
        await message.answer(advice)

@dp.message(Command(commands=['chart_categories']))
async def send_category_chart(message: types.Message, state: FSMContext):
    if not await check_consent_or_block(message, state):
        return
    """
    Отправляет пользователю круговую диаграмму расходов по категориям за указанный период (week/month).
    """
    # Разбиваем команду на части
    parts = message.text.split(maxsplit=1) # Разбиваем на /chart_categories и период
    period = parts[1].lower() if len(parts) > 1 else 'week' # По умолчанию - неделя

    user = await get_or_create_django_user(message.from_user.id, message.from_user.username)
    today = datetime.now().date()

    # Определяем даты начала и конца периода
    if period == 'week':
        start_date = today - timedelta(days=today.weekday()) # Понедельник недели
        end_date = today
        period_name = "за неделю"
    elif period == 'month':
        start_date = today.replace(day=1) # Первый день месяца
        end_date = today
        period_name = "с начала месяца"
    else:
        await message.reply("Неверный период. Используйте 'week' или 'month'. Пример: /chart_categories week")
        return

    # Получаем расходы за период
    expenses_queryset = await get_expenses_for_user_and_period(user, start_date, end_date)
    # Выполняем запрос
    expenses_list = await sync_to_async(list)(expenses_queryset)

    if not expenses_list:
        await message.reply(f"Нет расходов {period_name} для отображения диаграммы.")
        return

    # Генерируем диаграмму
    chart_buffer = await sync_to_async(generate_category_pie_chart)(expenses_list)

    # Отправляем изображение
    await message.answer_photo(
        photo=types.BufferedInputFile(chart_buffer.read(), filename=f"category_chart_{period}.png"),
        caption=f"Расходы по категориям {period_name} ({start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')})"
    )

    # Получаем ВСЕ транзакции за период
    all_transactions_queryset = await get_transactions_for_user_and_date_range(user, start_date, end_date)
    all_transactions_list = await sync_to_async(list)(all_transactions_queryset)

    # Генерируем и отправляем совет на основе всех транзакций
    advice_text = await sync_to_async(generate_advice)(all_transactions_list) # <-- Передаём all_transactions_list
    if advice_text:
        await message.answer(advice_text)

@dp.message(Command(commands=['help']))
async def send_help(message: types.Message, state: FSMContext):
    if not await check_consent_or_block(message, state):
        return
    await message.reply(
        "Доступные команды:\n"
        "/today - расходы за сегодня\n"
        "/week - статистика за неделю\n"
        "/category <название> - траты по категории\n"
        "/add <type> <amount> <date> <category> <description> - добавить операцию\n\n"
        "📈 Графики:\n"
        "/graph_week - график за текущую неделю\n"
        "/graph_month - график за текущий месяц\n"
        "/graph_day ДД.ММ.ГГГГ - график за конкретный день\n"
        "/graph_month_full ММ.ГГГГ - график за конкретный месяц\n"
        "/graph_year ГГГГ - график за целый год\n\n"
        "📊 Диаграммы по категориям:\n"
        "/chart_categories week - за текущую неделю\n"
        "/chart_categories month - с начала текущего месяца\n"
        "/help - этот список команд"
    )

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен...")
    dp.run_polling(bot)
