# remove_cover_flaps.py
# pip install pymupdf numpy

from pathlib import Path
import fitz  # PyMuPDF
import numpy as np


INPUT_PDF = Path("yo_trimmed.pdf")
OUTPUT_PDF = Path("yo_no_flaps.pdf")

POINTS_PER_INCH = 72

# Render resolution used only for detection.
# Output PDF is not rasterized.
DETECT_DPI = 150

# A full cover with flaps is usually much wider than a normal wrap cover.
# For example, no-flap wrap cover may be ~1.3x-1.6x height;
# flapped cover often becomes ~1.8x+ height.
MIN_PAGE_ASPECT_FOR_FLAPS = 1.75

# Where to search for left and right flap fold lines.
# These are ratios of total page width.
LEFT_SEAM_SEARCH = (0.08, 0.35)
RIGHT_SEAM_SEARCH = (0.65, 0.92)

# Expected flap width range as ratio of total page width.
MIN_FLAP_WIDTH_RATIO = 0.08
MAX_FLAP_WIDTH_RATIO = 0.35

# Flaps are usually roughly equal width.
# Set this higher if your left/right flaps can differ a lot.
MAX_FLAP_WIDTH_DIFF_RATIO = 0.06

# Seam must be stronger than the average page noise.
# Increase if it crops non-flap covers incorrectly.
# Decrease if it fails to detect real flaps.
SEAM_SCORE_MULTIPLIER = 5.0

# Safety padding inside the detected fold line.
# Positive value keeps a tiny bit extra near the fold.
PADDING_PT = 0.5

# Optional manual override.
# Use these if you know exact flap widths.
# Example: MANUAL_LEFT_FLAP_IN = 3.25
MANUAL_LEFT_FLAP_IN = None
MANUAL_RIGHT_FLAP_IN = None


def pt_to_in(value: float) -> float:
    return value / POINTS_PER_INCH


def smooth_signal(signal: np.ndarray, window: int) -> np.ndarray:
    window = max(3, int(window))
    if window % 2 == 0:
        window += 1

    kernel = np.ones(window, dtype=np.float32) / window
    return np.convolve(signal, kernel, mode="same")


def smooth_columns(columns: np.ndarray, window: int) -> np.ndarray:
    window = max(3, int(window))
    if window % 2 == 0:
        window += 1

    kernel = np.ones(window, dtype=np.float32) / window

    smoothed = np.empty_like(columns, dtype=np.float32)
    for channel in range(columns.shape[1]):
        smoothed[:, channel] = np.convolve(
            columns[:, channel],
            kernel,
            mode="same",
        )

    return smoothed


def best_seam(signal: np.ndarray, start_ratio: float, end_ratio: float) -> tuple[int, float]:
    w = len(signal)
    start = int(w * start_ratio)
    end = int(w * end_ratio)

    segment = signal[start:end]
    local_index = int(np.argmax(segment))
    index = start + local_index

    return index, float(signal[index])


