from django.urls import path

from . import views

urlpatterns = [
    path("upload/", views.CsvUploadView.as_view(), name="portfolio-upload"),
]
