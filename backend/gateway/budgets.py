"""Monthly budgets per department.

- Spend = sum of cost_usd in UsageLog for the current calendar month (time zone from settings.TIME_ZONE).
- Before a model call: spend >= budget  ->  the request is blocked.
- After a model call: alerts are recorded at GATEWAY_BUDGET_ALERT_PERCENT (default 80%) and at 100%.

Known limit: the cost of a request is only known after the model answers, so several requests running at
the same moment can push a department slightly over its budget. A stricter version would reserve an
estimated cost before the call (e.g. from max_tokens) and settle it afterwards.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from .models import BudgetAlert, Department, UsageLog


def month_range(year: int | None = None, month: int | None = None) -> tuple[datetime, datetime]:
    """Start (inclusive) and end (exclusive) of a calendar month in the local time zone.
    Raises ValueError for an impossible month."""
    now = timezone.localtime()
    year = year or now.year
    month = month or now.month
    tz = timezone.get_current_timezone()
    start = datetime(year, month, 1, tzinfo=tz)
    end = datetime(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1, tzinfo=tz)
    return start, end


def month_spend(department: Department, start: datetime, end: datetime) -> Decimal:
    total = UsageLog.objects.filter(
        department=department, created_at__gte=start, created_at__lt=end
    ).aggregate(total=Sum("cost_usd"))["total"]
    return total or Decimal("0")


@dataclass
class BudgetStatus:
    budget: Decimal | None
    spend: Decimal

    @property
    def percent(self) -> float | None:
        if self.budget is None:
            return None
        if self.budget <= 0:
            return 100.0
        return float(self.spend / self.budget * 100)

    @property
    def blocked(self) -> bool:
        return self.budget is not None and self.spend >= self.budget


def budget_status(department: Department) -> BudgetStatus:
    start, end = month_range()
    return BudgetStatus(budget=department.monthly_budget_usd, spend=month_spend(department, start, end))


def record_alerts(department: Department) -> None:
    """Creates the 80% / 100% alerts for this month if they are reached and do not exist yet."""
    status = budget_status(department)
    if status.percent is None:
        return
    start, _ = month_range()
    for level in (settings.GATEWAY_BUDGET_ALERT_PERCENT, 100):
        if status.percent >= level:
            BudgetAlert.objects.get_or_create(
                department=department,
                month=start.date(),
                level=level,
                defaults={"spend_usd": status.spend, "budget_usd": status.budget},
            )
