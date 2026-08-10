import io
import textwrap

import pandas as pd
import qrcode

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import black, white

# ==========================================================
# PDF CONFIGURATION
# ==========================================================

# Landscape page:
# 150 mm width × 100 mm height
PAGE_WIDTH = 150 * mm
PAGE_HEIGHT = 100 * mm

# QR code size
QR_SIZE = 48 * mm

# Top margin
TOP_MARGIN = 8 * mm

# Gap between QR and caption box
CAPTION_GAP = 6 * mm

# Caption font
FONT_NAME = "Helvetica-Bold"
FONT_SIZE = 15

# Caption wrapping
MAX_CHARS_PER_LINE = 15

# Caption box
BOX_HEIGHT = 12 * mm
BOX_WIDTH = QR_SIZE
BOX_RADIUS = 2.5 * mm
BOX_PADDING = 5 * mm

# Divider
DIVIDER_COLOR = white
DIVIDER_WIDTH = 1
DIVIDER_TOP_MARGIN = 8 * mm
DIVIDER_BOTTOM_MARGIN = 8 * mm


# ==========================================================
# QR CODE GENERATOR
# ==========================================================


def generate_qr(data):
    """
    Generate an inverted QR code.

    White QR code
    Black background

    Returns:
        PIL Image
    """

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=16,
        border=2,
    )

    qr.add_data(data)
    qr.make(fit=True)

    image = qr.make_image(
        fill_color="white",
        back_color="black",
    ).convert("RGB")

    return image


# ==========================================================
# DRAW PAGE BACKGROUND
# ==========================================================


def draw_background(pdf):
    """
    Draw black background on the entire page.
    """

    pdf.setFillColor(black)

    pdf.rect(
        0,
        0,
        PAGE_WIDTH,
        PAGE_HEIGHT,
        fill=1,
        stroke=0,
    )


# ==========================================================
# DRAW VERTICAL DIVIDER
# ==========================================================


def draw_divider(pdf):
    """
    Draw vertical white divider between the two QR codes.
    """

    pdf.setStrokeColor(DIVIDER_COLOR)
    pdf.setLineWidth(DIVIDER_WIDTH)

    divider_x = PAGE_WIDTH / 2

    pdf.line(
        divider_x,
        DIVIDER_BOTTOM_MARGIN,
        divider_x,
        PAGE_HEIGHT - DIVIDER_TOP_MARGIN,
    )


# ==========================================================
# DRAW QR CODE
# ==========================================================


def draw_qr(pdf, image, qr_x, qr_y):
    """
    Draw QR image on PDF.
    """

    image_buffer = io.BytesIO()

    image.save(
        image_buffer,
        format="PNG",
    )

    image_buffer.seek(0)

    pdf.drawImage(
        ImageReader(image_buffer),
        qr_x,
        qr_y,
        width=QR_SIZE,
        height=QR_SIZE,
        preserveAspectRatio=True,
        mask="auto",
    )


# ==========================================================
# DRAW CAPTION BOX
# ==========================================================


def draw_caption_box(
    pdf,
    caption,
    qr_x,
    qr_y,
):
    """
    Draw caption inside one single filled white box.

    The box width matches the QR width.
    If the caption wraps into multiple lines,
    the box height automatically increases.
    """

    pdf.setFont(
        FONT_NAME,
        FONT_SIZE,
    )

    # ------------------------------------------
    # Wrap caption into multiple lines
    # ------------------------------------------

    lines = textwrap.wrap(
        caption,
        width=MAX_CHARS_PER_LINE,
    )

    if not lines:
        return

    # ------------------------------------------
    # Calculate box height dynamically
    # ------------------------------------------

    line_height = FONT_SIZE + 4

    box_height = len(lines) * line_height + 2 * BOX_PADDING

    # ------------------------------------------
    # Box position
    # ------------------------------------------

    box_y = qr_y - CAPTION_GAP - box_height

    # ------------------------------------------
    # Draw ONE white box
    # ------------------------------------------

    pdf.setFillColor(white)

    pdf.roundRect(
        qr_x,
        box_y,
        BOX_WIDTH,
        box_height,
        BOX_RADIUS,
        fill=1,
        stroke=0,
    )

    # ------------------------------------------
    # Draw caption
    # ------------------------------------------

    pdf.setFillColor(black)

    pdf.setFont(
        FONT_NAME,
        FONT_SIZE,
    )

    # Start from top of box
    text_y = box_y + box_height - BOX_PADDING - FONT_SIZE

    for line in lines:

        pdf.drawCentredString(
            qr_x + BOX_WIDTH / 2,
            text_y,
            line,
        )

        text_y -= line_height


# ==========================================================
# GENERATE PDF FROM DATAFRAME
# ==========================================================


def generate_qr_pdf_from_dataframe(df):
    """
    Generate QR PDF from a pandas DataFrame.

    Required columns:

        title
        caption

    Returns:
        BytesIO object containing PDF.
    """

    required_columns = {
        "title",
        "caption",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:

        raise ValueError("Missing required CSV columns: " + ", ".join(missing_columns))

    # ------------------------------------------
    # Create PDF in memory
    # ------------------------------------------

    pdf_buffer = io.BytesIO()

    pdf = canvas.Canvas(
        pdf_buffer,
        pagesize=(
            PAGE_WIDTH,
            PAGE_HEIGHT,
        ),
    )

    # ------------------------------------------
    # Two QR codes per page
    # ------------------------------------------

    for start in range(
        0,
        len(df),
        2,
    ):

        rows = df.iloc[start : start + 2]

        # --------------------------------------
        # Background
        # --------------------------------------

        draw_background(pdf)

        # --------------------------------------
        # Divider
        # --------------------------------------

        draw_divider(pdf)

        # --------------------------------------
        # Two equal columns
        # --------------------------------------

        column_width = PAGE_WIDTH / 2

        # --------------------------------------
        # QR Y position
        # --------------------------------------

        qr_y = PAGE_HEIGHT - TOP_MARGIN - QR_SIZE

        # --------------------------------------
        # Draw each QR
        # --------------------------------------

        for index, (_, row) in enumerate(rows.iterrows()):

            title = str(row["title"]).strip()

            caption = str(row["caption"]).strip()

            # ------------------------------
            # Generate QR
            # ------------------------------

            qr_image = generate_qr(title)

            # ------------------------------
            # Center QR inside column
            # ------------------------------

            qr_x = index * column_width + (column_width - QR_SIZE) / 2

            # ------------------------------
            # Draw QR
            # ------------------------------

            draw_qr(
                pdf,
                qr_image,
                qr_x,
                qr_y,
            )

            # ------------------------------
            # Draw Caption
            # ------------------------------

            draw_caption_box(
                pdf,
                caption,
                qr_x,
                qr_y,
            )

        # --------------------------------------
        # Finish page
        # --------------------------------------

        pdf.showPage()

    # ------------------------------------------
    # Finish PDF
    # ------------------------------------------

    pdf.save()

    pdf_buffer.seek(0)

    return pdf_buffer


# ==========================================================
# GENERATE PDF FROM CSV
# ==========================================================


def generate_qr_pdf(csv_file):
    """
    Generate QR PDF from uploaded CSV file.

    csv_file can be:

        Django UploadedFile
        file-like object
        local file

    Required CSV columns:

        title
        caption

    Returns:
        BytesIO containing generated PDF.
    """

    try:

        df = pd.read_csv(csv_file)

    except Exception as exc:

        raise ValueError(f"Unable to read CSV file: {exc}")

    return generate_qr_pdf_from_dataframe(df)
