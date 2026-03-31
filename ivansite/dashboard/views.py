import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
import csv

from .models import Document, FinancialRecord, AnalysisResult, Metric
from .parsers import parse_document
from .analyzers import analyze_document


ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv', 'xml'}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def login_view(request):
    # авторизация пользователя
    if request.user.is_authenticated:
        return redirect('dashboard:upload')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard:upload')
        messages.error(request, 'Неверный логин или пароль')
    return render(request, 'dashboard/login.html')


def register_view(request):
    # регистрация нового пользователя
    if request.user.is_authenticated:
        return redirect('dashboard:upload')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        if not username or not password:
            messages.error(request, 'Заполните все поля')
        elif password != password2:
            messages.error(request, 'Пароли не совпадают')
        elif len(password) < 6:
            messages.error(request, 'Пароль слишком короткий (минимум 6 символов)')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Пользователь с таким именем уже существует')
        else:
            User.objects.create_user(username=username, password=password)
            messages.success(request, 'Аккаунт создан. Войдите в систему.')
            return redirect('dashboard:login')
    return render(request, 'dashboard/register.html')


def logout_view(request):
    # выход из системы
    logout(request)
    return redirect('dashboard:login')


@login_required
def upload_view(request):
    # загрузка и обработка документа
    if request.method == 'POST':
        file = request.FILES.get('file')
        doc_type = request.POST.get('doc_type', '')
        period = request.POST.get('period', '')

        if not file:
            messages.error(request, 'Выберите файл')
            return redirect('dashboard:upload')

        ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''
        if ext not in ALLOWED_EXTENSIONS:
            messages.error(request, f'Неподдерживаемый формат. Допустимые: {", ".join(ALLOWED_EXTENSIONS)}')
            return redirect('dashboard:upload')

        if file.size > MAX_FILE_SIZE:
            messages.error(request, 'Файл слишком большой (максимум 20 МБ)')
            return redirect('dashboard:upload')

        if doc_type not in dict(Document.DOCUMENT_TYPES):
            messages.error(request, 'Выберите тип документа')
            return redirect('dashboard:upload')

        document = Document.objects.create(
            user=request.user,
            file=file,
            file_name=file.name,
            doc_type=doc_type,
            period=period,
            status=Document.STATUS_VALIDATING,
        )

        try:
            document.file.seek(0)
            records_data = parse_document(document.file, document.file_name, doc_type)

            document.status = Document.STATUS_ANALYZING
            document.save()

            FinancialRecord.objects.filter(document=document).delete()
            for rd in records_data:
                FinancialRecord.objects.create(
                    document=document,
                    date=rd.get('date'),
                    category=rd.get('category', ''),
                    amount=rd.get('amount', 0),
                    record_type=rd.get('record_type', ''),
                    counterparty=rd.get('counterparty', ''),
                    department=rd.get('department', ''),
                    indicator=rd.get('indicator', ''),
                    plan_value=rd.get('plan_value'),
                    fact_value=rd.get('fact_value'),
                    period=rd.get('period', ''),
                )

            analyze_document(document)
            document.status = Document.STATUS_DONE
            document.save()
            messages.success(request, f'Документ «{document.file_name}» успешно проанализирован')
            return redirect('dashboard:document_detail', pk=document.pk)

        except ValueError as e:
            document.status = Document.STATUS_ERROR
            document.error_message = str(e)
            document.save()
            messages.error(request, f'Ошибка: {e}')
            return redirect('dashboard:upload')
        except Exception as e:
            document.status = Document.STATUS_ERROR
            document.error_message = str(e)
            document.save()
            messages.error(request, 'Произошла ошибка при обработке файла')
            return redirect('dashboard:upload')

    recent_docs = Document.objects.filter(user=request.user)[:5]
    return render(request, 'dashboard/upload.html', {
        'document_types': Document.DOCUMENT_TYPES,
        'recent_docs': recent_docs,
    })


@login_required
def history_view(request):
    # история загруженных документов с фильтрацией и пагинацией
    docs_qs = Document.objects.filter(user=request.user)

    doc_type_filter = request.GET.get('doc_type', '')
    status_filter = request.GET.get('status', '')
    period_filter = request.GET.get('period', '')

    if doc_type_filter:
        docs_qs = docs_qs.filter(doc_type=doc_type_filter)
    if status_filter:
        docs_qs = docs_qs.filter(status=status_filter)
    if period_filter:
        docs_qs = docs_qs.filter(period__icontains=period_filter)

    paginator = Paginator(docs_qs, 10)
    page = request.GET.get('page', 1)
    documents = paginator.get_page(page)

    return render(request, 'dashboard/history.html', {
        'documents': documents,
        'document_types': Document.DOCUMENT_TYPES,
        'statuses': Document.STATUSES,
        'current_filters': {
            'doc_type': doc_type_filter,
            'status': status_filter,
            'period': period_filter,
        },
    })


@login_required
def document_detail(request, pk):
    # детальный просмотр документа и результатов анализа
    document = get_object_or_404(Document, pk=pk, user=request.user)
    analysis = getattr(document, 'analysis', None)
    metrics = document.metrics.all()
    records = document.records.all()[:100]

    chart_data_json = json.dumps(analysis.chart_data if analysis else {})

    return render(request, 'dashboard/document_detail.html', {
        'document': document,
        'analysis': analysis,
        'metrics': metrics,
        'records': records,
        'chart_data_json': chart_data_json,
    })


@login_required
def delete_document(request, pk):
    # удаление документа пользователя
    document = get_object_or_404(Document, pk=pk, user=request.user)
    if request.method == 'POST':
        document.delete()
        messages.success(request, 'Документ удалён')
    return redirect('dashboard:history')


@login_required
def export_csv(request, pk):
    # экспорт записей документа в CSV файл
    document = get_object_or_404(Document, pk=pk, user=request.user)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="report_{document.pk}.csv"'
    response.write('\ufeff')

    writer = csv.writer(response)

    if document.doc_type == 'income_expense':
        writer.writerow(['Дата', 'Статья', 'Тип', 'Сумма'])
        for r in document.records.all():
            writer.writerow([r.date, r.category, r.record_type, r.amount])
    elif document.doc_type == 'cash_flow':
        writer.writerow(['Дата', 'Тип', 'Контрагент', 'Сумма'])
        for r in document.records.all():
            writer.writerow([r.date, r.record_type, r.counterparty, r.amount])
    elif document.doc_type == 'budget':
        writer.writerow(['Период', 'Подразделение', 'Статья', 'План', 'Факт', 'Отклонение'])
        for r in document.records.all():
            dev = (r.fact_value or 0) - (r.plan_value or 0)
            writer.writerow([r.period, r.department, r.category, r.plan_value, r.fact_value, dev])
    elif document.doc_type == 'kpi':
        writer.writerow(['Период', 'Подразделение', 'Показатель', 'План', 'Факт', 'Отклонение'])
        for r in document.records.all():
            dev = (r.fact_value or 0) - (r.plan_value or 0)
            writer.writerow([r.period, r.department, r.indicator, r.plan_value, r.fact_value, dev])

    return response


@login_required
def formats_view(request):
    # страница с описанием поддерживаемых форматов
    return render(request, 'dashboard/formats.html')
