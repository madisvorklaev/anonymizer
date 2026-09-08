import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import pdf_ops

app = FastAPI(title="PDF Anonymizer")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class Region(BaseModel):
    page: int
    x0: float
    y0: float
    x1: float
    y1: float


class AnonymizeRequest(BaseModel):
    doc_id: str
    regions: list[Region]


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")
    data = await file.read()
    doc_id = uuid.uuid4().hex
    pdf_ops.save_upload(doc_id, data)
    try:
        count = pdf_ops.page_count(doc_id)
    except Exception:
        pdf_ops.doc_path(doc_id).unlink(missing_ok=True)
        raise HTTPException(400, "Could not read this file as a PDF.")
    return {"doc_id": doc_id, "page_count": count, "filename": file.filename}


@app.get("/api/page/{doc_id}/{page_num}")
def get_page(doc_id: str, page_num: int):
    if not pdf_ops.doc_path(doc_id).exists():
        raise HTTPException(404, "Unknown document.")
    try:
        png_bytes, w, h = pdf_ops.render_page_png(doc_id, page_num)
    except Exception:
        raise HTTPException(404, "Page not found.")
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"X-Page-Width-Pts": str(w), "X-Page-Height-Pts": str(h)},
    )


@app.post("/api/anonymize")
def anonymize(req: AnonymizeRequest):
    if not pdf_ops.doc_path(req.doc_id).exists():
        raise HTTPException(404, "Unknown document.")
    if not req.regions:
        raise HTTPException(400, "No regions selected.")
    regions = [r.model_dump() for r in req.regions]
    out_path = pdf_ops.anonymize(req.doc_id, regions)
    return FileResponse(out_path, media_type="application/pdf", filename="anonymized.pdf")


@app.post("/api/restore")
async def restore(file: UploadFile = File(...)):
    data = await file.read()
    try:
        restored = pdf_ops.restore(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Could not process this PDF.")
    return Response(
        content=restored,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=restored.pdf"},
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
