from django.urls import path
from rest_framework.routers import SimpleRouter

from .dashboard_views import (
    AlertsView,
    ApiKeyViewSet,
    DailyCostView,
    DepartmentViewSet,
    ModelPriceViewSet,
    ModelUsageView,
    RequestsView,
    SummaryView,
)

router = SimpleRouter()
router.register("departments", DepartmentViewSet, basename="department")
router.register("api-keys", ApiKeyViewSet, basename="apikey")
router.register("models", ModelPriceViewSet, basename="modelprice")

urlpatterns = [
    path("summary/", SummaryView.as_view(), name="summary"),
    path("daily/", DailyCostView.as_view(), name="daily"),
    path("models-usage/", ModelUsageView.as_view(), name="models-usage"),
    path("requests/", RequestsView.as_view(), name="requests"),
    path("alerts/", AlertsView.as_view(), name="alerts"),
    *router.urls,
]
