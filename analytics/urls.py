from django.urls import path

from . import views

urlpatterns = [
    path("analysis/", views.PortfolioAnalysisView.as_view(), name="analytics-analysis"),
]
