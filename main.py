# main.py
# Lightweight FastAPI service exposing the cover/interior PDF fixers.
# Bytes in, bytes out: the PDF is sent as the raw request body and the fixed
# PDF is returned as the raw response body. No files are written to disk.
#
# Run:
#   uvicorn main:app --host 0.0.0.0 --port 8000

import os

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from fix_cover import fix_cover
from fix_interior_file import fix_interior_file

app = FastAPI(title="PDF Fix Service")

PDF_MEDIA_TYPE = "application/pdf"
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# Allow the browser to call this API directly (no Node proxy). Override with
# ALLOW_ORIGINS=https://foo.com,https://bar.com ; default "*" for any origin.
_origins = os.environ.get("ALLOW_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    # Serve the UI from the same origin as the API (no CORS/mixed-content issues).
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


async def _read_pdf_body(request: Request) -> bytes:
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="empty request body")
    return body


@app.post("/fix-cover")
async def fix_cover_endpoint(
    request: Request,
    width_in: float = Query(..., gt=0, description="Final cover width in inches"),
    height_in: float = Query(..., gt=0, description="Final cover height in inches"),
) -> Response:
    body = await _read_pdf_body(request)
    try:
        data = await run_in_threadpool(fix_cover, body, width_in, height_in)
    except Exception as exc:  # malformed/unsupported PDF -> 400, not 500
        raise HTTPException(status_code=400, detail=f"failed to process PDF: {exc}")
    return Response(content=data, media_type=PDF_MEDIA_TYPE)


@app.post("/fix-interior")
async def fix_interior_endpoint(request: Request) -> Response:
    body = await _read_pdf_body(request)
    try:
        data = await run_in_threadpool(fix_interior_file, body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"failed to process PDF: {exc}")
    return Response(content=data, media_type=PDF_MEDIA_TYPE)
