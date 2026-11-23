"""Dashboard users. Login uses Django's built-in User; the role and department are in Profile.

Roles:
- admin: sees every department, sets budgets, models and prices, manages any department's API keys.
- head:  department head; sees only their own department, manages its API keys, cannot change budgets.

A user without a Profile (e.g. a Django superuser for /admin) cannot log in to the dashboard.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q


class Profile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        HEAD = "head", "Department head"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=Role.choices)
    department = models.ForeignKey(
        "gateway.Department",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="heads",
        help_text="Required for department heads.",
    )

    class Meta:
        constraints = [
            # The database itself refuses a department head without a department.
            models.CheckConstraint(
                condition=Q(role="admin") | Q(department__isnull=False),
                name="head_needs_department",
            ),
        ]

    def __str__(self) -> str:
        where = f" of {self.department}" if self.department_id else ""
        return f"{self.user} ({self.get_role_display()}{where})"
