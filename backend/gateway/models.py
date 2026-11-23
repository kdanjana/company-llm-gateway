"""Database tables of the gateway.

Department  - a team that uses AI (Sales, HR, Support...), with an optional monthly budget.
ApiKey      - the secret a department's app sends with every request. Only a hash is stored.
ModelPrice  - which models the gateway allows, what they cost, and which model to fall back to.
              A model without a row is refused, so the gateway never runs a request it cannot price.
UsageLog    - one row per request: who, which model, tokens, cost, time, status.
              The prompt and the answer are NOT stored (privacy: they may contain personal data).
BudgetAlert - "department X reached 80% / 100% of its budget this month" (one row per level per month).
"""
from __future__ import annotations

import hashlib
import secrets
from decimal import Decimal

from django.db import models

KEY_PREFIX = "gw_"


def hash_key(raw_key: str) -> str:
    """SHA-256 of the key. Enough here because keys are long random strings (not passwords people choose),
    so they cannot be guessed from the hash. Fast hashing also keeps every request quick."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    monthly_budget_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Monthly limit in USD. Empty = no limit. At 100% the department's requests are blocked.",
    )
    is_active = models.BooleanField(default=True, help_text="Inactive departments cannot call the gateway.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ApiKey(models.Model):
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="api_keys")
    name = models.CharField(max_length=100, default="default", help_text="Which app uses this key, e.g. 'sales-bot'.")
    prefix = models.CharField(max_length=12, help_text="First characters of the key, to recognise it in lists.")
    key_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.department} / {self.name} ({self.prefix}...)"

    @classmethod
    def issue(cls, department: Department, name: str = "default") -> tuple["ApiKey", str]:
        """Create a new key. Returns (row, raw key). The raw key is shown once and never stored."""
        raw_key = KEY_PREFIX + secrets.token_urlsafe(32)
        api_key = cls.objects.create(department=department, name=name, prefix=raw_key[:10], key_hash=hash_key(raw_key))
        return api_key, raw_key


class ModelPrice(models.Model):
    model_id = models.CharField(max_length=200, unique=True, help_text="Bedrock model ID or inference profile ID.")
    input_price_per_1k = models.DecimalField(max_digits=12, decimal_places=6, help_text="USD per 1,000 input tokens.")
    output_price_per_1k = models.DecimalField(max_digits=12, decimal_places=6, help_text="USD per 1,000 output tokens.")
    fallback_model_id = models.CharField(
        max_length=200,
        blank=True,
        help_text="If this model is rate-limited or unavailable, retry once on this model (it needs its own price row).",
    )
    is_enabled = models.BooleanField(default=True, help_text="Disabled models are refused by the gateway.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["model_id"]

    def __str__(self) -> str:
        return self.model_id

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        """Cost in USD, rounded to 6 decimals. Decimal (not float) so money adds up exactly."""
        total = (Decimal(input_tokens) * self.input_price_per_1k + Decimal(output_tokens) * self.output_price_per_1k) / 1000
        return total.quantize(Decimal("0.000001"))


class UsageLog(models.Model):
    class Status(models.TextChoices):
        OK = "ok", "OK"
        ERROR = "error", "Error"
        BLOCKED = "blocked", "Blocked (budget)"

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="usage_logs")
    api_key = models.ForeignKey(ApiKey, on_delete=models.SET_NULL, null=True, blank=True, related_name="usage_logs")
    model_id = models.CharField(max_length=200, help_text="The model the app asked for.")
    served_model_id = models.CharField(max_length=200, blank=True, help_text="The model that answered (differs after a fallback).")
    status = models.CharField(max_length=10, choices=Status.choices)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal("0"))
    latency_ms = models.PositiveIntegerField(default=0, help_text="Time the model took to answer.")
    pii_masked_count = models.PositiveIntegerField(default=0, help_text="How many personal-data items were masked.")
    cached = models.BooleanField(default=False, help_text="Answered from the cache (no model call, no cost).")
    streamed = models.BooleanField(default=False)
    fallback_used = models.BooleanField(default=False)
    error_code = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        # Dashboard and budget queries filter by department and date range.
        indexes = [models.Index(fields=["department", "created_at"])]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.department} {self.model_id} {self.status}"


class BudgetAlert(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="budget_alerts")
    month = models.DateField(help_text="First day of the month the alert belongs to.")
    level = models.PositiveSmallIntegerField(help_text="Percent of the budget reached, e.g. 80 or 100.")
    spend_usd = models.DecimalField(max_digits=12, decimal_places=6)
    budget_usd = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["department", "month", "level"], name="one_alert_per_level_per_month"),
        ]

    def __str__(self) -> str:
        return f"{self.department} {self.month:%Y-%m} {self.level}%"
