import os
import tempfile
import textwrap

import pandas as pd
import qrcode

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import black, white

# ==========================================================
# CONFIGURATION
# ==========================================================

CSV_FILE = "input.csv"
OUTPUT_PDF = "qr_codes.pdf"

# 150 x 100 mm Landscape
PAGE_WIDTH = 150 * mm
PAGE_HEIGHT = 100 * mm

QR_SIZE = 48 * mm

TOP_MARGIN = 8 * mm

CAPTION_GAP = 6 * mm

FONT_NAME = "Helvetica-Bold"
FONT_SIZE = 15

LINE_SPACING = 18
MAX_CHARS_PER_LINE = 15

BOX_PADDING = 5 * mm
BOX_HEIGHT = 12 * mm
BOX_WIDTH = QR_SIZE  # Box width matches QR width
BOX_RADIUS = 2.5 * mm


DIVIDER_COLOR = white
DIVIDER_WIDTH = 1
DIVIDER_TOP_MARGIN = 8 * mm
DIVIDER_BOTTOM_MARGIN = 8 * mm

# ==========================================================
# QR Generator
# ==========================================================


def generate_qr(data, filename):

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=16,
        border=2,
    )

    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="white", back_color="black").convert("RGB")

    img.save(filename)


# ==========================================================
# PDF Generator
# ==========================================================


def create_pdf(csv_file, output_pdf):

    df = pd.read_csv(csv_file)

    pdf = canvas.Canvas(output_pdf, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))

    with tempfile.TemporaryDirectory() as tmp:

        for start in range(0, len(df), 2):

            rows = df.iloc[start : start + 2]

            # Black Background
            pdf.setFillColor(black)
            pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)

            column_width = PAGE_WIDTH / 2

            # ---------------------------------
            # Vertical Divider
            # ---------------------------------
            pdf.setStrokeColor(DIVIDER_COLOR)
            pdf.setLineWidth(DIVIDER_WIDTH)

            divider_x = PAGE_WIDTH / 2

            pdf.line(
                divider_x,
                DIVIDER_BOTTOM_MARGIN,
                divider_x,
                PAGE_HEIGHT - DIVIDER_TOP_MARGIN
            )
            
            qr_y = PAGE_HEIGHT - TOP_MARGIN - QR_SIZE

            for index, (_, row) in enumerate(rows.iterrows()):

                title = str(row["title"]).strip()
                caption = str(row["caption"]).strip()

                qr_file = os.path.join(tmp, f"{start+index}.png")

                generate_qr(title, qr_file)

                qr_x = index * column_width + (column_width - QR_SIZE) / 2

                # Draw QR
                pdf.drawImage(
                    ImageReader(qr_file),
                    qr_x,
                    qr_y,
                    width=QR_SIZE,
                    height=QR_SIZE,
                    preserveAspectRatio=True,
                    mask="auto",
                )

                # Wrap caption
                lines = textwrap.wrap(
                    caption,
                    width=MAX_CHARS_PER_LINE
                )

                box_y = qr_y - CAPTION_GAP - BOX_HEIGHT

                for line in lines:

                    # Center box under QR
                    box_x = qr_x

                    # Draw filled white box
                    pdf.setFillColor(white)
                    pdf.roundRect(
                        box_x,
                        box_y,
                        BOX_WIDTH,
                        BOX_HEIGHT,
                        BOX_RADIUS,
                        fill=1,
                        stroke=0
                    )

                    # Draw centered black text
                    pdf.setFillColor(black)
                    pdf.setFont(FONT_NAME, FONT_SIZE)

                    pdf.drawCentredString(
                        qr_x + BOX_WIDTH / 2,
                        box_y + 3.5 * mm,
                        line
                    )

                    box_y -= (BOX_HEIGHT + 2 * mm)

            pdf.showPage()

    pdf.save()

    print("=" * 50)
    print("PDF Generated Successfully")
    print("Output:", output_pdf)
    print("=" * 50)


# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":
    create_pdf(CSV_FILE, OUTPUT_PDF)
