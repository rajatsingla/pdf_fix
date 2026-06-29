# resize_pdf_final.py
# pip install pymupdf

from pathlib import Path
import fitz  # PyMuPDF

INPUT_PDF = Path("yo3.pdf")
OUTPUT_PDF = Path("yoyo3.pdf")

TARGET_WIDTH_IN = 5.5
TARGET_HEIGHT_IN = 8.5
POINTS_PER_INCH = 72


def resize_doc(doc: fitz.Document, target_w_in: float, target_h_in: float) -> fitz.Document:
    """
    Scale every page of ``doc`` to the target size in inches.

    The page contents are wrapped in a single reusable scaling transform, so
    artwork is scaled (not rasterized) and all standard page boxes are updated.
    Assumes uniform page sizes; scaling is computed from the first page.
    Mutates and returns ``doc``.
    """
    target_w = target_w_in * POINTS_PER_INCH
    target_h = target_h_in * POINTS_PER_INCH

    # Pages are uniform, so calculate scaling from the first page.
    old_w = doc[0].mediabox.width
    old_h = doc[0].mediabox.height

    sx = target_w / old_w
    sy = target_h / old_h

    # Add one reusable scaling wrapper around existing page contents.
    prefix_xref = doc.get_new_xref()
    doc.update_object(prefix_xref, "<<>>")
    doc.update_stream(
        prefix_xref,
        f"q\n{sx:.12g} 0 0 {sy:.12g} 0 0 cm\n".encode("ascii")
    )

    suffix_xref = doc.get_new_xref()
    doc.update_object(suffix_xref, "<<>>")
    doc.update_stream(suffix_xref, b"\nQ\n")

    new_box = f"[0 0 {target_w:.12g} {target_h:.12g}]"

    for page in doc:
        original_contents = page.get_contents()

        # Wrap original content in the scaling transform.
        if original_contents:
            contents_refs = (
                [f"{prefix_xref} 0 R"]
                + [f"{xref} 0 R" for xref in original_contents]
                + [f"{suffix_xref} 0 R"]
            )
            doc.xref_set_key(page.xref, "Contents", "[" + " ".join(contents_refs) + "]")

        # Set all standard page boxes to the target size.
        for box_name in ("MediaBox", "CropBox", "TrimBox", "BleedBox", "ArtBox"):
            doc.xref_set_key(page.xref, box_name, new_box)

    return doc


def main():
    doc = fitz.open(INPUT_PDF)

    resize_doc(doc, TARGET_WIDTH_IN, TARGET_HEIGHT_IN)

    doc.save(OUTPUT_PDF)
    doc.close()

    print(f"Saved: {OUTPUT_PDF.resolve()}")


if __name__ == "__main__":
    main()
