from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image

from .image_pipeline import CropBox, build_export, crop_and_resize, detect_crops, grid_crops, image_bytes, load_png, safe_folder_name


BASE_DIR = Path(__file__).resolve().parent
SESSION_TTL_SECONDS = 2 * 60 * 60
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@dataclass
class WorkSession:
    image: Image.Image
    boxes: list[CropBox]
    source_name: str
    created_at: float


class ExportItem(BaseModel):
    crop_index: int = Field(ge=0)
    name: str
    box: dict[str, int] | None = None


class ExportRequest(BaseModel):
    session_id: str
    folder_name: str
    items: list[ExportItem]


app = FastAPI(title="表情切切", version="1.0.0")
sessions: dict[str, WorkSession] = {}


def _session(session_id: str) -> WorkSession:
    current = sessions.get(session_id)
    if current is None or time.time() - current.created_at > SESSION_TTL_SECONDS:
        sessions.pop(session_id, None)
        raise HTTPException(status_code=404, detail="处理记录已过期，请重新上传")
    return current


def _cleanup_sessions() -> None:
    cutoff = time.time() - SESSION_TTL_SECONDS
    for key in [key for key, value in sessions.items() if value.created_at < cutoff]:
        sessions.pop(key, None)


async def _read_upload(file: UploadFile) -> bytes:
    """流式读取上传内容，超过 25 MB 立即拒绝，避免把超大文件整体读入内存。"""
    data = bytearray()
    while chunk := await file.read(1024 * 1024):
        data.extend(chunk)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=422, detail="PNG 文件不能超过 25 MB")
    return bytes(data)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    mode: str = Form("auto"),
    rows: int = Form(2),
    columns: int = Form(2),
) -> dict[str, object]:
    _cleanup_sessions()
    try:
        image = load_png(await _read_upload(file))
        boxes = grid_crops(image, rows, columns) if mode == "grid" else detect_crops(image)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    session_id = uuid.uuid4().hex
    source_stem = safe_folder_name(Path(file.filename or "表情包").stem)
    sessions[session_id] = WorkSession(image, boxes, source_stem, time.time())
    return {
        "session_id": session_id,
        "source_name": source_stem,
        "width": image.width,
        "height": image.height,
        "boxes": [box.as_dict() for box in boxes],
    }


@app.get("/api/session/{session_id}/source")
def source_image(session_id: str) -> Response:
    current = _session(session_id)
    return Response(image_bytes(current.image), media_type="image/png")


@app.get("/api/session/{session_id}/crop/{crop_index}")
def crop_image(session_id: str, crop_index: int) -> Response:
    current = _session(session_id)
    if not 0 <= crop_index < len(current.boxes):
        raise HTTPException(status_code=404, detail="裁剪图片不存在")
    result = crop_and_resize(current.image, current.boxes[crop_index], 300)
    return Response(image_bytes(result), media_type="image/png")


@app.post("/api/export")
def export(request: ExportRequest) -> StreamingResponse:
    current = _session(request.session_id)
    try:
        content = build_export(
            current.image,
            current.boxes,
            [
                (
                    item.crop_index,
                    item.name.strip(),
                    item.box,
                )
                for item in request.items
            ],
            request.folder_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    filename = f"{safe_folder_name(request.folder_name)}.zip"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    return StreamingResponse(content, media_type="application/zip", headers=headers)


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
