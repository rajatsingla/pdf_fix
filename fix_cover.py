# fix_cover.py
# pip install pymupdf numpy
#
# One entry point that fixes a cover PDF (given as bytes) and resizes it to the
# desired final dimensions. All detection logic is reused from the existing
# scripts in this folder:
#   - remove_crop_marks.py : BleedBox/TrimBox crop + visual crop-mark detection
#   - trim_white_space.py  : whitespace fallback crop
#   - trim_flaps.py        : flap detection/removal
#   - resize.py            : final scaling

import fitz  # PyMuPDF

from remove_crop_marks import existing_box_clip, detect_crop_mark_clip, is_valid_clip
from trim_white_space import detect_nonwhite_bbox, expand_rect, has_real_crop, PADDING_PT
from trim_flaps import detect_flap_clip
from resize import resize_doc


def _apply_clip(src: fitz.Document, page_index: int, out: fitz.Document, clip: fitz.Rect) -> None:
    """
    Draw ``src`` page ``page_index`` into a new page of ``out``, cropped to ``clip``.

    Destination size == clip size, so artwork is cropped but never scaled or
    rasterized. All standard page boxes are reset to the new page. This is the
    same block used by the trim/flap scripts' main() loops.
    """
    new_page = out.new_page(width=clip.width, height=clip.height)

    new_page.show_pdf_page(
        new_page.rect,
        src,
        page_index,
        clip=clip,
    )

    new_page.set_cropbox(new_page.rect)
    new_page.set_trimbox(new_page.rect)
    new_page.set_bleedbox(new_page.rect)
    new_page.set_artbox(new_page.rect)


def _trim_clip(page: fitz.Page) -> fitz.Rect:
    """
    Decide the trim clip for a page using the requested priority:
      1. BleedBox if present
      2. else TrimBox if present
      3. else visual crop-mark detection
      4. else whitespace crop
    Falls back to the full page rect if nothing qualifies.
    """
    page_rect = page.rect

    # 1. BleedBox
    clip = existing_box_clip(page, page.bleedbox)
    if clip is not None:
        return clip

    # 2. TrimBox
    clip = existing_box_clip(page, page.trimbox)
    if clip is not None:
        return clip

    # 3. Visual crop marks
    clip, info = detect_crop_mark_clip(page)
    if info.get("detected"):
        return clip

    # 4. Whitespace fallback
    detected = detect_nonwhite_bbox(page)
    if detected is not None:
        detected = expand_rect(detected, PADDING_PT, page_rect)
        # Require both a real crop and a sane size. Without the size guard a
        # single stray dark pixel (or the any-non-white fallback inside
        # detect_nonwhite_bbox) could crop the cover down to a speck.
        if has_real_crop(page_rect, detected) and is_valid_clip(detected, page_rect):
            return detected

    return page_rect


def fix_cover(
    cover_bytes: bytes,
    final_width_in: float,
    final_height_in: float,
    output_path: str | None = None,
) -> bytes:
    """
    Fix a cover PDF and resize it to the final dimensions.

    Pipeline:
      1-4. Crop to BleedBox / TrimBox / detected crop marks / whitespace.
      5.   Detect and remove flaps if present.
      6.   Resize to ``final_width_in`` x ``final_height_in`` (inches).

    Args:
        cover_bytes:     The cover PDF as bytes.
        final_width_in:  Desired final width in inches.
        final_height_in: Desired final height in inches.
        output_path:     Optional path to also write the final PDF to.

    Returns:
        The final PDF as bytes.
    """
    src = fitz.open(stream=cover_bytes, filetype="pdf")

    # Stage A: trim (bleed / trim / crop marks / whitespace).
    stage_a = fitz.open()
    stage_a.set_metadata(src.metadata)
    for page_index, page in enumerate(src):
        _apply_clip(src, page_index, stage_a, _trim_clip(page))
    src.close()

    # Stage B: remove flaps (no-op when none detected).
    stage_b = fitz.open()
    stage_b.set_metadata(stage_a.metadata)
    for page_index, page in enumerate(stage_a):
        clip, _info = detect_flap_clip(page)
        _apply_clip(stage_a, page_index, stage_b, clip)
    stage_a.close()

    # Stage C: resize to final dimensions.
    resize_doc(stage_b, final_width_in, final_height_in)

    data = stage_b.tobytes(garbage=4, deflate=True)
    stage_b.close()

    if output_path is not None:
        with open(output_path, "wb") as f:
            f.write(data)

    return data


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 5:
        print("usage: python fix_cover.py <input.pdf> <width_in> <height_in> <output.pdf>")
        raise SystemExit(1)

    in_path, w_in, h_in, out_path = sys.argv[1:5]
    with open(in_path, "rb") as f:
        result = fix_cover(f.read(), float(w_in), float(h_in), out_path)

    print(f"Saved: {out_path} ({len(result)} bytes)")
