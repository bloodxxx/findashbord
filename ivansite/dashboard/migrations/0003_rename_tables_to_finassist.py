from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('finassist', '0002_document_period_end_document_period_start_auditlog_and_more'),
    ]

    operations = [
        migrations.AlterModelTable('Document', 'finassist_document'),
        migrations.AlterModelTable('FinancialRecord', 'finassist_financialrecord'),
        migrations.AlterModelTable('AnalysisResult', 'finassist_analysisresult'),
        migrations.AlterModelTable('Metric', 'finassist_metric'),
        migrations.AlterModelTable('AuditLog', 'finassist_auditlog'),
        migrations.AlterModelTable('PanelSettings', 'finassist_panelsettings'),
    ]
