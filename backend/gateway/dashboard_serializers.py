"""Serializers for the dashboard API (JWT login, admins and department heads)."""
from rest_framework import serializers

from .models import ApiKey, BudgetAlert, Department, ModelPrice, UsageLog


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "monthly_budget_usd", "is_active", "created_at"]
        read_only_fields = ["created_at"]
        extra_kwargs = {"monthly_budget_usd": {"min_value": 0}}


class ApiKeySerializer(serializers.ModelSerializer):
    department = serializers.CharField(source="department.name", read_only=True)
    department_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ApiKey
        fields = ["id", "name", "prefix", "department", "department_id", "is_active", "created_at", "last_used_at"]
        read_only_fields = fields


class ApiKeyCreateSerializer(serializers.Serializer):
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.filter(is_active=True))
    name = serializers.CharField(max_length=100, default="default")


class ModelPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelPrice
        fields = ["id", "model_id", "input_price_per_1k", "output_price_per_1k", "fallback_model_id", "is_enabled", "updated_at"]
        read_only_fields = ["updated_at"]
        extra_kwargs = {
            "input_price_per_1k": {"min_value": 0},
            "output_price_per_1k": {"min_value": 0},
        }

    def validate(self, attrs):
        model_id = attrs.get("model_id", getattr(self.instance, "model_id", None))
        fallback = attrs.get("fallback_model_id", getattr(self.instance, "fallback_model_id", ""))
        if fallback:
            if fallback == model_id:
                raise serializers.ValidationError({"fallback_model_id": "A model cannot be its own fallback."})
            if not ModelPrice.objects.filter(model_id=fallback).exists():
                raise serializers.ValidationError({"fallback_model_id": "Add this model with its price first."})
        return attrs


class UsageLogSerializer(serializers.ModelSerializer):
    department = serializers.CharField(source="department.name", read_only=True)
    api_key = serializers.SerializerMethodField()

    class Meta:
        model = UsageLog
        fields = [
            "id", "created_at", "department", "api_key", "model_id", "served_model_id", "status",
            "input_tokens", "output_tokens", "cost_usd", "latency_ms", "pii_masked_count",
            "cached", "streamed", "fallback_used", "error_code",
        ]
        read_only_fields = fields

    def get_api_key(self, log: UsageLog) -> str | None:
        return log.api_key.name if log.api_key else None


class BudgetAlertSerializer(serializers.ModelSerializer):
    department = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = BudgetAlert
        fields = ["id", "department", "month", "level", "spend_usd", "budget_usd", "created_at"]
        read_only_fields = fields
