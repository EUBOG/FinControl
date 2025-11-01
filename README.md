# FinControl - Система управления личными финансами

![Django](https://img.shields.io/badge/Django-5.2.7-green)
![Python](https://img.shields.io/badge/Python-3.8+-blue)

FinControl - это веб-приложение для управления личными финансами с возможностью создания отчетов и аналитики.

## 🚀 Возможности

- ✅ Учет доходов и расходов
- ✅ Категоризация операций
- ✅ Визуализация данных в PDF отчетах
- ✅ Автоматические уведомления (cron)
- ✅ Аутентификация пользователей
- ✅ Аналитика по категориям

## 📦 Установка

### 1. Клонирование репозитория
```bash
git clone https://github.com/yourusername/FinControl.git
cd FinControl
```
### 2. Создание виртуального окружения
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```
### 3. Установка зависимостей
```bash
pip install -r requirements.txt
```
### 4. Настройка базы данных
```bash
python manage.py migrate
```
### 5. Создание суперпользователя
```bash
python manage.py createsuperuser
```
### 6. Запуск сервера
```bash
python manage.py runserver
```
### Структура проекта
```
FinControl/
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
├── manage.py
├── FinControl/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── accounts/
├── finance/
├── templates/
└── media/
```
### Использование
1. Регистрация и вход - создайте аккаунт или войдите в систему
2. Добавление операций - укажите доходы и расходы по категориям
3. Просмотр отчетов - генерируйте PDF отчеты за выбранный период
4. Аналитика - отслеживайте статистику по категориям

### Технологии
- Backend: Django 5.2.7
- Frontend: Bootstrap 5, HTML/CSS
- База данных: SQLite3
- PDF генерация: ReportLab
- Планировщик: django-crontab
