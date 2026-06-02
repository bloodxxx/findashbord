from decimal import Decimal
from collections import defaultdict
from .models import FinancialRecord, AnalysisResult, Metric


GRANS = ['day', 'week', 'month', 'quarter']


def _period_key(d, gran):
    # ключ агрегации даты по гранулярности (день/неделя/месяц/квартал)
    if gran == 'week':
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"
    if gran == 'month':
        return f"{d.year}-{d.month:02d}"
    if gran == 'quarter':
        return f"{d.year}-Q{(d.month - 1) // 3 + 1}"
    return d.isoformat()


def _aggregate_by_gran(records, fields):
    # агрегация записей по всем гранулярностям; fields: {имя: функция(record)->Decimal}
    out = {}
    for gran in GRANS:
        buckets = defaultdict(lambda: {k: Decimal('0') for k in fields})
        for r in records:
            if not r.date:
                continue
            key = _period_key(r.date, gran)
            for name, fn in fields.items():
                buckets[key][name] += fn(r)
        labels = sorted(buckets.keys())
        series = {'labels': labels}
        for name in fields:
            series[name] = [float(buckets[l][name]) for l in labels]
        out[gran] = series
    return out


def _forecast(values, periods=1):
    # линейный прогноз тренда (метод наименьших квадратов) на следующие периоды
    n = len(values)
    if n < 2:
        return [values[-1] if values else 0.0] * periods
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    denom = sum((x - mean_x) ** 2 for x in xs) or 1
    slope = sum((xs[i] - mean_x) * (values[i] - mean_y) for i in range(n)) / denom
    intercept = mean_y - slope * mean_x
    return [round(slope * (n - 1 + k) + intercept, 2) for k in range(1, periods + 1)]


def _detect_period(document, records):
    # автоопределение дат начала и конца периода по данным
    dates = [r.date for r in records if r.date]
    if dates:
        document.period_start = min(dates)
        document.period_end = max(dates)
        document.save(update_fields=['period_start', 'period_end'])


def analyze_document(document):
    # маршрутизация анализа по типу документа
    records = list(document.records.all())
    _detect_period(document, records)
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
        'periods': _aggregate_by_gran(records, {
            'income': lambda r: r.amount if r.record_type == 'income' else Decimal('0'),
            'expense': lambda r: r.amount if r.record_type != 'income' else Decimal('0'),
        }),
    }
    # прогноз доходов на следующий период по месячному тренду
    monthly_income = chart_data['periods']['month']['income']
    chart_data['forecast'] = {
        'labels': chart_data['periods']['month']['labels'],
        'income': monthly_income,
        'next': _forecast(monthly_income, 3),
    }

    ratio = float(total_income / total_expense) if total_expense else 0

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
    Metric.objects.create(document=document, metric_name='Доход / Расход', value=round(ratio, 2))
    return result


def _analyze_cash_flow(document, records):
    # анализ движения денежных средств
    total_inflow = Decimal('0')
    total_outflow = Decimal('0')
    by_date = defaultdict(lambda: {'inflow': Decimal('0'), 'outflow': Decimal('0')})
    by_counterparty = defaultdict(Decimal)

    for r in records:
        if r.record_type == 'inflow':
            total_inflow += r.amount
        else:
            total_outflow += r.amount
        if r.counterparty:
            by_counterparty[r.counterparty] += r.amount
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
        'periods': _aggregate_by_gran(records, {
            'inflow': lambda r: r.amount if r.record_type == 'inflow' else Decimal('0'),
            'outflow': lambda r: r.amount if r.record_type != 'inflow' else Decimal('0'),
        }),
    }
    monthly_net = [i - o for i, o in zip(
        chart_data['periods']['month']['inflow'], chart_data['periods']['month']['outflow'])]
    chart_data['forecast'] = {
        'labels': chart_data['periods']['month']['labels'],
        'net': monthly_net,
        'next': _forecast(monthly_net, 3),
    }

    cp_count = len(by_counterparty)
    avg_per_cp = float(sum(by_counterparty.values()) / cp_count) if cp_count else 0

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
    Metric.objects.create(document=document, metric_name='Средний оборот на контрагента', value=round(avg_per_cp, 2))
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
