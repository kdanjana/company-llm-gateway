"""API-key login for apps calling the gateway.

The calling app sends:   Authorization: Bearer gw_xxxxxxxx...
We hash the key and look the hash up. The raw key is never stored, so a database leak does not leak keys.
"""
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework import authentication, exceptions, permissions

from .models import ApiKey, hash_key


class ApiKeyAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("latin-1")
        if not header:
            return None  # no key sent -> HasApiKey refuses with 401

        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            raise exceptions.AuthenticationFailed("Send the key as: Authorization: Bearer <api key>")

        api_key = ApiKey.objects.select_related("department").filter(key_hash=hash_key(parts[1])).first()
        if api_key is None or not api_key.is_active or not api_key.department.is_active:
            # Same message for "unknown" and "disabled", so callers cannot probe which keys exist.
            raise exceptions.AuthenticationFailed("Invalid or disabled API key.")

        # .update() writes one column without loading/saving the whole row (safe with parallel requests).
        ApiKey.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())
        # DRF expects (user, auth). There is no person behind an app call, so user is anonymous
        # and the ApiKey travels as request.auth.
        return (AnonymousUser(), api_key)

    def authenticate_header(self, request):
        # Having this makes DRF answer 401 (not 403) when the key is missing or wrong.
        return self.keyword


class HasApiKey(permissions.BasePermission):
    """Allows the request only if ApiKeyAuthentication accepted a key."""

    def has_permission(self, request, view):
        return isinstance(request.auth, ApiKey)
