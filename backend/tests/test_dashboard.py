"""Dashboard API: login, roles, and that a department head only ever sees their own department."""
from decimal import Decimal

from django.contrib.auth import get_user_model

from gateway.models import ApiKey, Department, ModelPrice, UsageLog

from .conftest import MODEL, make_user

BASE = "/api/dashboard"


def log_for(department, cost="1.00"):
    return UsageLog.objects.create(department=department, model_id=MODEL, status="ok", cost_usd=Decimal(cost))


# ---------- login ----------

def test_head_can_log_in_and_see_who_they_are(api, sales_head):
    response = api.post("/api/auth/login/", {"username": "sales_head", "password": "a-long-test-password-1"}, format="json")
    assert response.status_code == 200
    access = response.data["access"]

    me = api.get("/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {access}")
    assert me.status_code == 200
    assert me.data == {"username": "sales_head", "role": "head", "department": {"id": sales_head.profile.department_id, "name": "Sales"}}


def test_user_without_profile_cannot_log_in(api, db):
    get_user_model().objects.create_user(username="plain", password="a-long-test-password-1")
    response = api.post("/api/auth/login/", {"username": "plain", "password": "a-long-test-password-1"}, format="json")
    assert response.status_code == 401


def test_wrong_password_is_401(api, sales_head):
    response = api.post("/api/auth/login/", {"username": "sales_head", "password": "wrong"}, format="json")
    assert response.status_code == 401


def test_dashboard_needs_login(api, db):
    assert api.get(f"{BASE}/summary/").status_code == 401


# ---------- what each role can see ----------

def test_head_sees_only_own_department_in_summary(api, sales_head, department, other_department):
    log_for(department, "2.00")
    log_for(other_department, "9.00")
    api.force_authenticate(sales_head)

    data = api.get(f"{BASE}/summary/").data

    assert [d["name"] for d in data["departments"]] == ["Sales"]
    assert data["totals"]["spend_usd"] == "2.000000"


def test_admin_sees_all_departments(api, gw_admin, department, other_department):
    log_for(department, "2.00")
    log_for(other_department, "9.00")
    api.force_authenticate(gw_admin)

    data = api.get(f"{BASE}/summary/").data

    assert [d["name"] for d in data["departments"]] == ["HR", "Sales"]
    assert Decimal(data["totals"]["spend_usd"]) == Decimal("11")


def test_summary_shows_percent_of_budget(api, sales_head, department):
    department.monthly_budget_usd = Decimal("10.00")
    department.save()
    log_for(department, "8.00")
    api.force_authenticate(sales_head)

    row = api.get(f"{BASE}/summary/").data["departments"][0]
    assert row["percent_used"] == 80.0


def test_head_cannot_read_other_departments_requests(api, sales_head, department, other_department):
    log_for(department)
    log_for(other_department)
    api.force_authenticate(sales_head)

    rows = api.get(f"{BASE}/requests/").data["results"]
    assert {r["department"] for r in rows} == {"Sales"}
    # asking for the other department by id returns nothing, not its data
    assert api.get(f"{BASE}/requests/?department={other_department.id}").data["results"] == []


def test_daily_lists_every_day_of_the_month(api, gw_admin):
    api.force_authenticate(gw_admin)
    data = api.get(f"{BASE}/daily/?month=2026-02").data
    assert len(data["days"]) == 28
    assert data["days"][0] == {"date": "2026-02-01", "cost_usd": "0", "requests": 0}


def test_bad_month_is_400(api, gw_admin):
    api.force_authenticate(gw_admin)
    assert api.get(f"{BASE}/summary/?month=2026-13").status_code == 400


# ---------- budgets: admin only ----------

def test_head_cannot_change_budget(api, sales_head, department):
    api.force_authenticate(sales_head)
    response = api.patch(f"{BASE}/departments/{department.id}/", {"monthly_budget_usd": "999"}, format="json")
    assert response.status_code == 403


