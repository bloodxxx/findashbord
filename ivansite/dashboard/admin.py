from django.contrib import admin
from .models import Document, FinancialRecord, AnalysisResult, Metric


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('file_name', 'doc_type', 'user', 'status', 'period', 'uploaded_at')
    list_filter = ('doc_type', 'status')
    search_fields = ('file_name', 'user__username')


@admin.register(FinancialRecord)
class FinancialRecordAdmin(admin.ModelAdmin):
    list_display = ('document', 'date', 'category', 'amount', 'record_type')
    list_filter = ('record_type',)


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display = ('document', 'total_income', 'total_expense', 'profit', 'created_at')


@admin.register(Metric)
class MetricAdmin(admin.ModelAdmin):
    list_display = ('document', 'metric_name', 'value')
