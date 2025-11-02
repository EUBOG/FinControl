# accounts/views.py
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.views.generic import CreateView
from django.contrib.auth.views import LogoutView, LoginView
from django.urls import reverse_lazy
from .forms import CustomUserCreationForm, CustomAuthenticationForm  # ← ДОБАВИТЬ этот импорт


class CustomLoginView(LoginView):
    """
    Кастомное представление для входа с измененными labels
    """
    template_name = 'registration/login.html'
    authentication_form = CustomAuthenticationForm


class CustomLogoutView(LogoutView):
    """
    Кастомное представление для выхода из системы.
    """
    next_page = reverse_lazy('login')


class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'registration/register.html'