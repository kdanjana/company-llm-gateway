"""Dashboard API for the React app. Login: JWT. Roles: see accounts/permissions.py.

Read (admins and heads, limited to visible departments):
  GET /api/dashboard/summary/?month=YYYY-MM       spend vs budget per department + totals
  GET /api/dashboard/daily/?month=&department=    cost and requests per day
  GET /api/dashboard/models-usage/?month=&department=
  GET /api/dashboard/requests/?department=&status=&limit=&offset=
  GET /api/dashboard/alerts/?month=
  GET /api/dashboard/departments/   GET /api/dashboard/api-keys/   GET /api/dashboard/models/

Write:
  POST  /api/dashboard/api-keys/              {department, name} -> includes raw_key ONCE   (admin; head: own dept)
  POST  /api/dashboard/api-keys/<id>/revoke/                                                (admin; head: own dept)
  POST  /api/dashboard/departments/  PATCH /api/dashboard/departments/<id>/                 (admin only)
  POST  /api/dashboard/models/       PATCH /api/dashboard/models/<id>/                      (admin only)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin, IsAdminOrHead, visible_departments

from .budgets import month_range
from .dashboard_serializers import (
    ApiKeyCreateSerializer,
    ApiKeySerializer,
    BudgetAlertSerializer,
    DepartmentSerializer,
    ModelPriceSerializer,
    UsageLogSerializer,
)
from .models import ApiKey, BudgetAlert, ModelPrice, UsageLog

MONEY = DecimalField(max_digits=14, decimal_places=6)
ZERO_MONEY = Value(Decimal("0"), output_field=MONEY)
ZERO_INT = Value(0, output_field=IntegerField())


# ---------------------------------------------------------------- query helpers

def parse_month(request) -> tuple[datetime, datetime, str]:
    raw = request.query_params.get("month")
    try:
        if raw:
            year, month = (int(part) for part in raw.split("-"))
            start, end = month_range(year, month)
        else:
            start, end = month_range()
    except (ValueError, TypeError):
        raise ValidationError({"month": "Use the format YYYY-MM."})
    return start, end, f"{start:%Y-%m}"


def department_filter(request) -> int | None:
    raw = request.query_params.get("department")
    if not raw:
        return None
    if not raw.isdigit():
        raise ValidationError({"department": "Must be a department id."})
    return int(raw)


def visible_logs(request):
    """Usage logs of the departments this user may see (optionally one department)."""
    logs = UsageLog.objects.filter(department__in=visible_departments(request.user))
    department_id = department_filter(request)
    if department_id is not None:
        logs = logs.filter(department_id=department_id)
    return logs


def percent_used(spend: Decimal, budget: Decimal | None) -> float | None:
    if budget is None:
        return None
    if budget <= 0:
        return 100.0
    return round(float(spend / budget * 100), 1)


# ---------------------------------------------------------------- read-only statistics

class SummaryView(APIView):
    permission_classes = [IsAdminOrHead]

    def get(self, request):
        start, end, label = parse_month(request)
        in_month = Q(usage_logs__created_at__gte=start, usage_logs__created_at__lt=end)
        departments = (
            visible_departments(request.user)
            .annotate(
                spend=Coalesce(Sum("usage_logs__cost_usd", filter=in_month), ZERO_MONEY, output_field=MONEY),
                requests=Count("usage_logs", filter=in_month),
                errors=Count("usage_logs", filter=in_month & Q(usage_logs__status=UsageLog.Status.ERROR)),
                blocked=Count("usage_logs", filter=in_month & Q(usage_logs__status=UsageLog.Status.BLOCKED)),
                cached=Count("usage_logs", filter=in_month & Q(usage_logs__cached=True)),
                input_tokens=Coalesce(Sum("usage_logs__input_tokens", filter=in_month), ZERO_INT, output_field=IntegerField()),
                output_tokens=Coalesce(Sum("usage_logs__output_tokens", filter=in_month), ZERO_INT, output_field=IntegerField()),
                pii_masked=Coalesce(Sum("usage_logs__pii_masked_count", filter=in_month), ZERO_INT, output_field=IntegerField()),
            )
            .order_by("name")
        )

        rows = []
        for d in departments:
            rows.append(
                {
                    "id": d.id,
                    "name": d.name,
                    "is_active": d.is_active,
                    "monthly_budget_usd": str(d.monthly_budget_usd) if d.monthly_budget_usd is not None else None,
                    "spend_usd": str(d.spend.quantize(Decimal("0.000001"))),
                    "percent_used": percent_used(d.spend, d.monthly_budget_usd),
                    "requests": d.requests,
                    "errors": d.errors,
                    "blocked": d.blocked,
                    "cached": d.cached,
                    "input_tokens": d.input_tokens,
                    "output_tokens": d.output_tokens,
                    "pii_masked": d.pii_masked,
                }
            )

        totals = {
            "spend_usd": str(sum((Decimal(r["spend_usd"]) for r in rows), Decimal("0"))),
            **{key: sum(r[key] for r in rows) for key in ("requests", "errors", "blocked", "cached", "input_tokens", "output_tokens", "pii_masked")},
        }
        return Response({"month": label, "departments": rows, "totals": totals})


class DailyCostView(APIView):
    """Cost and requests per day of the month (days without traffic are included as zero)."""

    permission_classes = [IsAdminOrHead]

    def get(self, request):
        start, end, label = parse_month(request)
        rows = (
            visible_logs(request)
            .filter(created_at__gte=start, created_at__lt=end)
            .annotate(day=TruncDate("created_at", tzinfo=timezone.get_current_timezone()))
            .values("day")
            .annotate(cost=Sum("cost_usd"), requests=Count("id"))
            .order_by("day")
        )
        by_day = {row["day"]: row for row in rows}

        days, day = [], start.date()
        while day < end.date():
            row = by_day.get(day)
            days.append(
                {
                    "date": day.isoformat(),
                    "cost_usd": str(row["cost"] if row else Decimal("0")),
                    "requests": row["requests"] if row else 0,
                }
            )
            day += timedelta(days=1)
        return Response({"month": label, "days": days})


class ModelUsageView(APIView):
    permission_classes = [IsAdminOrHead]

    def get(self, request):
        start, end, label = parse_month(request)
        rows = (
            visible_logs(request)
            .filter(created_at__gte=start, created_at__lt=end)
            .values("model_id")
            .annotate(
                requests=Count("id"),
                errors=Count("id", filter=Q(status=UsageLog.Status.ERROR)),
                cached=Count("id", filter=Q(cached=True)),
                fallbacks=Count("id", filter=Q(fallback_used=True)),
                input_tokens=Sum("input_tokens"),
                output_tokens=Sum("output_tokens"),
                cost=Sum("cost_usd"),
                # Average answer time of real model calls only (cached answers take ~0 ms).
                avg_latency_ms=Avg("latency_ms", filter=Q(status=UsageLog.Status.OK, cached=False)),
            )
            .order_by("-cost")
        )
        models = [
            {
                "model_id": r["model_id"],
                "requests": r["requests"],
                "errors": r["errors"],
                "cached": r["cached"],
                "fallbacks": r["fallbacks"],
                "input_tokens": r["input_tokens"] or 0,
                "output_tokens": r["output_tokens"] or 0,
                "cost_usd": str(r["cost"] or Decimal("0")),
                "avg_latency_ms": round(r["avg_latency_ms"]) if r["avg_latency_ms"] is not None else None,
            }
            for r in rows
        ]
        return Response({"month": label, "models": models})


class RequestsPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 200


class RequestsView(ListAPIView):
    """Most recent requests first."""

    permission_classes = [IsAdminOrHead]
    serializer_class = UsageLogSerializer
    pagination_class = RequestsPagination

    def get_queryset(self):
        logs = visible_logs(self.request).select_related("department", "api_key").order_by("-created_at")
        status = self.request.query_params.get("status")
        if status:
            if status not in UsageLog.Status.values:
                raise ValidationError({"status": f"Use one of: {', '.join(UsageLog.Status.values)}."})
            logs = logs.filter(status=status)
        return logs


class AlertsView(APIView):
    permission_classes = [IsAdminOrHead]

    def get(self, request):
        start, _, label = parse_month(request)
        alerts = (
            BudgetAlert.objects.filter(department__in=visible_departments(request.user), month=start.date())
            .select_related("department")
            .order_by("-level", "department__name")
        )
        return Response({"month": label, "alerts": BudgetAlertSerializer(alerts, many=True).data})


# ---------------------------------------------------------------- data that can be changed

class DepartmentViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Heads see their own department; only admins create departments or change budgets."""

    serializer_class = DepartmentSerializer
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        return visible_departments(self.request.user).order_by("name")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update"):
            return [IsAdmin()]
        return [IsAdminOrHead()]


class ApiKeyViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Admins manage keys of any department; heads only their own."""

    serializer_class = ApiKeySerializer
    permission_classes = [IsAdminOrHead]

    def get_queryset(self):
        keys = ApiKey.objects.filter(department__in=visible_departments(self.request.user)).select_related("department")
        department_id = department_filter(self.request)
        if department_id is not None:
            keys = keys.filter(department_id=department_id)
        return keys.order_by("-created_at")

    def create(self, request):
        serializer = ApiKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        department = serializer.validated_data["department"]
        if not visible_departments(request.user).filter(pk=department.pk).exists():
            raise PermissionDenied("You can only create keys for your own department.")

        api_key, raw_key = ApiKey.issue(department, name=serializer.validated_data["name"])
        data = ApiKeySerializer(api_key).data
        data["raw_key"] = raw_key  # shown once; only the hash is stored
        return Response(data, status=201)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        api_key = self.get_object()  # 404 for keys of other departments (not in get_queryset)
        api_key.is_active = False
        api_key.save(update_fields=["is_active"])
        return Response(ApiKeySerializer(api_key).data)


class ModelPriceViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Everyone can see which models exist and what they cost; only admins change them."""

    serializer_class = ModelPriceSerializer
    queryset = ModelPrice.objects.order_by("model_id")
    http_method_names = ["get", "post", "patch"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update"):
            return [IsAdmin()]
        return [IsAdminOrHead()]
