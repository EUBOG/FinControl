# finance/urls.py
from django.urls import path
from . import views # Импортируем views из текущего приложения

app_name = 'finance' # Пространство имён для URL приложения 'finance'

urlpatterns = [
    # Маршрут для создания новой транзакции
    # При переходе на / (пустой путь относительно включенного URLConf)
    # будет вызвано TransactionCreateView
    path('', views.TransactionCreateView.as_view(), name='transaction_create'),
    # Маршрут для загрузки параметров отчёта (AJAX)
    path('load_report/<int:report_id>/', views.load_saved_report, name='load_saved_report'),
    # Пример: если бы был список транзакций
    # path('list/', views.TransactionListView.as_view(), name='transaction_list'),
    path('reports/', views.report_builder, name='report_builder'),
    path('reports/create/', views.create_report, name='create_report'),
    path('reports/quick/', views.quick_reports, name='quick_reports'),
    # path('reports/download/<int:report_id>/', views.download_report, name='download_report'),
    # path('reports/generate/<int:report_id>/', views.generate_report_now, name='generate_report_now'),
]