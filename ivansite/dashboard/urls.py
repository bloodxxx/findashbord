from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.upload_view, name='upload'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('history/', views.history_view, name='history'),
    path('document/<int:pk>/', views.document_detail, name='document_detail'),
    path('document/<int:pk>/delete/', views.delete_document, name='delete_document'),
    path('document/<int:pk>/export/', views.export_csv, name='export_csv'),
    path('formats/', views.formats_view, name='formats'),
]
