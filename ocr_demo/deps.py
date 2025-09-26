# ocr_demo/deps.py
import os
from functools import lru_cache

from .ocr.base import OcrEngine
from .ocr.paddle_impl import PaddleEngine

@lru_cache(maxsize=1)
def get_engine() -> OcrEngine:
    """
    获取 OCR 引擎实例（单例缓存）
    - 默认使用 PaddleEngine
    - 可通过环境变量 OCR_ENGINE / OCR_LANG 控制
    """
    engine_type = os.getenv("OCR_ENGINE", "paddle")  # 未来可扩展：cloud, mock 等
    lang = os.getenv("OCR_LANG", "ch")              # 默认中文模型
    
    if engine_type == "paddle":
        return PaddleEngine(lang=lang, use_gpu=False)
    else:
        # 预留扩展：云 OCR 引擎
        raise NotImplementedError(f"OCR engine '{engine_type}' is not implemented yet")
