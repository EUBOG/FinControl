# finance/models.py
import json # Импортируем json для сериализации параметров
import django
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from decimal import Decimal

# Определим класс согласия
class UserConsent(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='consent')
    telegram_id = models.BigIntegerField(null=True, blank=True, verbose_name="Telegram ID")
    given_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата согласия")
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата отзыва")

    @property
    def is_valid(self):
        return self.given_at is not None and self.revoked_at is None

    def __str__(self):
        status = "Действует" if self.is_valid else "Отозвано/Не дано"
        return f"Согласие {self.user.username}: {status}"

    class Meta:
        verbose_name = "Согласие на обработку ПД"
        verbose_name_plural = "Согласия на обработку ПД"

class Category(models.Model):
    """
    Модель для категории финансовой операции.
    """
    name = models.CharField(max_length=100, unique=True, verbose_name="Название категории")

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["name"] # Сортировка по умолчанию по имени

    def __str__(self):
        return self.name


class Transaction(models.Model):
    """
    Модель для финансовой операции (доход или расход).
    """
    TRANSACTION_TYPES = [
        ('income', 'Доход'),
        ('expense', 'Расход'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE, # При удалении пользователя удаляются его транзакции
        verbose_name="Пользователь"
    )
    amount = models.DecimalField(
        max_digits=12, # Общее количество цифр (например, 999999999.99)
        decimal_places=2, # Количество знаков после запятой
        validators=[MinValueValidator(Decimal('0.01'))], # Сумма должна быть > 0
        verbose_name="Сумма"
    )
    date = models.DateField(verbose_name="Дата")
    type = models.CharField(
        max_length=10,
        choices=TRANSACTION_TYPES,
        verbose_name="Тип операции"
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT, # При удалении категории транзакции не удаляются (ошибка, если не обработать)
        verbose_name="Категория"
    )
    description = models.TextField(
        blank=True, # Поле не обязательное
        null=True,  # Может быть NULL в БД
        verbose_name="Описание"
    )

    class Meta:
        verbose_name = "Финансовая операция"
        verbose_name_plural = "Финансовые операции"
        ordering = ["-date"] # Сортировка по умолчанию по дате (новые сверху)

    def __str__(self):
        return f"{self.type} {self.amount} {self.user.username} - {self.category.name}"


class SavedReport(models.Model):
    REPORT_FORMATS = [
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('filter', 'Фильтр'),  # существующий тип
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name="Пользователь"
    )
    name = models.CharField(max_length=200, verbose_name="Название отчёта")
    report_format = models.CharField(
        max_length=10,
        choices=REPORT_FORMATS,
        default='filter',
        verbose_name="Формат отчета"
    )
    filters = models.JSONField(verbose_name="Параметры фильтрации")
    file = models.FileField(
        upload_to='reports/%Y/%m/%d/',
        null=True,
        blank=True,
        verbose_name="Файл отчета"
    )
    file_generated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Время генерации файла"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Сохранённый отчёт"
        verbose_name_plural = "Сохранённые отчёты"
        constraints = [
            models.UniqueConstraint(fields=['user', 'name'], name='unique_user_report_name')
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.user.username})"

    def get_filters(self):
        return self.filters

    def set_filters(self, filters_dict):
        self.filters = filters_dict

    @property
    def has_file(self):
        return bool(self.file) and os.path.exists(self.file.path)