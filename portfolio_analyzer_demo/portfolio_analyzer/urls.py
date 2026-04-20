from django.urls import path
from portfolio.views import UploadCSV, PortfolioAnalysis

urlpatterns = [
    path('upload/', UploadCSV.as_view()),
    path('analysis/', PortfolioAnalysis.as_view()),
]
