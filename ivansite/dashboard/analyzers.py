from decimal import Decimal
from collections import defaultdict
from .models import FinancialRecord, AnalysisResult, Metric


def analyze_document(document):
    # маршрутизация анализа по типу документа
    records = document.records.all()
    doc_type = document.doc_type

    if doc_type == 'income_expense':
        return _analyze_income_expense(document, records)
    elif doc_type == 'cash_flow':
        return _analyze_cash_flow(document, records)
    elif doc_type == 'budget':
        return _analyze_budget(document, records)
    elif doc_type == 'kpi':
        return _analyze_kpi(document, records)


def _analyze_income_expense(document, records):
    # анализ доходов и расходов
    total_income = Decimal('0')
    total_expense = Decimal('0')
    by_category = defaultdict(Decimal)
    by_date = defaultdict(lambda: {'income': Decimal('0'), 'expense': Decimal('0')})

    for r in records:
        if r.record_type == 'income':
            total_income += r.amount
        else:
            total_expense += r.amount
            by_category[r.category or 'Прочее'] += r.amount
        date_key = str(r.date) if r.date else 'N/A'
        by_date[date_key][r.record_type if r.record_type in ('income', 'expense') else 'expense'] += r.amount

    profit = total_income - total_expense

    sorted_dates = sorted(by_date.keys())
    chart_data = {
        'line': {
            'labels': sorted_dates,
            'income': [float(by_date[d]['income']) for d in sorted_dates],
            'expense': [float(by_date[d]['expense']) for d in sorted_dates],
        },
        'pie': {
            'labels': list(by_category.keys()),
            'values': [float(v) for v in by_category.values()],
        },
    }

    result, _ = AnalysisResult.objects.update_or_create(
        document=document,
        defaults={
            'total_income': total_income,
            'total_expense': total_expense,
            'profit': profit,
            'chart_data': chart_data,
        }
    )
    Metric.objects.filter(document=document).delete()
    Metric.objects.create(document=document, metric_name='Общие доходы', value=total_income)
    Metric.objects.create(document=document, metric_name='Общие расходы', value=total_expense)
    Metric.objects.create(document=document, metric_name='Прибыль', value=profit)
    return result


def _analyze_cash_flow(document, records):
    # анализ движения денежных средств
    total_inflow = Decimal('0')
    total_outflow = Decimal('0')
    by_date = defaultdict(lambda: {'inflow': Decimal('0'), 'outflow': Decimal('0')})

    for r in records:
        if r.record_type == 'inflow':
            total_inflow += r.amount
        else:
            total_outflow += r.amount
        date_key = str(r.date) if r.date else 'N/A'
        by_date[date_key][r.record_type if r.record_type in ('inflow', 'outflow') else 'outflow'] += r.amount

    balance = total_inflow - total_outflow
    sorted_dates = sorted(by_date.keys())
    cumulative = Decimal('0')
    cumulative_list = []
    for d in sorted_dates:
        cumulative += by_date[d]['inflow'] - by_date[d]['outflow']
        cumulative_list.append(float(cumulative))

    chart_data = {
        'bar': {
            'labels': sorted_dates,
            'inflow': [float(by_date[d]['inflow']) for d in sorted_dates],
            'outflow': [float(by_date[d]['outflow']) for d in sorted_dates],
        },
        'balance_line': {
            'labels': sorted_dates,
            'values': cumulative_list,
        },
    }

    result, _ = AnalysisResult.objects.update_or_create(
        document=document,
        defaults={
            'total_inflow': total_inflow,
            'total_outflow': total_outflow,
            'balance': balance,
            'net_flow': balance,
            'chart_data': chart_data,
        }
    )
    Metric.objects.filter(document=document).delete()
    Metric.objects.create(document=document, metric_name='Поступления', value=total_inflow)
    Metric.objects.create(document=document, metric_name='Списания', value=total_outflow)
    Metric.objects.create(document=document, metric_name='Остаток', value=balance)
    Metric.objects.create(document=document, metric_name='Чистый поток', value=balance)
    return result


def _analyze_budget(document, records):
    # анализ бюджета план факт
    categories = []
    plan_vals = []
    fact_vals = []
    deviations = []
    pct_list = []

    by_cat = defaultdict(lambda: {'plan': Decimal('0'), 'fact': Decimal('0')})
    for r in records:
        key = r.category or r.department or 'Прочее'
        by_cat[key]['plan'] += r.plan_value or Decimal('0')
        by_cat[key]['fact'] += r.fact_value or Decimal('0')

    total_plan = Decimal('0')
    total_fact = Decimal('0')

    for cat, vals in by_cat.items():
        p = vals['plan']
        f = vals['fact']
        dev = f - p
        pct = float(f / p * 100) if p else 0
        categories.append(cat)
        plan_vals.append(float(p))
        fact_vals.append(float(f))
        deviations.append(float(dev))
        pct_list.append(round(pct, 1))
        total_plan += p
        total_fact += f

    overall_pct = float(total_fact / total_plan * 100) if total_plan else 0

    chart_data = {
        'plan_fact': {
            'labels': categories,
            'plan': plan_vals,
            'fact': fact_vals,
        },
        'deviation': {
            'labels': categories,
            'values': deviations,
        },
        'categories': categories,
        'pct_list': pct_list,
    }

    result, _ = AnalysisResult.objects.update_or_create(
        document=document,
        defaults={
            'total_income': total_plan,
            'total_expense': total_fact,
            'profit': total_fact - total_plan,
            'chart_data': chart_data,
        }
    )
    Metric.objects.filter(document=document).delete()
    Metric.objects.create(document=document, metric_name='Общий план', value=total_plan)
    Metric.objects.create(document=document, metric_name='Общий факт', value=total_fact)
    Metric.objects.create(document=document, metric_name='Отклонение', value=total_fact - total_plan)
    Metric.objects.create(document=document, metric_name='% выполнения', value=round(overall_pct, 2))
    return result


def _analyze_kpi(document, records):
    # анализ показателей KPI
    indicators = []
    plan_vals = []
    fact_vals = []
    statuses = []
    pct_list = []

    for r in records:
        plan = r.plan_value or Decimal('0')
        fact = r.fact_value or Decimal('0')
        pct = float(fact / plan * 100) if plan else 0
        status = 'success' if pct >= 100 else ('warning' if pct >= 80 else 'danger')
        indicators.append(r.indicator or r.category or 'N/A')
        plan_vals.append(float(plan))
        fact_vals.append(float(fact))
        statuses.append(status)
        pct_list.append(round(pct, 1))

    chart_data = {
        'kpi_bar': {
            'labels': indicators,
            'plan': plan_vals,
            'fact': fact_vals,
        },
        'statuses': statuses,
        'pct_list': pct_list,
        'indicators': indicators,
    }

    done_count = sum(1 for s in statuses if s == 'success')
    total_count = len(statuses)

    result, _ = AnalysisResult.objects.update_or_create(
        document=document,
        defaults={
            'chart_data': chart_data,
        }
    )
    Metric.objects.filter(document=document).delete()
    Metric.objects.create(document=document, metric_name='Показателей выполнено', value=done_count)
    Metric.objects.create(document=document, metric_name='Всего показателей', value=total_count)
    if total_count:
        Metric.objects.create(document=document, metric_name='% выполненных KPI', value=round(done_count / total_count * 100, 2))
    return result
