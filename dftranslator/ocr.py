"""OCR: RapidOCR (PaddleOCR-модели в ONNX), работает локально, без видеокарты.

Поддерживаются обе линейки пакета:
  rapidocr_onnxruntime (1.x, модели внутри пакета, Python <= 3.12)
  rapidocr             (2.x/3.x, модели докачиваются при первом запуске)
"""
from __future__ import annotations

import numpy as np

from .blocks import OcrLine, box_to_rect


class OcrUnavailable(RuntimeError):
    pass


class OcrEngine:
    def __init__(self, min_score: float = 0.55):
        self.min_score = min_score
        self._engine = None
        self._api = None

    def _ensure(self) -> None:
        if self._engine is not None:
            return
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore

            self._engine, self._api = RapidOCR(), "v1"
            return
        except ImportError:
            pass
        try:
            from rapidocr import RapidOCR  # type: ignore

            self._engine, self._api = RapidOCR(), "v2"
        except ImportError as exc:
            raise OcrUnavailable(
                "Не найден OCR. Установите: pip install rapidocr-onnxruntime "
                "(Python 3.10–3.12) или pip install rapidocr onnxruntime"
            ) from exc

    def warmup(self) -> None:
        self._ensure()

    def read(self, image_bgr: np.ndarray, scale: float = 1.0) -> list[OcrLine]:
        self._ensure()
        img = image_bgr
        if scale and abs(scale - 1.0) > 1e-3:
            import cv2  # приходит вместе с rapidocr

            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        raw = self._run(img)
        lines: list[OcrLine] = []
        for box, text, score in raw:
            if not text or score < self.min_score:
                continue
            x0, y0, x1, y1 = box_to_rect(box)
            lines.append(OcrLine(x0 / scale, y0 / scale, x1 / scale, y1 / scale, str(text), float(score)))
        return lines

    def _run(self, img: np.ndarray) -> list[tuple]:
        if self._api == "v1":
            result, _ = self._engine(img)
            return [(r[0], r[1], float(r[2])) for r in (result or [])]
        out = self._engine(img)
        if getattr(out, "boxes", None) is None or getattr(out, "txts", None) is None:
            return []
        return [(b, t, float(s)) for b, t, s in zip(out.boxes, out.txts, out.scores)]


def region_scale(width: int, height: int) -> float:
    """Маленькие выделенные области лучше распознаются после увеличения."""
    if height < 60 or width < 220:
        return 3.0
    if height < 140:
        return 2.0
    if height < 260:
        return 1.5
    return 1.0
