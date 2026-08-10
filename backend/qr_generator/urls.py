from django.urls import path

from .views import GenerateQRPDFView, GenerateNodeCSVView

urlpatterns = [
    path(
        "generate/pdf/",
        GenerateQRPDFView.as_view(),
        name="generate-qr-pdf",
    ),
    path(
        "generate/csv/",
        GenerateNodeCSVView.as_view(),
        name="generate-node-csv",
    ),
]