def test_admin_can_change_budget(api, gw_admin, department):
    api.force_authenticate(gw_admin)
    response = api.patch(f"{BASE}/departments/{department.id}/", {"monthly_budget_usd": "50.00"}, format="json")
    assert response.status_code == 200
    department.refresh_from_db()
    assert department.monthly_budget_usd == Decimal("50.00")


def test_admin_can_create_department(api, gw_admin):
    api.force_authenticate(gw_admin)
    response = api.post(f"{BASE}/departments/", {"name": "Support", "monthly_budget_usd": "20"}, format="json")
    assert response.status_code == 201
    assert Department.objects.filter(name="Support").exists()


def test_negative_budget_is_refused(api, gw_admin, department):
    api.force_authenticate(gw_admin)
    response = api.patch(f"{BASE}/departments/{department.id}/", {"monthly_budget_usd": "-1"}, format="json")
    assert response.status_code == 400


# ---------- API keys ----------

def test_head_can_create_key_for_own_department(api, sales_head, department):
    api.force_authenticate(sales_head)
    response = api.post(f"{BASE}/api-keys/", {"department": department.id, "name": "crm-bot"}, format="json")

    assert response.status_code == 201
    assert response.data["raw_key"].startswith("gw_")
    assert response.data["department"] == "Sales"


def test_head_cannot_create_key_for_other_department(api, sales_head, other_department):
    api.force_authenticate(sales_head)
    response = api.post(f"{BASE}/api-keys/", {"department": other_department.id, "name": "x"}, format="json")
    assert response.status_code == 403
    assert not ApiKey.objects.filter(department=other_department).exists()


def test_raw_key_is_not_in_the_key_list(api, sales_head, raw_key):
    api.force_authenticate(sales_head)
    rows = api.get(f"{BASE}/api-keys/").data
    assert len(rows) == 1
    assert "raw_key" not in rows[0]


def test_head_can_revoke_own_key_but_not_others(api, sales_head, raw_key, other_raw_key, other_department):
    api.force_authenticate(sales_head)
    own = ApiKey.objects.get(department__name="Sales")
    other = ApiKey.objects.get(department=other_department)

    assert api.post(f"{BASE}/api-keys/{own.id}/revoke/").status_code == 200
    own.refresh_from_db()
    assert own.is_active is False

    assert api.post(f"{BASE}/api-keys/{other.id}/revoke/").status_code == 404
    other.refresh_from_db()
    assert other.is_active is True


# ---------- models and prices ----------

def test_head_can_view_models_but_not_change_them(api, sales_head, price):
    api.force_authenticate(sales_head)
    assert api.get(f"{BASE}/models/").status_code == 200
    response = api.patch(f"{BASE}/models/{price.id}/", {"input_price_per_1k": "0"}, format="json")
    assert response.status_code == 403


def test_admin_can_add_model_with_fallback(api, gw_admin, price):
    api.force_authenticate(gw_admin)
    response = api.post(
        f"{BASE}/models/",
        {"model_id": "new-model", "input_price_per_1k": "0.003", "output_price_per_1k": "0.015", "fallback_model_id": MODEL},
        format="json",
    )
    assert response.status_code == 201
    assert ModelPrice.objects.get(model_id="new-model").fallback_model_id == MODEL


def test_fallback_must_be_a_known_model(api, gw_admin, price):
    api.force_authenticate(gw_admin)
    response = api.patch(f"{BASE}/models/{price.id}/", {"fallback_model_id": "unknown"}, format="json")
    assert response.status_code == 400


def test_model_cannot_fall_back_to_itself(api, gw_admin, price):
    api.force_authenticate(gw_admin)
    response = api.patch(f"{BASE}/models/{price.id}/", {"fallback_model_id": MODEL}, format="json")
    assert response.status_code == 400


def test_head_without_profile_department_constraint(db, department):
    """A head must have a department (database constraint)."""
    import pytest
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        make_user("broken", "head", None)
