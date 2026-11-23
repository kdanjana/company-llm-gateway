"""Monthly budgets: block at 100%, alerts at 80% and 100%, only the current month counts."""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from gateway.models import BudgetAlert, UsageLog

from .conftest import MODEL, chat_body, post_chat


def spend(department, amount: str, days_ago: int = 0):
    log = UsageLog.objects.create(department=department, model_id=MODEL, status="ok", cost_usd=Decimal(amount))
    if days_ago:
        UsageLog.objects.filter(pk=log.pk).update(created_at=timezone.now() - timedelta(days=days_ago))


def test_no_budget_means_no_limit(api, raw_key, department, price, fake_bedrock):
    spend(department, "1000")
    assert post_chat(api, raw_key).status_code == 200


def test_request_is_blocked_when_budget_is_used_up(api, raw_key, department, price, fake_bedrock):
    department.monthly_budget_usd = Decimal("5.00")
    department.save()
    spend(department, "5.00")

    response = post_chat(api, raw_key)

    assert response.status_code == 403
    assert response.data["error"]["code"] == "budget_exceeded"
    assert fake_bedrock.calls == []  # the model was never called
    blocked = UsageLog.objects.get(status=UsageLog.Status.BLOCKED)
    assert blocked.error_code == "budget_exceeded"
    assert blocked.cost_usd == 0


def test_zero_budget_blocks_everything(api, raw_key, department, price, fake_bedrock):
    department.monthly_budget_usd = Decimal("0")
    department.save()
    assert post_chat(api, raw_key).status_code == 403


def test_spend_from_earlier_months_does_not_count(api, raw_key, department, price, fake_bedrock):
    department.monthly_budget_usd = Decimal("5.00")
    department.save()
    spend(department, "100", days_ago=40)  # always in an earlier month
    assert post_chat(api, raw_key).status_code == 200


def test_alerts_at_80_and_100_percent(api, raw_key, department, price, fake_bedrock):
    department.monthly_budget_usd = Decimal("1.00")
    department.save()
    # 800,000 input tokens * $0.001/1k = $0.80 per request
    fake_bedrock.input_tokens, fake_bedrock.output_tokens = 800_000, 0
    no_cache = chat_body(cache=False)  # otherwise the 2nd identical request would be a free cached answer

    post_chat(api, raw_key, no_cache)  # spend 0.80 -> 80%
    assert list(BudgetAlert.objects.values_list("level", flat=True)) == [80]

    post_chat(api, raw_key, no_cache)  # spend 1.60 -> 160%
    assert sorted(BudgetAlert.objects.values_list("level", flat=True)) == [80, 100]

    assert post_chat(api, raw_key, no_cache).status_code == 403  # now blocked
    assert BudgetAlert.objects.count() == 2  # no duplicate alerts


def test_other_departments_spend_does_not_count(api, raw_key, department, other_department, price, fake_bedrock):
    department.monthly_budget_usd = Decimal("5.00")
    department.save()
    spend(other_department, "100")
    assert post_chat(api, raw_key).status_code == 200
