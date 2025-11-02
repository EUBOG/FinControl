# accounts/backends.py - СОЗДАТЬ новый файл
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q

class EmailBackend(ModelBackend):
    """
    Кастомный бэкенд для аутентификации по email или username
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            # Ищем пользователя по username ИЛИ email
            user = User.objects.get(
                Q(username=username) | Q(email=username)
            )
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            # Если найдено несколько пользователей (маловероятно), берем первого
            user = User.objects.filter(
                Q(username=username) | Q(email=username)
            ).first()
            if user and user.check_password(password):
                return user
        return None