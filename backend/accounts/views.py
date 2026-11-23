"""Dashboard login with JWT (same approach as the Knowledge Hub project).

POST /api/auth/login/    {"username", "password"}  -> {"access", "refresh"}
POST /api/auth/refresh/  {"refresh"}               -> {"access", "refresh"}  (the refresh token rotates)
POST /api/auth/logout/   {"refresh"}               -> the refresh token is blacklisted
GET  /api/auth/me/                                 -> {"username", "role", "department"}
"""
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .permissions import IsAdminOrHead, get_profile


class DashboardLoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)  # checks username + password
        if get_profile(self.user) is None:
            raise exceptions.AuthenticationFailed("This account has no dashboard access.", code="no_dashboard_access")
        return data


class LoginView(TokenObtainPairView):
    serializer_class = DashboardLoginSerializer


class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        try:
            RefreshToken(request.data.get("refresh", "")).blacklist()
        except TokenError:
            pass  # already expired or invalid: the user is logged out either way
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAdminOrHead]

    def get(self, request):
        profile = get_profile(request.user)
        department = profile.department
        return Response(
            {
                "username": request.user.username,
                "role": profile.role,
                "department": {"id": department.id, "name": department.name} if department else None,
            }
        )
