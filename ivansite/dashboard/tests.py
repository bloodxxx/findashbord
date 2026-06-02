import json
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse

from .analyzers import _forecast, _period_key, _aggregate_by_gran, analyze_document
from .models import Document, FinancialRecord, AnalysisResult, Metric, AuditLog, PanelSettings
from .parsers import parse_document


CSV_IE = b"""date,article,type,amount
05.01.2024,Sales,income,100000
10.01.2024,Rent,expense,30000
05.02.2024,Sales,income,120000
10.02.2024,Rent,expense,30000
"""

CSV_CF = b"""date,type,counterparty,amount
05.01.2024,inflow,Alpha,50000
10.01.2024,outflow,Beta,20000
05.02.2024,inflow,Alpha,60000
"""

CSV_BUDGET = b"""period,department,article,plan,fact
Jan 2024,Sales,Salary,100000,95000
Jan 2024,IT,Equipment,50000,60000
"""

CSV_KPI = b"""period,department,indicator,plan,fact
Q1 2024,Sales,Revenue,1000000,1100000
Q1 2024,IT,Uptime,99.5,99.8
"""


def make_doc(user, csv_bytes, doc_type, name='test.csv'):
    doc = Document.objects.create(
        user=user, file_name=name, doc_type=doc_type,
        file=SimpleUploadedFile(name, csv_bytes, content_type='text/csv'),
        status=Document.STATUS_VALIDATING,
    )
    doc.file.seek(0)
    recs = parse_document(doc.file, name, doc_type)
    for rd in recs:
        FinancialRecord.objects.create(
            document=doc, date=rd.get('date'), category=rd.get('category', ''),
            amount=rd.get('amount', 0), record_type=rd.get('record_type', ''),
            counterparty=rd.get('counterparty', ''), department=rd.get('department', ''),
            indicator=rd.get('indicator', ''), plan_value=rd.get('plan_value'),
            fact_value=rd.get('fact_value'), period=rd.get('period', ''),
        )
    analyze_document(doc)
    doc.status = Document.STATUS_DONE
    doc.save()
    return doc


class ForecastTest(TestCase):
    def test_linear_trend(self):
        self.assertEqual(_forecast([10, 20, 30], 2), [40.0, 50.0])

    def test_single_value(self):
        self.assertEqual(_forecast([5], 2), [5, 5])

    def test_flat(self):
        self.assertEqual(_forecast([7, 7, 7], 1), [7.0])


class PeriodKeyTest(TestCase):
    def test_month(self):
        self.assertEqual(_period_key(date(2024, 3, 15), 'month'), '2024-03')

    def test_quarter(self):
        self.assertEqual(_period_key(date(2024, 4, 1), 'quarter'), '2024-Q2')

    def test_week(self):
        self.assertEqual(_period_key(date(2024, 1, 8), 'week'), '2024-W02')

    def test_day(self):
        self.assertEqual(_period_key(date(2024, 6, 1), 'day'), '2024-06-01')


class ParserTest(TestCase):
    def test_income_expense(self):
        recs = parse_document(BytesIO(CSV_IE), 'test.csv', 'income_expense')
        self.assertEqual(len(recs), 4)
        self.assertEqual(recs[0]['record_type'], 'income')
        self.assertEqual(recs[1]['record_type'], 'expense')
        self.assertEqual(recs[0]['amount'], Decimal('100000'))

    def test_cash_flow(self):
        recs = parse_document(BytesIO(CSV_CF), 'test.csv', 'cash_flow')
        self.assertEqual(len(recs), 3)
        self.assertEqual(recs[0]['record_type'], 'inflow')
        self.assertEqual(recs[1]['record_type'], 'outflow')

    def test_budget(self):
        recs = parse_document(BytesIO(CSV_BUDGET), 'test.csv', 'budget')
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]['plan_value'], Decimal('100000'))

    def test_kpi(self):
        recs = parse_document(BytesIO(CSV_KPI), 'test.csv', 'kpi')
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]['fact_value'], Decimal('1100000'))

    def test_missing_column_raises(self):
        bad = b"date,amount\n2024-01-01,100\n"
        with self.assertRaises(ValueError):
            parse_document(BytesIO(bad), 'bad.csv', 'income_expense')

    def test_empty_file_raises(self):
        with self.assertRaises(ValueError):
            parse_document(BytesIO(b"date,article,type,amount\n"), 'empty.csv', 'income_expense')


class AnalyzerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('atest', password='pass')

    def test_income_expense_metrics(self):
        doc = make_doc(self.user, CSV_IE, 'income_expense')
        metrics = {m.metric_name: float(m.value) for m in doc.metrics.all()}
        self.assertIn('Общие доходы', metrics)
        self.assertIn('Общие расходы', metrics)
        self.assertIn('Прибыль', metrics)
        self.assertIn('Доход / Расход', metrics)
        self.assertAlmostEqual(metrics['Общие доходы'], 220000)
        self.assertAlmostEqual(metrics['Прибыль'], 160000)
        self.assertGreater(metrics['Доход / Расход'], 1)

    def test_period_auto_detected(self):
        doc = make_doc(self.user, CSV_IE, 'income_expense')
        self.assertEqual(doc.period_start, date(2024, 1, 5))
        self.assertEqual(doc.period_end, date(2024, 2, 10))

    def test_period_aggregation_in_chart_data(self):
        doc = make_doc(self.user, CSV_IE, 'income_expense')
        cd = doc.analysis.chart_data
        self.assertIn('periods', cd)
        for gran in ('day', 'week', 'month', 'quarter'):
            self.assertIn(gran, cd['periods'])
        self.assertEqual(cd['periods']['month']['labels'], ['2024-01', '2024-02'])

    def test_forecast_in_chart_data(self):
        doc = make_doc(self.user, CSV_IE, 'income_expense')
        cd = doc.analysis.chart_data
        self.assertIn('forecast', cd)
        self.assertEqual(len(cd['forecast']['next']), 3)

    def test_cash_flow_avg_counterparty(self):
        doc = make_doc(self.user, CSV_CF, 'cash_flow')
        metrics = {m.metric_name: float(m.value) for m in doc.metrics.all()}
        self.assertIn('Средний оборот на контрагента', metrics)

    def test_budget_pct_metric(self):
        doc = make_doc(self.user, CSV_BUDGET, 'budget')
        metrics = {m.metric_name: float(m.value) for m in doc.metrics.all()}
        self.assertIn('% выполнения', metrics)

    def test_kpi_analysis(self):
        doc = make_doc(self.user, CSV_KPI, 'kpi')
        metrics = {m.metric_name: float(m.value) for m in doc.metrics.all()}
        self.assertIn('% выполненных KPI', metrics)
        self.assertEqual(metrics['% выполненных KPI'], 100.0)


class ViewsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('vtest', email='v@v.local', password='pass')
        self.c = Client()
        self.c.login(username='vtest', password='pass')

    def _upload(self, csv_bytes, doc_type, name='test.csv'):
        f = SimpleUploadedFile(name, csv_bytes, content_type='text/csv')
        return self.c.post('/', {'doc_type': doc_type, 'period': '2024', 'file': f})

    # ── Auth ──
    def test_login_required_redirect(self):
        r = Client().get('/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login/', r.url)

    def test_register(self):
        r = Client().post('/register/', {'username': 'newu', 'password': 'abc123', 'password2': 'abc123'},
                          HTTP_HOST='localhost')
        self.assertEqual(r.status_code, 302)
        self.assertTrue(User.objects.filter(username='newu').exists())

    def test_register_email_saved(self):
        Client().post('/register/', {'username': 'eu', 'email': 'eu@eu.com', 'password': 'abc123', 'password2': 'abc123'},
                      HTTP_HOST='localhost')
        self.assertEqual(User.objects.get(username='eu').email, 'eu@eu.com')

    def test_password_reset_page(self):
        r = Client().get('/password-reset/')
        self.assertEqual(r.status_code, 200)

    # ── Upload ──
    def test_single_upload_redirects_to_detail(self):
        r = self._upload(CSV_IE, 'income_expense')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/document/', r.url)

    def test_batch_upload_redirects_to_history(self):
        f1 = SimpleUploadedFile('a.csv', CSV_IE, content_type='text/csv')
        f2 = SimpleUploadedFile('b.csv', CSV_CF, content_type='text/csv')
        r = self.c.post('/', {'doc_type': 'income_expense', 'period': '2024', 'file': [f1, f2]},
                        HTTP_HOST='localhost')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/history/', r.url)

    def test_invalid_extension_rejected(self):
        f = SimpleUploadedFile('bad.txt', b'data', content_type='text/plain')
        r = self.c.post('/', {'doc_type': 'income_expense', 'file': f})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Document.objects.filter(user=self.user).count(), 0)

    def test_invalid_doc_type_rejected(self):
        f = SimpleUploadedFile('t.csv', CSV_IE, content_type='text/csv')
        r = self.c.post('/', {'doc_type': 'bad_type', 'file': f})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Document.objects.filter(user=self.user).count(), 0)

    # ── Document detail ──
    def test_detail_200(self):
        self._upload(CSV_IE, 'income_expense')
        doc = Document.objects.filter(user=self.user, status='done').first()
        r = self.c.get(f'/document/{doc.pk}/')
        self.assertEqual(r.status_code, 200)

    def test_detail_logs_view(self):
        self._upload(CSV_IE, 'income_expense')
        doc = Document.objects.filter(user=self.user, status='done').first()
        before = AuditLog.objects.filter(user=self.user, action='view').count()
        self.c.get(f'/document/{doc.pk}/')
        self.assertEqual(AuditLog.objects.filter(user=self.user, action='view').count(), before + 1)

    def test_other_user_cannot_view(self):
        self._upload(CSV_IE, 'income_expense')
        doc = Document.objects.filter(user=self.user).first()
        other = Client()
        other.force_login(User.objects.create_user('other', password='p'))
        r = other.get(f'/document/{doc.pk}/')
        self.assertEqual(r.status_code, 404)

    # ── Exports ──
    def _doc(self):
        self._upload(CSV_IE, 'income_expense')
        return Document.objects.filter(user=self.user, status='done').first()

    def test_export_csv(self):
        doc = self._doc()
        r = self.c.get(f'/document/{doc.pk}/export/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('text/csv', r['Content-Type'])

    def test_export_excel(self):
        doc = self._doc()
        r = self.c.get(f'/document/{doc.pk}/export/excel/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('spreadsheetml', r['Content-Type'])

    def test_export_pdf(self):
        doc = self._doc()
        r = self.c.get(f'/document/{doc.pk}/export/pdf/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')

    def test_export_visual(self):
        doc = self._doc()
        png = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        r = self.c.post(f'/document/{doc.pk}/export/visual/',
                        data=json.dumps({'images': [png]}),
                        content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')

    def test_export_logs_audit(self):
        doc = self._doc()
        self.c.get(f'/document/{doc.pk}/export/')
        self.assertTrue(AuditLog.objects.filter(user=self.user, action='export').exists())

    # ── API ──
    def test_api_json(self):
        doc = self._doc()
        r = self.c.get(f'/document/{doc.pk}/api/')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertEqual(data['doc_type'], 'income_expense')
        self.assertIn('chart_data', data)
        self.assertIn('metrics', data)
        self.assertIsNotNone(data['period_start'])

    # ── Audit ──
    def test_audit_page(self):
        r = self.c.get('/audit/')
        self.assertEqual(r.status_code, 200)

    def test_upload_logged(self):
        self._upload(CSV_IE, 'income_expense')
        self.assertTrue(AuditLog.objects.filter(user=self.user, action='upload').exists())

    def test_delete_logged(self):
        self._upload(CSV_IE, 'income_expense')
        doc = Document.objects.filter(user=self.user).first()
        self.c.post(f'/document/{doc.pk}/delete/')
        self.assertTrue(AuditLog.objects.filter(user=self.user, action='delete').exists())

    # ── Panel settings ──
    def test_save_panels(self):
        doc = self._doc()
        cfg = {'income_expense': {'hidden': ['pie']}}
        r = self.c.post(f'/document/{doc.pk}/panels/',
                        data=json.dumps(cfg), content_type='application/json',
                        HTTP_HOST='localhost')
        self.assertEqual(r.status_code, 200)
        ps = PanelSettings.objects.get(user=self.user)
        self.assertEqual(ps.config['income_expense']['hidden'], ['pie'])

    # ── History & formats ──
    def test_history_200(self):
        r = self.c.get('/history/')
        self.assertEqual(r.status_code, 200)

    def test_formats_200(self):
        r = self.c.get('/formats/')
        self.assertEqual(r.status_code, 200)

    # ── All 4 doc types render detail ──
    def test_cash_flow_detail(self):
        self._upload(CSV_CF, 'cash_flow', 'cf.csv')
        doc = Document.objects.filter(user=self.user, doc_type='cash_flow', status='done').first()
        self.assertEqual(self.c.get(f'/document/{doc.pk}/').status_code, 200)

    def test_budget_detail(self):
        self._upload(CSV_BUDGET, 'budget', 'b.csv')
        doc = Document.objects.filter(user=self.user, doc_type='budget', status='done').first()
        self.assertEqual(self.c.get(f'/document/{doc.pk}/').status_code, 200)

    def test_kpi_detail(self):
        self._upload(CSV_KPI, 'kpi', 'k.csv')
        doc = Document.objects.filter(user=self.user, doc_type='kpi', status='done').first()
        self.assertEqual(self.c.get(f'/document/{doc.pk}/').status_code, 200)