def detect_flap_clip(page: fitz.Page) -> tuple[fitz.Rect, dict]:
    """
    Detect left/right cover flaps and return the clip rect to keep.

    Method:
    - Render page only for detection.
    - Compute the dominant vertical color profile.
    - Find strong vertical fold/seam positions near left and right sides.
    - Crop away only the outer panels if both seams look valid.

    Output PDF keeps PDF content via show_pdf_page(), so it is not resized
    and not rasterized.
    """

    page_rect = page.rect
    page_aspect = page_rect.width / page_rect.height

    info = {
        "detected": False,
        "reason": "",
        "page_aspect": page_aspect,
        "left_flap_pt": 0,
        "right_flap_pt": 0,
        "left_score": 0,
        "right_score": 0,
    }

    # Manual override path.
    if MANUAL_LEFT_FLAP_IN is not None or MANUAL_RIGHT_FLAP_IN is not None:
        left_pt = (MANUAL_LEFT_FLAP_IN or 0) * POINTS_PER_INCH
        right_pt = (MANUAL_RIGHT_FLAP_IN or 0) * POINTS_PER_INCH

        x0 = page_rect.x0 + left_pt
        x1 = page_rect.x1 - right_pt

        if x1 <= x0:
            info["reason"] = "manual flap widths are larger than page width"
            return page_rect, info

        clip = fitz.Rect(x0, page_rect.y0, x1, page_rect.y1)

        info.update({
            "detected": True,
            "reason": "manual override",
            "left_flap_pt": left_pt,
            "right_flap_pt": right_pt,
        })

        return clip, info

    # Aspect-ratio guard to avoid cropping normal covers.
    if page_aspect < MIN_PAGE_ASPECT_FOR_FLAPS:
        info["reason"] = (
            f"page aspect {page_aspect:.3f} is below "
            f"MIN_PAGE_ASPECT_FOR_FLAPS={MIN_PAGE_ASPECT_FOR_FLAPS}"
        )
        return page_rect, info

    zoom = DETECT_DPI / POINTS_PER_INCH

    pix = page.get_pixmap(
        matrix=fitz.Matrix(zoom, zoom),
        colorspace=fitz.csRGB,
        alpha=False,
    )

    arr = np.frombuffer(pix.samples, dtype=np.uint8)
    arr = arr.reshape(pix.height, pix.width, pix.n)
    rgb = arr[:, :, :3].astype(np.float32)

    # Dominant color per vertical column.
    # Median is used instead of mean so small text does not dominate detection.
    column_color = np.median(rgb, axis=0)

    # Smooth enough to ignore text/image details but preserve panel boundaries.
    smooth_window = max(9, int(pix.width * 0.01))
    column_color_smooth = smooth_columns(column_color, smooth_window)

    # Strong vertical changes in the smoothed color profile are likely folds.
    gradient = np.linalg.norm(np.diff(column_color_smooth, axis=0), axis=1)

    gradient = smooth_signal(
        gradient,
        max(5, int(pix.width * 0.002)),
    )

    baseline = float(np.median(gradient))
    min_required_score = max(0.01, baseline * SEAM_SCORE_MULTIPLIER)

    left_px, left_score = best_seam(
        gradient,
        LEFT_SEAM_SEARCH[0],
        LEFT_SEAM_SEARCH[1],
    )

    right_px, right_score = best_seam(
        gradient,
        RIGHT_SEAM_SEARCH[0],
        RIGHT_SEAM_SEARCH[1],
    )

    left_pt = left_px / zoom
    right_seam_pt = right_px / zoom
    right_flap_pt = page_rect.width - right_seam_pt

    left_ratio = left_pt / page_rect.width
    right_ratio = right_flap_pt / page_rect.width

    info.update({
        "left_flap_pt": left_pt,
        "right_flap_pt": right_flap_pt,
        "left_score": left_score,
        "right_score": right_score,
        "baseline_score": baseline,
        "min_required_score": min_required_score,
    })

    # Validate detected seams.
    if left_score < min_required_score or right_score < min_required_score:
        info["reason"] = "seam scores are too weak"
        return page_rect, info

    if not (MIN_FLAP_WIDTH_RATIO <= left_ratio <= MAX_FLAP_WIDTH_RATIO):
        info["reason"] = f"left flap ratio {left_ratio:.3f} is outside expected range"
        return page_rect, info

    if not (MIN_FLAP_WIDTH_RATIO <= right_ratio <= MAX_FLAP_WIDTH_RATIO):
        info["reason"] = f"right flap ratio {right_ratio:.3f} is outside expected range"
        return page_rect, info

    if abs(left_ratio - right_ratio) > MAX_FLAP_WIDTH_DIFF_RATIO:
        info["reason"] = (
            f"left/right flap width mismatch is too high: "
            f"{left_ratio:.3f} vs {right_ratio:.3f}"
        )
        return page_rect, info

    x0 = page_rect.x0 + left_pt + PADDING_PT
    x1 = page_rect.x1 - right_flap_pt - PADDING_PT

    if x1 <= x0:
        info["reason"] = "detected crop is invalid"
        return page_rect, info

    clip = fitz.Rect(x0, page_rect.y0, x1, page_rect.y1)

    info["detected"] = True
    info["reason"] = "flaps detected"

    return clip, info


def main():
    src = fitz.open(INPUT_PDF)
    out = fitz.open()

    out.set_metadata(src.metadata)

    for page_index, page in enumerate(src):
        page_rect = page.rect
        clip, info = detect_flap_clip(page)

        # Create output page exactly equal to kept area.
        # Destination size == clip size, so there is no artwork resizing.
        new_page = out.new_page(width=clip.width, height=clip.height)

        new_page.show_pdf_page(
            new_page.rect,
            src,
            page_index,
            clip=clip,
        )

        # Make all standard page boxes match the new page.
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
        print(f"  flaps removed: {info['detected']}")
        print(f"  reason: {info['reason']}")
        print(
            f"  removed: left={clip.x0 - page_rect.x0:.2f} pt "
            f"({pt_to_in(clip.x0 - page_rect.x0):.3f} in), "
            f"right={page_rect.x1 - clip.x1:.2f} pt "
            f"({pt_to_in(page_rect.x1 - clip.x1):.3f} in)"
        )

        if "baseline_score" in info:
            print(
                f"  seam scores: left={info['left_score']:.3f}, "
                f"right={info['right_score']:.3f}, "
                f"baseline={info['baseline_score']:.3f}, "
                f"required={info['min_required_score']:.3f}"
            )

    out.save(OUTPUT_PDF, garbage=4, deflate=True)
    out.close()
    src.close()

    print(f"\nSaved: {OUTPUT_PDF.resolve()}")


if __name__ == "__main__":
    main()