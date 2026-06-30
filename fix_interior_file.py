# fix_interior_file.py
# pip install pymupdf numpy
#
# One entry point that fixes an interior (book block) PDF given as bytes:
#   1. Remove crop marks if present (no flaps, no whitespace trim).
#   2. Match the page size to the supported book trim sizes, allowing up to
#      +0.25 in of added trim/bleed.
#   3. Always run the resize pipeline to normalise the file:
#        - match found  -> resize to the file's own dimensions (normalise only,
#                          which also fixes stray rotated/horizontal pages).
#        - no match     -> resize to the closest supported trim size.
#
# All detection/editing logic is reused from the existing scripts in this folder.

import fitz  # PyMuPDF

from remove_crop_marks import existing_box_clip, detect_crop_mark_clip
from resize import resize_doc
from fix_cover import _apply_clip

POINTS_PER_INCH = 72

# A file may carry up to this much added trim/bleed over the true trim size.
TRIM_TOLERANCE_IN = 0.25

# Supported book trim sizes (international superset of domesticBookSizes),
# mirrored from tango/src/utils/book/index.ts. Includes both portrait and
# landscape variants, so (width, height) is compared directly.
SUPPORTED_SIZES = [
    {"name": "Pocket Book", "width_in": 4.25, "height_in": 6.87},
    {"name": "Novella", "width_in": 5.0, "height_in": 8.0},
    {"name": "Digest", "width_in": 5.5, "height_in": 8.5},
    {"name": "A5", "width_in": 5.83, "height_in": 8.27},
    {"name": "US Trade", "width_in": 6.0, "height_in": 9.0},
    {"name": "Royal", "width_in": 6.14, "height_in": 9.21},
    {"name": "Executive", "width_in": 7.0, "height_in": 10.0},
    {"name": "Crown Quarto", "width_in": 7.44, "height_in": 9.68},
    {"name": "Small Square", "width_in": 7.5, "height_in": 7.5},
    {"name": "A4", "width_in": 8.27, "height_in": 11.69},
    {"name": "Square", "width_in": 8.5, "height_in": 8.5},
    {"name": "US Letter", "width_in": 8.5, "height_in": 11.0},
    {"name": "Small Landscape", "width_in": 9.0, "height_in": 7.0},
    {"name": "US Letter Landscape", "width_in": 11.0, "height_in": 8.5},
    {"name": "A4 Landscape", "width_in": 11.69, "height_in": 8.27},
]


def _crop_marks_clip(page: fitz.Page) -> fitz.Rect:
    """
    Decide the crop-mark clip for an interior page:
      1. BleedBox if present
      2. else TrimBox if present
      3. else visual crop-mark detection
    Falls back to the full page rect when no crop marks are found.
    No whitespace trim and no flap handling for interiors.
    """
    clip = existing_box_clip(page, page.bleedbox)
    if clip is not None:
        return clip

    clip = existing_box_clip(page, page.trimbox)
    if clip is not None:
        return clip

    clip, info = detect_crop_mark_clip(page)
    if info.get("detected"):
        return clip

    return page.rect


def _area(size: dict) -> float:
    return size["width_in"] * size["height_in"]


def _match_size(width_in: float, height_in: float) -> tuple[str, dict]:
    """
    Match (width_in, height_in) against the supported sizes.

    A size matches when the file is no smaller than the trim size and at most
    TRIM_TOLERANCE_IN larger on each dimension:
        size.w <= width  <= size.w + 0.25  AND  size.h <= height <= size.h + 0.25

    Returns ("match", size) when at least one size matches (ambiguous ->
    smallest area). Otherwise ("resize", closest_size) by Euclidean distance,
    ties broken towards the smaller size.
    """
    matches = [
        s for s in SUPPORTED_SIZES
        if s["width_in"] <= width_in <= s["width_in"] + TRIM_TOLERANCE_IN
        and s["height_in"] <= height_in <= s["height_in"] + TRIM_TOLERANCE_IN
    ]

    if matches:
        return "match", min(matches, key=_area)

    def distance(s: dict) -> tuple[float, float]:
        dw = width_in - s["width_in"]
        dh = height_in - s["height_in"]
        return (dw * dw + dh * dh, _area(s))

    return "resize", min(SUPPORTED_SIZES, key=distance)


def fix_interior_file(pdf_bytes: bytes, output_path: str | None = None) -> bytes:
    """
    Fix an interior PDF: remove crop marks, match to a supported size, and
    resize/normalise.

    Args:
        pdf_bytes:   The interior PDF as bytes.
        output_path: Optional path to also write the final PDF to.

    Returns:
        The final PDF as bytes.
    """
    src = fitz.open(stream=pdf_bytes, filetype="pdf")

    # Stage A: remove crop marks (BleedBox / TrimBox / visual marks).
    stage_a = fitz.open()
    stage_a.set_metadata(src.metadata)
    for page_index, page in enumerate(src):
        _apply_clip(src, page_index, stage_a, _crop_marks_clip(page))
    src.close()

    # Match the (uniform) page size against the supported trim sizes.
    width_in = stage_a[0].rect.width / POINTS_PER_INCH
    height_in = stage_a[0].rect.height / POINTS_PER_INCH
    kind, size = _match_size(width_in, height_in)

    if kind == "match":
        # Already a supported size (within trim tolerance): keep its own dims,
        # run resize only to normalise (e.g. fix stray rotated pages).
        target_w_in, target_h_in = width_in, height_in
    else:
        target_w_in, target_h_in = size["width_in"], size["height_in"]

    # Stage B: resize / normalise.
    resize_doc(stage_a, target_w_in, target_h_in)

    data = stage_a.tobytes(garbage=4, deflate=True)
    stage_a.close()

    if output_path is not None:
        with open(output_path, "wb") as f:
            f.write(data)

    return data


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("usage: python fix_interior_file.py <input.pdf> <output.pdf>")
        raise SystemExit(1)

    in_path, out_path = sys.argv[1:3]
    with open(in_path, "rb") as f:
        result = fix_interior_file(f.read(), out_path)

    print(f"Saved: {out_path} ({len(result)} bytes)")
