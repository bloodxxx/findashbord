import pandas as pd
import io
from decimal import Decimal, InvalidOperation
from datetime import date


REQUIRED_COLUMNS = {
    'income_expense': ['дата', 'статья', 'тип', 'сумма'],
    'cash_flow': ['дата', 'сумма', 'тип', 'контрагент'],
    'budget': ['период', 'подразделение', 'статья', 'план'],
    'kpi': ['период', 'подразделение', 'показатель', 'план', 'факт'],
}

COLUMN_ALIASES = {
    'дата': ['дата', 'date', 'дата платежа', 'дата операции'],
    'статья': ['статья', 'article', 'категория', 'category', 'наименование'],
    'тип': ['тип', 'type', 'тип операции', 'вид операции', 'вид'],
    'сумма': ['сумма', 'amount', 'sum', 'итого', 'значение'],
    'контрагент': ['контрагент', 'counterparty', 'получатель', 'отправитель', 'контрагент/назначение'],
    'период': ['период', 'period', 'месяц', 'квартал', 'год'],
    'подразделение': ['подразделение', 'department', 'отдел', 'dept'],
    'план': ['план', 'plan', 'плановое значение', 'бюджет'],
    'факт': ['факт', 'fact', 'фактическое значение', 'фактически'],
    'показатель': ['показатель', 'indicator', 'kpi', 'метрика', 'наименование kpi'],
}


def normalize_column_name(col):
    # нормализация имени колонки к нижнему регистру
    return str(col).strip().lower()


def find_column(df_columns, aliases):
    # поиск колонки по списку допустимых псевдонимов
    normalized = [normalize_column_name(c) for c in df_columns]
    for alias in aliases:
        if alias.lower() in normalized:
            idx = normalized.index(alias.lower())
            return df_columns[idx]
    return None


def map_columns(df, doc_type):
    # сопоставление колонок файла с ожидаемыми полями
    mapping = {}
    for key, aliases in COLUMN_ALIASES.items():
        col = find_column(df.columns.tolist(), aliases)
        if col:
            mapping[key] = col
    return mapping


def parse_amount(val):
    # парсинг суммы с очисткой форматирования
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return Decimal('0')
    try:
        cleaned = str(val).replace(' ', '').replace('\xa0', '').replace(',', '.').replace('₽', '')
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal('0')


def parse_date(val):
    # парсинг даты из строкового значения
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, date):
        return val
    try:
        return pd.to_datetime(str(val), dayfirst=True).date()
    except Exception:
        return None


def load_dataframe(file_obj, file_name):
    # загрузка файла в датафрейм по расширению
    name = file_name.lower()
    if name.endswith('.xlsx') or name.endswith('.xls'):
        df = pd.read_excel(file_obj, dtype=str)
    elif name.endswith('.csv'):
        raw = file_obj.read()
        for enc in ('utf-8', 'cp1251', 'latin-1'):
            try:
                df = pd.read_csv(io.StringIO(raw.decode(enc)), dtype=str)
                break
            except Exception:
                continue
        else:
            raise ValueError("Не удалось прочитать CSV файл")
    elif name.endswith('.xml'):
        df = pd.read_xml(file_obj)
        df = df.astype(str)
    else:
        raise ValueError("Неподдерживаемый формат файла")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how='all')
    return df


def validate(df, doc_type):
    # проверка наличия обязательных колонок
    if df.empty:
        raise ValueError("Файл пустой или не содержит данных")
    required = REQUIRED_COLUMNS.get(doc_type, [])
    mapping = map_columns(df, doc_type)
    missing = [r for r in required if r not in mapping]
    if missing:
        raise ValueError(f"Отсутствуют обязательные колонки: {', '.join(missing)}")
    return mapping


def parse_income_expense(df, mapping):
    # парсинг строк отчёта о доходах и расходах
    records = []
    for _, row in df.iterrows():
        raw_type = str(row.get(mapping.get('тип', ''), '')).strip().lower()
        record_type = 'income' if any(w in raw_type for w in ['доход', 'приход', 'income', '+']) else 'expense'
        records.append({
            'date': parse_date(row.get(mapping.get('дата', ''), None)),
            'category': str(row.get(mapping.get('статья', ''), '')).strip(),
            'amount': parse_amount(row.get(mapping.get('сумма', ''), 0)),
            'record_type': record_type,
        })
    return records


def parse_cash_flow(df, mapping):
    # парсинг строк отчёта о движении денежных средств
    records = []
    for _, row in df.iterrows():
        raw_type = str(row.get(mapping.get('тип', ''), '')).strip().lower()
        record_type = 'inflow' if any(w in raw_type for w in ['поступ', 'приход', 'inflow', '+', 'зачисл']) else 'outflow'
        records.append({
            'date': parse_date(row.get(mapping.get('дата', ''), None)),
            'amount': parse_amount(row.get(mapping.get('сумма', ''), 0)),
            'record_type': record_type,
            'counterparty': str(row.get(mapping.get('контрагент', ''), '')).strip(),
        })
    return records


def parse_budget(df, mapping):
    # парсинг строк бюджета
    records = []
    for _, row in df.iterrows():
        records.append({
            'period': str(row.get(mapping.get('период', ''), '')).strip(),
            'department': str(row.get(mapping.get('подразделение', ''), '')).strip(),
            'category': str(row.get(mapping.get('статья', ''), '')).strip(),
            'plan_value': parse_amount(row.get(mapping.get('план', ''), 0)),
            'fact_value': parse_amount(row.get(mapping.get('факт', ''), None)) if mapping.get('факт') else None,
        })
    return records


def parse_kpi(df, mapping):
    # парсинг строк KPI
    records = []
    for _, row in df.iterrows():
        plan = parse_amount(row.get(mapping.get('план', ''), 0))
        fact = parse_amount(row.get(mapping.get('факт', ''), 0))
        records.append({
            'period': str(row.get(mapping.get('период', ''), '')).strip(),
            'department': str(row.get(mapping.get('подразделение', ''), '')).strip(),
            'indicator': str(row.get(mapping.get('показатель', ''), '')).strip(),
            'plan_value': plan,
            'fact_value': fact,
        })
    return records


def parse_document(file_obj, file_name, doc_type):
    # точка входа для парсинга документа по типу
    df = load_dataframe(file_obj, file_name)
    mapping = validate(df, doc_type)

    parsers = {
        'income_expense': parse_income_expense,
        'cash_flow': parse_cash_flow,
        'budget': parse_budget,
        'kpi': parse_kpi,
    }
    return parsers[doc_type](df, mapping)
