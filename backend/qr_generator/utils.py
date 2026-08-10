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


# ==========================================================
# QR CONFIGURATION
# ==========================================================

QR_SIZE = 48 * mm


# ==========================================================
# CAPTION CONFIGURATION
# ==========================================================

# Gap between QR and caption box
CAPTION_GAP = 6 * mm

# Caption font
FONT_NAME = "Helvetica-Bold"
FONT_SIZE = 12

# Maximum characters per line
MAX_CHARS_PER_LINE = 20

# Space inside caption box
BOX_PADDING = 5 * mm

# Caption box width = QR width
BOX_WIDTH = QR_SIZE

# Rounded corner radius
BOX_RADIUS = 2.5 * mm


# ==========================================================
# DIVIDER CONFIGURATION
# ==========================================================

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

    QR:
        White

    Background:
        Black

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
    Draw vertical white divider between
    the two QR code sections.
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


def draw_qr(
    pdf,
    image,
    qr_x,
    qr_y,
):
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
# GET CAPTION LINES
# ==========================================================


def get_caption_lines(caption):
    """
    Wrap caption into multiple lines.

    Returns:
        list[str]
    """

    if not caption:
        return []

    return textwrap.wrap(
        caption,
        width=MAX_CHARS_PER_LINE,
        break_long_words=True,
        break_on_hyphens=False,
    )


# ==========================================================
# CALCULATE CAPTION BOX HEIGHT
# ==========================================================


def get_caption_box_height(lines):
    """
    Calculate caption box height based
    on the number of text lines.
    """

    if not lines:
        return 0

    line_height = FONT_SIZE + 4

    return len(lines) * line_height + 2 * BOX_PADDING


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
    Draw caption inside ONE white box.

    The box width is exactly the same
    as the QR width.

    Multiple caption lines remain inside
    the same box.

    Text is centered both horizontally
    and vertically.
    """

    lines = get_caption_lines(caption)

    if not lines:
        return

    # ------------------------------------------
    # Calculate box height
    # ------------------------------------------

    box_height = get_caption_box_height(lines)

    # ------------------------------------------
    # Calculate box Y position
    # ------------------------------------------

    box_y = qr_y - CAPTION_GAP - box_height

    # ------------------------------------------
    # Draw white box
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
    # Caption font
    # ------------------------------------------

    pdf.setFillColor(black)

    pdf.setFont(
        FONT_NAME,
        FONT_SIZE,
    )

    # ------------------------------------------
    # Calculate vertical text position
    # ------------------------------------------

    line_height = FONT_SIZE + 4

    total_text_height = len(lines) * line_height

    text_y = box_y + (box_height + total_text_height) / 2 - line_height + 2

    # ------------------------------------------
    # Draw each line
    # ------------------------------------------

    center_x = qr_x + BOX_WIDTH / 2

    for line in lines:

        pdf.drawCentredString(
            center_x,
            text_y,
            line,
        )

        text_y -= line_height


# ==========================================================
# DRAW QR + CAPTION GROUP
# ==========================================================


def draw_qr_group(
    pdf,
    title,
    caption,
    column_x,
    column_width,
):
    """
    Draw complete QR + caption group.

    The entire group is centered:

        Horizontally
        Vertically

    inside its column.
    """

    # ------------------------------------------
    # Caption lines
    # ------------------------------------------

    lines = get_caption_lines(caption)

    # ------------------------------------------
    # Caption box height
    # ------------------------------------------

    caption_box_height = get_caption_box_height(lines) if lines else 0

    # ------------------------------------------
    # Total group height
    #
    # QR
    # +
    # Gap
    # +
    # Caption box
    # ------------------------------------------

    if lines:

        total_group_height = QR_SIZE + CAPTION_GAP + caption_box_height

    else:

        total_group_height = QR_SIZE

    # ------------------------------------------
    # Center entire group vertically
    # ------------------------------------------

    group_y = (PAGE_HEIGHT - total_group_height) / 2

    # ------------------------------------------
    # QR Y
    # ------------------------------------------

    qr_y = group_y + caption_box_height + CAPTION_GAP

    # ------------------------------------------
    # Center QR horizontally
    # ------------------------------------------

    qr_x = column_x + (column_width - QR_SIZE) / 2

    # ------------------------------------------
    # Generate QR
    # ------------------------------------------

    qr_image = generate_qr(title)

    # ------------------------------------------
    # Draw QR
    # ------------------------------------------

    draw_qr(
        pdf,
        qr_image,
        qr_x,
        qr_y,
    )

    # ------------------------------------------
    # Draw caption
    # ------------------------------------------

    if lines:

        draw_caption_box(
            pdf,
            caption,
            qr_x,
            qr_y,
        )


# ==========================================================
# GENERATE PDF FROM DATAFRAME
# ==========================================================


def generate_qr_pdf_from_dataframe(df):
    """
    Generate QR PDF from a pandas DataFrame.

    Required columns:

        id
        caption

    Layout:

        150 mm × 100 mm
        Landscape

        2 QR codes per page

        Each QR + caption group is
        horizontally and vertically centered.

    Returns:
        BytesIO object containing PDF.
    """

    # ------------------------------------------
    # Validate columns
    # ------------------------------------------

    required_columns = {
        "id",
        "caption",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:

        raise ValueError(
            "Missing required CSV columns: " + ", ".join(sorted(missing_columns))
        )

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
        # Draw each QR group
        # --------------------------------------

        for index, (_, row) in enumerate(rows.iterrows()):

            id = str(row["id"]).strip()

            caption = str(row["caption"]).strip()

            # ----------------------------------
            # Column position
            # ----------------------------------

            column_x = index * column_width

            # ----------------------------------
            # Draw centered QR group
            # ----------------------------------

            draw_qr_group(
                pdf,
                id,
                caption,
                column_x,
                column_width,
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
