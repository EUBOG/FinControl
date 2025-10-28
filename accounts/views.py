# accounts/views.py
from django.contrib.auth.forms import UserCreationForm
from django.views.generic import CreateView
from django.contrib.auth.views import LogoutView # Импортируем стандартный LogoutView
from django.urls import reverse_lazy

# Новое представление, наследуемое от LogoutView
class CustomLogoutView(LogoutView):
    """
    Кастомное представление для выхода из системы.
    Перенаправляет на страницу входа после выхода.
    """
    next_page = reverse_lazy('login')

class SignUpView(CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy('login') # Перенаправление на страницу входа после регистрации
    template_name = 'registration/register.html'
