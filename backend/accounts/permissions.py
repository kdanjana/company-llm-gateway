"""Who may see and change what in the dashboard API.

Every dashboard query starts from visible_departments(user), so a department head can never
read another department's data, even by guessing IDs in the URL.
"""
from __future__ import annotations

from django.db.models import QuerySet
from rest_framework.permissions import BasePermission

from gateway.models import Department

from .models import Profile


def get_profile(user) -> Profile | None:
    if not user or not user.is_authenticated:
        return None
    try:
        return user.profile
    except Profile.DoesNotExist:
        return None


def is_admin(user) -> bool:
    profile = get_profile(user)
    return profile is not None and profile.role == Profile.Role.ADMIN


def visible_departments(user) -> QuerySet[Department]:
    profile = get_profile(user)
    if profile is None:
        return Department.objects.none()
    if profile.role == Profile.Role.ADMIN:
        return Department.objects.all()
    return Department.objects.filter(pk=profile.department_id)


class IsAdminOrHead(BasePermission):
    message = "Only admins and department heads can use the dashboard."

    def has_permission(self, request, view):
        return get_profile(request.user) is not None


class IsAdmin(BasePermission):
    message = "Only admins can do this."

    def has_permission(self, request, view):
        return is_admin(request.user)
