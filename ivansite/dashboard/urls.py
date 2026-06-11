from django.urls import path
from . import views

app_name = 'finassist'

urlpatterns = [
    path('', views.upload_view, name='upload'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('history/', views.history_view, name='history'),
    path('audit/', views.audit_view, name='audit'),
    path('document/<int:pk>/', views.document_detail, name='document_detail'),
    path('document/<int:pk>/delete/', views.delete_document, name='delete_document'),
    path('document/<int:pk>/export/', views.export_csv, name='export_csv'),
    path('document/<int:pk>/export/excel/', views.export_excel, name='export_excel'),
    path('document/<int:pk>/export/pdf/', views.export_pdf, name='export_pdf'),
    path('document/<int:pk>/export/visual/', views.export_visual, name='export_visual'),
    path('document/<int:pk>/api/', views.api_document, name='api_document'),
    path('document/<int:pk>/panels/', views.save_panels, name='save_panels'),
    path('formats/', views.formats_view, name='formats'),
    path('detect/', views.detect_type, name='detect_type'),
    path('db/', views.db_schema_view, name='db_schema'),
    path('entities/', views.entities_view, name='entities'),
    path('entities/<int:pk>/', views.entity_detail, name='entity_detail'),
    path('entities/<int:pk>/delete/', views.entity_delete, name='entity_delete'),
    path('compare/', views.compare_view, name='compare'),
]

