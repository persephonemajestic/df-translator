"""Цвета фона и текста под надписью на снимке — чтобы перевод лёг «на место» оригинала."""
from __future__ import annotations


def sample_colors(image, x0: float, y0: float, x1: float, y1: float):
    """image — BGR numpy (как от mss). Возвращает (bg, fg) в RGB или (None, None)."""
    try:
        import numpy as np

        h, w = image.shape[:2]
        x0, y0 = max(0, int(x0)), max(0, int(y0))
        x1, y1 = min(w, int(x1) + 1), min(h, int(y1) + 1)
        if x1 - x0 < 2 or y1 - y0 < 2:
            return None, None
        m = 3
        parts = []
        if y0 - m >= 0:
            parts.append(image[y0 - m:y0, x0:x1])
        if y1 + m <= h:
            parts.append(image[y1:y1 + m, x0:x1])
        if x0 - m >= 0:
            parts.append(image[y0:y1, x0 - m:x0])
        if x1 + m <= w:
            parts.append(image[y0:y1, x1:x1 + m])
        if not parts:  # надпись во весь снимок — берём края самой области
            box = image[y0:y1, x0:x1]
            parts = [box[:1], box[-1:], box[:, :1], box[:, -1:]]
        ring = np.concatenate([p.reshape(-1, image.shape[2])[:, :3] for p in parts if p.size], axis=0)
        bg = np.median(ring, axis=0)
        inside = image[y0:y1, x0:x1].reshape(-1, image.shape[2])[:, :3].astype(np.float32)
        dist = np.abs(inside - bg).sum(axis=1)
        thr = np.percentile(dist, 85)
        text_px = inside[dist >= max(thr, 60)]
        fg = np.median(text_px, axis=0) if len(text_px) else None
        to_rgb = lambda c: (int(c[2]), int(c[1]), int(c[0]))  # noqa: E731
        return to_rgb(bg), (to_rgb(fg) if fg is not None else None)
    except Exception:  # noqa: BLE001 — цвет не критичен
        return None, None


def readable_fg(bg, fg):
    """Цвет текста: как у оригинала, если он контрастный, иначе белый/тёмный по яркости фона."""
    lum = lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]  # noqa: E731
    if bg is None:
        return (238, 240, 245)
    if fg is not None and abs(lum(fg) - lum(bg)) >= 90:
        return fg
    return (20, 22, 26) if lum(bg) > 150 else (240, 242, 246)


def free_room(image, x0: float, y0: float, x1: float, y1: float, bg, limit: int = 1200) -> tuple[int, int]:
    """Докуда вправо и вниз от надписи тянется тот же фон (край панели, рамка, соседний текст).
    Возвращает (правая граница, нижняя граница) в координатах снимка — дальше плашку не растягиваем."""
    try:
        import numpy as np

        if bg is None:
            return image.shape[1], image.shape[0]
        h, w = image.shape[:2]
        ref = np.array([bg[2], bg[1], bg[0]], dtype=np.int32)   # bg в RGB, снимок в BGR
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)

        def first_edge(line) -> int | None:
            """Индекс начала первой серии из 3 пикселей «не фона» (векторно — быстро)."""
            if len(line) < 3:
                return None
            bad = np.abs(line[:, :3].astype(np.int32) - ref).sum(axis=1) > 70
            run = bad[:-2] & bad[1:-1] & bad[2:]
            idx = np.flatnonzero(run)
            return int(idx[0]) if len(idx) else None

        right = min(w, x1 + limit)
        start_x = min(w - 1, x1 + 3)
        for r in {y0 + 1, (y0 + y1) // 2, y1 - 1}:
            if 0 <= r < h:
                e = first_edge(image[r, start_x:right])
                if e is not None:
                    right = min(right, start_x + e)
        bottom = min(h, y1 + limit)
        start_y = min(h - 1, y1 + 3)
        for c in {x0 + 1, (x0 + x1) // 2, x1 - 1}:
            if 0 <= c < w:
                e = first_edge(image[start_y:bottom, c])
                if e is not None:
                    bottom = min(bottom, start_y + e)
        return int(right), int(bottom)
    except Exception:  # noqa: BLE001
        return image.shape[1], image.shape[0]
