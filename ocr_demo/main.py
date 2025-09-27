# ocr_demo/main.py
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from .deps import get_engine
from .ocr.base import OcrEngine, OcrResult
import traceback
import httpx

app = FastAPI(title="OCR Demo API", version="0.2.0")

# CORS（联调阶段放开，生产请收紧）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

class OcrBody(BaseModel):
    file_url: Optional[HttpUrl] = None
    lang: str = "auto"
    return_boxes: bool = False

    # 新增：可在 JSON 里传参（可选）
    char_type: Optional[str] = None          # "default" | "en_sensitive"
    box_thresh: Optional[float] = None       # 0.3 ~ 0.6
    unclip_ratio: Optional[float] = None     # 1.6 ~ 2.2
    drop_score: Optional[float] = None       # 0.3 ~ 0.6
    max_text_length: Optional[int] = None    # e.g. 128
    preprocess: Optional[int] = None         # 0/1

@app.get("/healthz")
def healthz():
    return {"ok": True}

def _apply_engine_overrides(
    engine: OcrEngine,
    *,
    char_type: str,
    box_thresh: float,
    unclip_ratio: float,
    drop_score: float,
    max_text_length: int,
    preprocess: int,
):
    """
    将参数覆盖到 PaddleEngine 上，并清空内部缓存，确保下次获取的 PaddleOCR 实例用新配置。
    注意：这里用到了实现类的属性（约定自 paddle_impl.PaddleEngine）。
    """
    # 尽量温和地“尝试设置”，便于向后兼容
    for name, value in [
        ("_rec_char_type", char_type),
        ("_det_db_box_thresh", box_thresh),
        ("_det_db_unclip_ratio", unclip_ratio),
        ("_drop_score", drop_score),
        ("_max_text_length", max_text_length),
        ("_enable_preprocess", bool(preprocess)),
    ]:
        if hasattr(engine, name):
            setattr(engine, name, value)

    # 让新参数生效：清空缓存的 PaddleOCR 实例，按需重建
    if hasattr(engine, "_engines"):
        try:
            engine._engines.clear()  # type: ignore[attr-defined]
        except Exception:
            pass

@app.post("/v1/ocr")
async def ocr(
    # 原有参数
    lang: str = Query("auto"),
    return_boxes: bool = Query(False),

    # 新增可调参数（Query 优先于 Body）
    char_type: str = Query("en_sensitive", description="PaddleOCR rec_char_type"),
    box_thresh: float = Query(0.45, ge=0.0, le=1.0, description="det_db_box_thresh"),
    unclip_ratio: float = Query(1.90, gt=0.0, description="det_db_unclip_ratio"),
    drop_score: float = Query(0.30, ge=0.0, le=1.0, description="drop_score"),
    max_text_length: int = Query(128, gt=0, description="rec max_text_length"),
    preprocess: int = Query(1, ge=0, le=1, description="enable preprocess (0/1)"),

    file: Optional[UploadFile] = File(None),
    body: Optional[OcrBody] = Body(None),
    engine: OcrEngine = Depends(get_engine),
) -> OcrResult:
    """
    同步 OCR（图片单页）：支持 multipart 上传或 JSON(file_url)
    返回 OcrResult：{ text: str, boxes?: [{text,bbox,confidence}] }
    """
    # Body 合并（如 Body 提供但 Query 未显式给出，可用 Body 值）
    if body is not None:
        lang = body.lang or lang
        return_boxes = body.return_boxes if body.return_boxes is not None else return_boxes
        if body.char_type is not None:
            char_type = body.char_type
        if body.box_thresh is not None:
            box_thresh = body.box_thresh
        if body.unclip_ratio is not None:
            unclip_ratio = body.unclip_ratio
        if body.drop_score is not None:
            drop_score = body.drop_score
        if body.max_text_length is not None:
            max_text_length = body.max_text_length
        if body.preprocess is not None:
            preprocess = body.preprocess

    # 读取图像字节
    data: Optional[bytes] = None
    if file and file.filename:
        data = await file.read()
    elif body and body.file_url:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(str(body.file_url))
            if resp.status_code != 200:
                raise HTTPException(400, f"failed to download file_url: {resp.status_code}")
            data = resp.content
        except httpx.HTTPError as e:
            raise HTTPException(400, f"download error: {e!s}")
    else:
        raise HTTPException(400, "file or file_url is required")

    if not data:
        raise HTTPException(400, "empty file data")

    # 将调参应用到后端引擎（即时生效）
    _apply_engine_overrides(
        engine,
        char_type=char_type,
        box_thresh=box_thresh,
        unclip_ratio=unclip_ratio,
        drop_score=drop_score,
        max_text_length=max_text_length,
        preprocess=preprocess,
    )

    try:
        result = engine.recognize(data, lang=lang, return_boxes=return_boxes)
        return result
    except Exception as e:
        # 避免把完整堆栈暴露给客户端
        traceback.print_exc()
        raise HTTPException(500, f"ocr failed: {e!s}")

@app.post("/v1/ocr/submit")
def ocr_submit():
    """
    异步升级位：将来对接队列（如 Celery/RQ）后返回 job_id，
    并新增 GET /v1/jobs/{id} 查询。
    """
    raise HTTPException(501, "async submit not implemented yet")

# 便于本地直接运行：python -m ocr_demo.main
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("ocr_demo.main:app", host="0.0.0.0", port=8000, reload=True)
