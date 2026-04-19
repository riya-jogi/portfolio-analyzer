"""URL configuration for portfolio_analyzer project."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("", include("portfolio.urls")),
    path("", include("analytics.urls")),
]
