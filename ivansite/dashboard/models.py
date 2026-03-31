from django.db import models
from django.contrib.auth.models import User


class Document(models.Model):
    TYPE_INCOME_EXPENSE = 'income_expense'
    TYPE_CASH_FLOW = 'cash_flow'
    TYPE_BUDGET = 'budget'
    TYPE_KPI = 'kpi'

    DOCUMENT_TYPES = [
        (TYPE_INCOME_EXPENSE, 'Отчет по доходам и расходам'),
        (TYPE_CASH_FLOW, 'Банковская выписка / ДДС'),
        (TYPE_BUDGET, 'Бюджет подразделения'),
        (TYPE_KPI, 'KPI-отчет подразделения'),
    ]

    STATUS_UPLOADED = 'uploaded'
    STATUS_VALIDATING = 'validating'
    STATUS_ANALYZING = 'analyzing'
    STATUS_DONE = 'done'
    STATUS_ERROR = 'error'

    STATUSES = [
        (STATUS_UPLOADED, 'Загружен'),
        (STATUS_VALIDATING, 'Проверяется'),
        (STATUS_ANALYZING, 'Анализируется'),
        (STATUS_DONE, 'Проанализирован'),
        (STATUS_ERROR, 'Ошибка'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='uploads/')
    file_name = models.CharField(max_length=255)
    doc_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES)
    period = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_UPLOADED)
    error_message = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.file_name} ({self.get_doc_type_display()})"


class FinancialRecord(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='records')
    date = models.DateField(null=True, blank=True)
    category = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    record_type = models.CharField(max_length=50, blank=True)
    counterparty = models.CharField(max_length=255, blank=True)
    department = models.CharField(max_length=255, blank=True)
    indicator = models.CharField(max_length=255, blank=True)
    plan_value = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    fact_value = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    period = models.CharField(max_length=100, blank=True)
    extra = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.document} | {self.date} | {self.amount}"


class AnalysisResult(models.Model):
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name='analysis')
    total_income = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_expense = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    profit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_inflow = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_outflow = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    net_flow = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    chart_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Analysis: {self.document}"


class Metric(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='metrics')
    metric_name = models.CharField(max_length=255)
    value = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.metric_name}: {self.value}"
