# finance/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Transaction, Category, SavedReport, UserConsent

# Инлайн для согласия
class UserConsentInline(admin.StackedInline):
    model = UserConsent
    can_delete = False
    verbose_name_plural = 'Согласие на обработку ПД'
    fields = ('is_valid', 'given_at', 'revoked_at')
    readonly_fields = ('is_valid', 'given_at', 'revoked_at')

# === ОСТАВЛЯЕМ ТОЛЬКО ОДИН UserConsentAdmin ===
@admin.register(UserConsent)
class UserConsentAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_status', 'given_at', 'revoked_at')
    list_filter = ('given_at', 'revoked_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('given_at', 'revoked_at')

    def get_status(self, obj):
        if obj.given_at and not obj.revoked_at:
            return "✅ Действует"
        elif obj.given_at and obj.revoked_at:
            return "🛑 Отозвано"
        else:
            return "❓ Не задано"
    get_status.short_description = 'Статус'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

# Админка для пользователей
class UserAdmin(BaseUserAdmin):
    inlines = (UserConsentInline,)
    list_display = ('username', 'email', 'get_consent_status', 'date_joined')
    list_filter = ('last_login', 'is_active', 'date_joined')

    def get_consent_status(self, obj):
        try:
            if obj.consent.given_at and not obj.consent.revoked_at:
                return "✅ Действует"
            elif obj.consent.given_at and obj.consent.revoked_at:
                return "🛑 Отозвано"
            else:
                return "❓ Не задано"
        except UserConsent.DoesNotExist:
            return "❌ Не дано"
    get_consent_status.short_description = 'Статус согласия'

# Перерегистрируем User
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

# Остальные модели
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'type', 'formatted_amount', 'formatted_date', 'category', 'description')

    def formatted_date(self, obj):
        return format_html('<span>{}</span>', obj.date.strftime('%d.%m.%Y')) if obj.date else "-"
    formatted_date.short_description = 'Дата (ДД.ММ.ГГГГ)'
    formatted_date.admin_order_field = 'date'

    def formatted_amount(self, obj):
        return format_html('<span style="text-align: right; display: block; padding-right: 8px;">{}</span>', obj.amount)
    formatted_amount.short_description = 'Сумма'
    formatted_amount.admin_order_field = 'amount'

@admin.register(SavedReport)
class SavedReportAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'created_at', 'updated_at')
    list_filter = ('user', 'created_at')
    search_fields = ('name', 'user__username')
    readonly_fields = ('created_at', 'updated_at')