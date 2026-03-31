# FinDashboard

Веб-приложение для анализа финансовых документов. Поддерживает загрузку отчётов в форматах Excel, CSV и XML с автоматическим анализом и визуализацией данных.

---

## Технологии

![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)
![Django](https://img.shields.io/badge/Django-6.0-green?logo=django)
![Pandas](https://img.shields.io/badge/Pandas-3.0-lightblue?logo=pandas)

---

## Установка и запуск

### 1. Установи Git

Скачай и установи Git для Windows:
👉 [Git-2.53.0.2-64-bit.exe](https://github.com/git-for-windows/git/releases/download/v2.53.0.windows.2/Git-2.53.0.2-64-bit.exe)

---

### 2. Установи Python

Скачай и установи Python 3.13:
👉 [python.org/downloads](https://www.python.org/downloads/latest/python3.13/)

> ⚠️ При установке обязательно отметь галочку **"Add Python to PATH"**

---

### 3. Клонируй репозиторий

Создай папку с английским названием, открой её в VS Code, затем открой терминал и выполни:

```bash
git clone https://github.com/bloodxxx/findashbord
```

---

### 4. Создай виртуальное окружение

```bash
py -m venv venv
```

---

### 5. Активируй виртуальное окружение

```bash
venv\Scripts\activate
```

После активации в начале строки терминала появится `(venv)`.

---

### 6. Перейди в папку проекта

```bash
cd ivansite
```

---

### 7. Установи зависимости

```bash
pip install -r requirements.txt
```

---

### 8. Запусти сервер

```bash
py manage.py runserver
```

Открой в браузере: [http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## Поддерживаемые форматы документов

| Тип документа | Расширения |
|---|---|
| Доходы и расходы | `.xlsx`, `.xls`, `.csv`, `.xml` |
| Движение денежных средств | `.xlsx`, `.xls`, `.csv`, `.xml` |
| Бюджет | `.xlsx`, `.xls`, `.csv`, `.xml` |
| KPI | `.xlsx`, `.xls`, `.csv`, `.xml` |
