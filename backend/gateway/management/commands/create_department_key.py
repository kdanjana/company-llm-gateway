"""Create a department (if it does not exist yet) and a new API key for it.

    python manage.py create_department_key Sales --key-name sales-bot --budget 50

The raw key is printed ONCE. Only its hash is stored, so it cannot be shown again.
(Department heads can also create keys in the dashboard.)
"""
import argparse
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand

from gateway.models import ApiKey, Department


def usd(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"'{value}' is not a number")
    if amount < 0:
        raise argparse.ArgumentTypeError("budget cannot be negative")
    return amount


class Command(BaseCommand):
    help = "Create a department (if new) and a new API key for it. The key is shown only once."

    def add_arguments(self, parser):
        parser.add_argument("department", help="Department name, e.g. Sales")
        parser.add_argument("--key-name", default="default", help="Which app will use the key, e.g. sales-bot")
        parser.add_argument("--budget", type=usd, default=None, help="Monthly budget in USD (sets or changes it)")

    def handle(self, *args, **options):
        department, created = Department.objects.get_or_create(name=options["department"])
        if options["budget"] is not None:
            department.monthly_budget_usd = options["budget"]
            department.save(update_fields=["monthly_budget_usd"])
        _, raw_key = ApiKey.issue(department, name=options["key_name"])

        budget = f"${department.monthly_budget_usd}/month" if department.monthly_budget_usd is not None else "no limit"
        self.stdout.write(f"Department: {department.name} ({'created' if created else 'already existed'}), budget: {budget}")
        self.stdout.write("API key (copy it now, it will not be shown again):")
        self.stdout.write(self.style.SUCCESS(raw_key))
