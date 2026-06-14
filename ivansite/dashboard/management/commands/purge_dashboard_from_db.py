"""
Management command: purge_dashboard_from_db
Removes all references to the old 'dashboard' app from the SQLite database:
  1. Drops old dashboard_* tables (they are duplicates; data lives in finassist_*)
  2. Removes django_migrations rows with app='dashboard'
  3. Removes django_content_type rows with app_label='dashboard'
     (and reassigns any auth_permission / django_admin_log rows that reference them)
Run once on PythonAnywhere after deploying the updated code.
"""

from django.core.management.base import BaseCommand
from django.db import connection


OLD_TABLES = [
    'dashboard_document',
    'dashboard_analysisresult',
    'dashboard_financialrecord',
    'dashboard_metric',
    'dashboard_auditlog',
    'dashboard_panelsettings',
]


class Command(BaseCommand):
    help = 'Удалить все упоминания dashboard из БД (таблицы, миграции, content types)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет сделано, без изменений',
        )

    def handle(self, *args, **options):
        dry = options['dry_run']
        prefix = '[DRY-RUN] ' if dry else ''

        with connection.cursor() as cur:
            # ── 1. Get existing tables ──────────────────────────────────────
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing = {r[0] for r in cur.fetchall()}

            # ── 2. Drop old dashboard_* tables ─────────────────────────────
            for table in OLD_TABLES:
                if table in existing:
                    self.stdout.write(f'{prefix}DROP TABLE {table}')
                    if not dry:
                        cur.execute(f'DROP TABLE IF EXISTS "{table}"')
                else:
                    self.stdout.write(self.style.WARNING(f'  (пропуск) {table} — не найдена'))

            # ── 3. Remove dashboard rows from django_migrations ─────────────
            cur.execute("SELECT id, app, name FROM django_migrations WHERE app = 'dashboard'")
            rows = cur.fetchall()
            if rows:
                for r in rows:
                    self.stdout.write(f"{prefix}DELETE django_migrations id={r[0]} app={r[1]} name={r[2]}")
                if not dry:
                    cur.execute("DELETE FROM django_migrations WHERE app = 'dashboard'")
            else:
                self.stdout.write(self.style.WARNING('  django_migrations: записей dashboard не найдено'))

            # ── 4. Remove dashboard content types (and cascaded refs) ───────
            cur.execute("SELECT id, app_label, model FROM django_content_type WHERE app_label = 'dashboard'")
            ct_rows = cur.fetchall()
            if ct_rows:
                ct_ids = [r[0] for r in ct_rows]
                ids_sql = ','.join(str(i) for i in ct_ids)
                for r in ct_rows:
                    self.stdout.write(f"{prefix}DELETE django_content_type id={r[0]} app={r[1]} model={r[2]}")

                # auth_permission rows referencing these content types
                cur.execute(f"SELECT COUNT(*) FROM auth_permission WHERE content_type_id IN ({ids_sql})")
                perm_count = cur.fetchone()[0]
                if perm_count:
                    self.stdout.write(f"{prefix}DELETE {perm_count} auth_permission rows (content_type dashboard)")
                    if not dry:
                        cur.execute(f"DELETE FROM auth_permission WHERE content_type_id IN ({ids_sql})")

                # django_admin_log rows referencing these content types
                cur.execute(f"SELECT COUNT(*) FROM django_admin_log WHERE content_type_id IN ({ids_sql})")
                log_count = cur.fetchone()[0]
                if log_count:
                    self.stdout.write(f"{prefix}DELETE {log_count} django_admin_log rows (content_type dashboard)")
                    if not dry:
                        cur.execute(f"DELETE FROM django_admin_log WHERE content_type_id IN ({ids_sql})")

                if not dry:
                    cur.execute(f"DELETE FROM django_content_type WHERE app_label = 'dashboard'")
            else:
                self.stdout.write(self.style.WARNING('  django_content_type: записей dashboard не найдено'))

        if dry:
            self.stdout.write(self.style.WARNING('\nDRY-RUN: изменения НЕ применены. Запустите без --dry-run для реального выполнения.'))
        else:
            self.stdout.write(self.style.SUCCESS('\nГотово! Все упоминания dashboard удалены из БД.'))
