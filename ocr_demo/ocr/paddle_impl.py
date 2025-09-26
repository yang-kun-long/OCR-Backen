# ocr_demo/ocr/paddle_impl.py
from typing import List, Dict, Tuple, Optional
import numpy as np
import cv2

from .base import OcrEngine, OcrResult, Box

# 轻量依赖：首次调用会自动下载 PaddleOCR 模型
from paddleocr import PaddleOCR

# 语言映射：演示优先中文。需要更细的中英混合可将 "ch_en" 映射到 "ch" 的 v4_server 模型。
_LANG_MAP = {
    "auto": "ch",
    "ch": "ch",
    "en": "en",
    "ch_en": "ch",
}

def _quad_to_xyxy(box_pts) -> List[int]:
    """
    box_pts: 4 点坐标 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    转换为 [x_min, y_min, x_max, y_max]
    """
    xs = [p[0] for p in box_pts]
    ys = [p[1] for p in box_pts]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


class PaddleEngine(OcrEngine):
    """
    本地 OCR 引擎（PaddleOCR）
    - 默认实例化一个中文模型
    - 按需缓存其它语言实例，避免反复下载/初始化
    - 增强：更敏感的字符集、放宽 drop_score、可选图像预处理
    """

    def __init__(
        self,
        lang: str = "ch",
        det: bool = True,
        rec: bool = True,
        use_gpu: bool = False,
        # —— 符号友好参数（可按需微调）——
        det_db_box_thresh: float = 0.45,
        det_db_unclip_ratio: float = 1.90,
        rec_char_type: str = "en_sensitive",
        drop_score: float = 0.30,
        use_space_char: bool = True,
        max_text_length: int = 128,
        # 预处理开关
        enable_preprocess: bool = True,
    ):
        self._det = det
        self._rec = rec
        self._use_gpu = use_gpu

        self._det_db_box_thresh = det_db_box_thresh
        self._det_db_unclip_ratio = det_db_unclip_ratio
        self._rec_char_type = rec_char_type
        self._drop_score = drop_score
        self._use_space_char = use_space_char
        self._max_text_length = max_text_length

        self._enable_preprocess = enable_preprocess

        # 以 (lang_key) 为键缓存实例；如需按参数区分，可把关键参数并入键
        self._engines: Dict[str, PaddleOCR] = {}

        # 预热一个默认实例
        lang_key = _LANG_MAP.get(lang, "ch")
        self._engines[lang_key] = self._build_engine(lang_key)

    def _build_engine(self, lang_key: str) -> PaddleOCR:
        """
        构造 PaddleOCR 引擎，带更适合符号的参数
        """
        return PaddleOCR(
            use_angle_cls=True,
            lang=lang_key,
            show_log=False,
            det=self._det,
            rec=self._rec,
            use_gpu=self._use_gpu,
            # —— 检测器（DB）参数 —— 让检测框更稳，符号不被切
            det_db_box_thresh=self._det_db_box_thresh,
            det_db_unclip_ratio=self._det_db_unclip_ratio,
            # —— 识别器参数 —— 让符号更全
            rec_char_type=self._rec_char_type,
            use_space_char=self._use_space_char,
            drop_score=self._drop_score,
            max_text_length=self._max_text_length,
        )

    def _get_engine(self, lang_key: str = "ch") -> PaddleOCR:
        if lang_key not in self._engines:
            # 懒加载并缓存不同语言的实例
            self._engines[lang_key] = self._build_engine(lang_key)
        return self._engines[lang_key]

    # -------- 轻量图像预处理：让细小符号更清晰（可关闭） --------
    def _preprocess(self, img: np.ndarray) -> np.ndarray:
        """
        预处理策略：
          1) 统一较高文本高度（避免细符号被压扁）
          2) 双边滤波去噪
          3) CLAHE 提升对比度
          4) 轻度二值 + 细粒度闭运算，避免细符号断裂
        """
        try:
            h, w = img.shape[:2]

            # 1) 提升到目标高度（不过度放大，<=3x）
            target_h = 48
            scale = target_h / max(1, h)
            if scale > 1.0 and scale <= 3.0:
                img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

            # 2) 灰度 & 去噪
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.bilateralFilter(gray, d=5, sigmaColor=30, sigmaSpace=30)

            # 3) 自适应对比度（增强细符号）
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)

            # 4) 轻度阈值（OTSU）
            thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

            # 5) 细粒度闭运算，修补细小断裂
            kernel = np.ones((1, 1), np.uint8)
            thr = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, kernel, iterations=1)

            # 回到 3 通道
            proc = cv2.cvtColor(thr, cv2.COLOR_GRAY2BGR)
            return proc
        except Exception:
            # 任意错误则退回原图，避免影响主流程
            return img

    def recognize(self, image_bytes: bytes, lang: str = "auto", return_boxes: bool = False) -> OcrResult:
        # 解析语言
        lang_key = _LANG_MAP.get(lang, "ch")
        engine = self._get_engine(lang_key)

        # 解码图像（支持常见格式：jpg/png/webp…）
        img_array = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image bytes. Unsupported or corrupted image data.")

        # 预处理（可选）
        if self._enable_preprocess:
            img = self._preprocess(img)

        # 运行 OCR（单张图）
        # 返回结构：list[ page -> list[ (boxPts, (text, score)) ] ]
        ocr_out = engine.ocr(img, cls=True)

        lines: List[str] = []
        boxes: List[Box] = []

        for page in ocr_out:
            for item in page:
                box_pts, (text, score) = item
                lines.append(text)
                if return_boxes:
                    xyxy = _quad_to_xyxy(box_pts)
                    boxes.append({"text": text, "bbox": xyxy, "confidence": float(score)})

        return {"text": "\n".join(lines), "boxes": boxes if return_boxes else None}
