from django.http import FileResponse

from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import HttpResponse

from drf_spectacular.utils import extend_schema

from .serializers import QRPDFUploadSerializer
from .utils import generate_qr_pdf
from users.models import Node
import csv


class GenerateQRPDFView(APIView):

    parser_classes = [
        MultiPartParser,
        FormParser,
    ]

    @extend_schema(
        summary="Generate QR Code PDF",
        description=(
            "Upload a CSV file containing "
            "'title' and 'caption' columns. "
            "The API generates a PDF containing "
            "two QR codes per 150 x 100 mm landscape page."
        ),
        request={
            "multipart/form-data": QRPDFUploadSerializer,
        },
        responses={
            200: {
                "type": "string",
                "format": "binary",
                "description": "Generated QR Code PDF",
            },
            400: {
                "description": "Invalid CSV file",
            },
        },
    )
    def post(self, request):
        if not request.user.is_superuser:
            return Response(
                {"detail": "You do not have permission to access this resource."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = QRPDFUploadSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        csv_file = serializer.validated_data["file"]

        try:

            pdf_buffer = generate_qr_pdf(csv_file)

        except ValueError as exc:

            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as exc:

            return Response(
                {"detail": ("Failed to generate PDF: " f"{str(exc)}")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = FileResponse(
            pdf_buffer,
            content_type="application/pdf",
        )

        response["Content-Disposition"] = 'attachment; filename="qr_codes.pdf"'

        return response


class GenerateNodeCSVView(APIView):

    @extend_schema(
        summary="Generate Node CSV",
        description=(
            "Generate a CSV file from the Node table. "
            "The CSV contains the Node answer and "
            "the data of its next_node."
        ),
        responses={
            200: {
                "type": "string",
                "format": "binary",
                "description": "Generated CSV file",
            }
        },
    )
    def get(self, request):
        if not request.user.is_superuser:
            return Response(
                {"detail": "You do not have permission to access this resource."},
                status=status.HTTP_403_FORBIDDEN,
            )
        response = HttpResponse(content_type="text/csv")

        response["Content-Disposition"] = "attachment; " 'filename="nodes.csv"'

        writer = csv.writer(response)

        writer.writerow(
            [
                "title",
                "caption",
            ]
        )

        nodes = Node.objects.select_related("next_node").all()

        for node in nodes:

            next_node_data = node.next_node.data if node.next_node else ""

            writer.writerow(
                [
                    next_node_data,
                    node.answer,
                ]
            )

        return response
