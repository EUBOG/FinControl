# FinControl/FinControl/urls.py
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from django.conf import settings
from django.conf.urls.static import static
from finance import views as finance_views
from accounts import views as accounts_views

urlpatterns = [
    path('', finance_views.index, name='home'),
    path('admin/', admin.site.urls),

    # Подключаем URL для регистрации
    path('accounts/register/', accounts_views.SignUpView.as_view(), name='register'),
    path('accounts/logout/', accounts_views.CustomLogoutView.as_view(), name='logout'),

    # Кастомный логин с нашей формой
    path('accounts/login/', accounts_views.CustomLoginView.as_view(), name='login'),

    # Подключаем остальные URL аутентификации
    path('accounts/password_change/', auth_views.PasswordChangeView.as_view(), name='password_change'),
    path('accounts/password_change/done/', auth_views.PasswordChangeDoneView.as_view(), name='password_change_done'),
    path('accounts/password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('accounts/password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('accounts/reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(),
         name='password_reset_confirm'),
    path('accounts/reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),

    # Подключаем URL-ы из приложения 'finance'
    path('transactions/', include('finance.urls')),
]

# Для медиа файлов в разработке
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)