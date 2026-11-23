"""Django admin pages (http://localhost:8000/admin), for developers. Department heads use the React dashboard."""
from django.contrib import admin

from .models import ApiKey, BudgetAlert, Department, ModelPrice, UsageLog


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name", "monthly_budget_usd", "is_active", "created_at"]


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ["prefix", "department", "name", "is_active", "last_used_at"]
    list_filter = ["department", "is_active"]
    readonly_fields = ["prefix", "key_hash", "created_at", "last_used_at"]

    def has_add_permission(self, request):
        # New keys come from the dashboard or `create_department_key`, which show the raw key once.
        return False


@admin.register(ModelPrice)
class ModelPriceAdmin(admin.ModelAdmin):
    list_display = ["model_id", "input_price_per_1k", "output_price_per_1k", "fallback_model_id", "is_enabled", "updated_at"]


class ReadOnlyAdmin(admin.ModelAdmin):
    """Logs and alerts are a record of what happened: read-only."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(UsageLog)
class UsageLogAdmin(ReadOnlyAdmin):
    list_display = [
        "created_at", "department", "model_id", "served_model_id", "status",
        "input_tokens", "output_tokens", "cost_usd", "latency_ms", "cached", "pii_masked_count",
    ]
    list_filter = ["department", "status", "model_id", "cached", "streamed", "fallback_used"]


@admin.register(BudgetAlert)
class BudgetAlertAdmin(ReadOnlyAdmin):
    list_display = ["created_at", "department", "month", "level", "spend_usd", "budget_usd"]
    list_filter = ["department", "level"]
