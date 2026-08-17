"""Game-master exports: printable QR sheets, and the node answer key.

Both are superuser-only, checked in the handler rather than by a guard so the
403 body stays the one clients already got.
"""
import csv
import io
from typing import Annotated

from django_bolt import JSON, Router, UploadFile
from django_bolt.params import File
from django_bolt.responses import Response

from config.concurrency import run_db
from config.security import DEFAULT_AUTH, DEFAULT_GUARDS
from users.models import Node

from .utils import generate_qr_pdf

qr_router = Router(
    prefix="/api/generate", tags=["generate"],
    auth=DEFAULT_AUTH, guards=DEFAULT_GUARDS,
)

_FORBIDDEN = {"detail": "You do not have permission to access this resource."}


@qr_router.post(
    "/pdf/",
    summary="Generate QR Code PDF",
    description=(
        "Upload a CSV file containing 'title' and 'caption' columns. "
        "The API generates a PDF containing two QR codes per "
        "150 x 100 mm landscape page."
    ),
)
async def generate_pdf(request, file: Annotated[UploadFile, File()]):
    # The File() marker is load-bearing: a bare UploadFile annotation is
    # read as a query parameter, not a multipart part.
    return await run_db(_generate_pdf, request, file)


def _generate_pdf(request, file):
    if not request.user.is_superuser:
        return JSON(_FORBIDDEN, status_code=403)

    if not (file.filename or "").lower().endswith(".csv"):
        return JSON({"file": ["Only CSV files are allowed."]}, status_code=400)

    try:
        pdf_buffer = generate_qr_pdf(io.BytesIO(file.file.read()))
    except ValueError as exc:
        return JSON({"detail": str(exc)}, status_code=400)
    except Exception as exc:
        return JSON({"detail": f"Failed to generate PDF: {exc}"}, status_code=500)

    return Response(
        pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="qr_codes.pdf"'},
    )


@qr_router.get(
    "/csv/",
    summary="Generate Node CSV",
    description=(
        "Generate a CSV file from the Node table. The CSV contains the Node "
        "answer and the data of its next_node."
    ),
)
async def generate_csv(request):
    return await run_db(_generate_csv, request)


def _generate_csv(request):
    if not request.user.is_superuser:
        return JSON(_FORBIDDEN, status_code=403)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "caption"])

    for node in Node.objects.select_related("next_node").all():
        writer.writerow([node.next_node.id if node.next_node else "", node.answer])

    return Response(
        buffer.getvalue().encode(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="nodes.csv"'},
    )
