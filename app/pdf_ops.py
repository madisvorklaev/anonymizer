"""Core PDF manipulation: rendering pages for the UI, performing true
(content-removing) redaction with an encrypted, reversible snapshot, and
restoring a previously anonymized PDF from those snapshots."""
import io
import re
import secrets
from pathlib import Path

import fitz  # PyMuPDF
import qrcode

from . import crypto, db

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"

LABEL_RE = re.compile(r"\[REDACTED ([0-9a-f]{10})\]")


def _label_for(redaction_id: str) -> str:
    return f"[REDACTED {redaction_id}]"


def doc_path(doc_id: str) -> Path:
    return UPLOAD_DIR / f"{doc_id}.pdf"


def save_upload(doc_id: str, data: bytes) -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    doc_path(doc_id).write_bytes(data)


def page_count(doc_id: str) -> int:
    with fitz.open(doc_path(doc_id)) as d:
        return d.page_count


def render_page_png(doc_id: str, page_num: int, zoom: float = 1.6):
    """Returns (png_bytes, page_width_pts, page_height_pts) for display in the UI."""
    with fitz.open(doc_path(doc_id)) as d:
        page = d[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return pix.tobytes("png"), page.rect.width, page.rect.height


def _make_qr_png(data: str) -> bytes:
    qr = qrcode.QRCode(border=1, box_size=6)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def anonymize(doc_id: str, regions: list[dict]) -> Path:
    """regions: [{"page": int, "x0","y0","x1","y1"}] in PDF point space (top-left origin).

    For each region: snapshot the original pixels (encrypted + stored locally,
    keyed by a short redaction ID), then permanently strip the underlying
    text/graphics/images in that area (not just paint over them), and stamp
    the redaction ID (+ a small QR code, when there's room) in its place.
    """
    doc = fitz.open(doc_path(doc_id))
    by_page: dict[int, list[dict]] = {}
    for r in regions:
        by_page.setdefault(int(r["page"]), []).append(r)

    for page_num, page_regions in by_page.items():
        page = doc[page_num]
        prepared = []
        for r in page_regions:
            rect = fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"])
            rect.normalize()
            if rect.is_empty:
                continue
            snap_pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=rect)
            snapshot_png = snap_pix.tobytes("png")
            redaction_id = secrets.token_hex(5)
            encrypted = crypto.encrypt(snapshot_png)
            db.insert_redaction(
                redaction_id, doc_id, page_num,
                (rect.x0, rect.y0, rect.x1, rect.y1), encrypted,
            )
            prepared.append((rect, redaction_id))
            page.add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)

        if not prepared:
            continue

        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_PIXELS,
            graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
        )

        for rect, redaction_id in prepared:
            label = _label_for(redaction_id)
            qr_size = min(rect.width, rect.height) * 0.4
            text_rect = rect
            if qr_size >= 14:
                qr_rect = fitz.Rect(
                    rect.x0 + 1, rect.y0 + 1,
                    rect.x0 + 1 + qr_size, rect.y0 + 1 + qr_size,
                )
                page.insert_image(qr_rect, stream=_make_qr_png(redaction_id))
                text_rect = fitz.Rect(rect.x0 + qr_size + 3, rect.y0, rect.x1, rect.y1)
            fontsize = max(4, min(8, rect.height * 0.5))
            if text_rect.width > 2 and text_rect.height > 2:
                page.insert_textbox(
                    text_rect, label, fontsize=fontsize,
                    color=(0, 0, 0), align=1,
                )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{doc_id}_anonymized.pdf"
    doc.save(out_path, garbage=4, deflate=True)
    doc.close()
    return out_path


def restore(pdf_bytes: bytes) -> bytes:
    """Finds redaction IDs embedded in the PDF, decrypts the matching stored
    snapshots, and pastes them back over their original location."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    restored_any = False
    try:
        for page in doc:
            found_ids = set(LABEL_RE.findall(page.get_text("text")))
            for redaction_id in found_ids:
                row = db.get_redaction(redaction_id)
                if row is None:
                    continue
                _, _doc_id, _page_num, x0, y0, x1, y1, encrypted = row
                snapshot_png = crypto.decrypt(encrypted)
                rect = fitz.Rect(x0, y0, x1, y1)
                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), width=0)
                page.insert_image(rect, stream=snapshot_png)
                restored_any = True

        if not restored_any:
            raise ValueError(
                "No known redaction markers were found in this PDF "
                "(or their originals aren't in this app's local database)."
            )

        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()
    finally:
        doc.close()
