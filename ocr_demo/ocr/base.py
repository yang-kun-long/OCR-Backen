# ocr_demo/ocr/base.py
from typing import List, Optional, TypedDict
from typing_extensions import TypedDict

class Box(TypedDict):
    text: str
    bbox: List[int]  # [x1, y1, x2, y2]
    confidence: float

class OcrResult(TypedDict):
    text: str
    boxes: Optional[List[Box]]

class OcrEngine:
    """
    OCR 引擎抽象基类
    不同实现（本地 PaddleOCR / 云 OCR）都要继承并实现 recognize 方法
    """
    def recognize(
        self, 
        image_bytes: bytes, 
        lang: str = "auto", 
        return_boxes: bool = False
    ) -> OcrResult:
        raise NotImplementedError("OCR engine must implement recognize()")
