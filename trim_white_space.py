# trim_cover_whitespace.py
# pip install pymupdf numpy

from pathlib import Path
import fitz  # PyMuPDF
import numpy as np


INPUT_PDF = Path("yo2.pdf")
OUTPUT_PDF = Path("yo_trimmed.pdf")

# Rendering DPI used only for detection.
# Higher = more accurate but slower.
DETECT_DPI = 200

# Pixels are considered "white" only if all RGB channels are >= this value.
# Lower this if light artwork is being treated as whitespace.
WHITE_THRESHOLD = 245

# Ignore tiny marks like crop marks by requiring a row/column to have
# enough non-white pixels before it counts as actual cover content.
# 0.02 = 2% of row/column.
MIN_COVERAGE_RATIO = 0.02

# Small safety padding so edge artwork is not clipped.
# Set to 0 if you want the tightest crop.
PADDING_PT = 0.5

# If detected crop removes less than this many points, treat as "no whitespace".
MIN_CROP_PT = 1.0


def expand_rect(rect: fitz.Rect, padding: float, bounds: fitz.Rect) -> fitz.Rect:
    return fitz.Rect(
        max(bounds.x0, rect.x0 - padding),
        max(bounds.y0, rect.y0 - padding),
        min(bounds.x1, rect.x1 + padding),
        min(bounds.y1, rect.y1 + padding),
    )


def detect_nonwhite_bbox(page: fitz.Page) -> fitz.Rect | None:
    """
    Detect the main non-white cover area.

    Important:
    - This is only for detection.
    - The output PDF remains vector because we crop using show_pdf_page().
    """

    zoom = DETECT_DPI / 72.0

    pix = page.get_pixmap(
        matrix=fitz.Matrix(zoom, zoom),
        colorspace=fitz.csRGB,
        alpha=False,
    )

    arr = np.frombuffer(pix.samples, dtype=np.uint8)
    arr = arr.reshape(pix.height, pix.width, pix.n)

    rgb = arr[:, :, :3]

    # True where pixel is not white.
    non_white = np.any(rgb < WHITE_THRESHOLD, axis=2)

    h, w = non_white.shape

    row_counts = non_white.sum(axis=1)
    col_counts = non_white.sum(axis=0)

    # Coverage threshold helps ignore thin crop marks in the whitespace.
    min_row_pixels = max(1, int(w * MIN_COVERAGE_RATIO))
    min_col_pixels = max(1, int(h * MIN_COVERAGE_RATIO))

    rows = np.where(row_counts >= min_row_pixels)[0]
    cols = np.where(col_counts >= min_col_pixels)[0]

    # Fallback: if the coverage method finds nothing, use any non-white pixel.
    if len(rows) == 0 or len(cols) == 0:
        rows = np.where(row_counts > 0)[0]
        cols = np.where(col_counts > 0)[0]

    if len(rows) == 0 or len(cols) == 0:
        return None

    x0 = cols[0] / zoom
    y0 = rows[0] / zoom
    x1 = (cols[-1] + 1) / zoom
    y1 = (rows[-1] + 1) / zoom

    rect = fitz.Rect(x0, y0, x1, y1)
    rect = rect & page.rect

    if rect.is_empty or rect.width <= 0 or rect.height <= 0:
        return None

    return rect


def has_real_crop(page_rect: fitz.Rect, crop_rect: fitz.Rect) -> bool:
    left = crop_rect.x0 - page_rect.x0
    top = crop_rect.y0 - page_rect.y0
    right = page_rect.x1 - crop_rect.x1
    bottom = page_rect.y1 - crop_rect.y1

    return max(left, top, right, bottom) > MIN_CROP_PT


def pt_to_in(value: float) -> float:
    return value / 72.0


def main():
    src = fitz.open(INPUT_PDF)
    out = fitz.open()

    out.set_metadata(src.metadata)

    for page_index, page in enumerate(src):
        page_rect = page.rect

        detected = detect_nonwhite_bbox(page)

        if detected is None:
            clip = page_rect
            cropped = False
        else:
            detected = expand_rect(detected, PADDING_PT, page_rect)

            if has_real_crop(page_rect, detected):
                clip = detected
                cropped = True
            else:
                clip = page_rect
                cropped = False

        # Create a new page exactly equal to the cropped area.
        # This changes page size but does not scale artwork.
        new_page = out.new_page(width=clip.width, height=clip.height)

        # Draw original PDF page into the new page using clip.
        # Destination size == clip size, so there is no resizing.
        new_page.show_pdf_page(
            new_page.rect,
            src,
            page_index,
            clip=clip,
        )

        # Make all standard boxes match the new cropped page.
        new_page.set_cropbox(new_page.rect)
        new_page.set_trimbox(new_page.rect)
        new_page.set_bleedbox(new_page.rect)
        new_page.set_artbox(new_page.rect)

        print(f"Page {page_index + 1}:")
        print(
            f"  old size: {page_rect.width:.2f} x {page_rect.height:.2f} pt "
            f"({pt_to_in(page_rect.width):.3f} x {pt_to_in(page_rect.height):.3f} in)"
        )
        print(
            f"  new size: {clip.width:.2f} x {clip.height:.2f} pt "
            f"({pt_to_in(clip.width):.3f} x {pt_to_in(clip.height):.3f} in)"
        )
        print(f"  cropped:  {cropped}")
        print(
            f"  removed:  left={clip.x0:.2f} pt, "
            f"top={clip.y0:.2f} pt, "
            f"right={page_rect.x1 - clip.x1:.2f} pt, "
            f"bottom={page_rect.y1 - clip.y1:.2f} pt"
        )

    out.save(OUTPUT_PDF, garbage=4, deflate=True)
    out.close()
    src.close()

    print(f"\nSaved: {OUTPUT_PDF.resolve()}")


if __name__ == "__main__":
    main()