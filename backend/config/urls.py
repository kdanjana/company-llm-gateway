from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    """Tells Docker / a load balancer that the web process is up. No login needed."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/v1/", include("gateway.urls")),               # apps calling models (API key)
    path("api/auth/", include("accounts.urls")),            # dashboard login (JWT)
    path("api/dashboard/", include("gateway.dashboard_urls")),  # dashboard data (JWT + role)
]
