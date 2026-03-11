import re

import cv2
import numpy as np
import pytesseract

PROFILES: dict[str, str] = {
    "auto": "Auto (all passes, max recall)",
    "clear": "Clear Photo (fast)",
    "embossed": "Embossed Plastic",
    "raw": "Raw (no preprocessing)",
}


# ---------------------------------------------------------------------------
# Tesseract wrapper
# ---------------------------------------------------------------------------

def _run_tesseract(img: np.ndarray, psm: int = 11) -> list[dict]:
    data = pytesseract.image_to_data(
        img,
        config=f"--psm {psm} --oem 3 -c tessedit_char_whitelist=0123456789",
        output_type=pytesseract.Output.DICT,
    )
    results = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = int(data["conf"][i])
        if not text or conf < 25:
            continue
        if not re.fullmatch(r"\d+", text):
            continue
        num = int(text)
        if not (1 <= num <= 999):
            continue
        results.append({
            "number": num,
            "px_x": data["left"][i],
            "px_y": data["top"][i],
            "px_w": data["width"][i],
            "px_h": data["height"][i],
            "confidence": conf,
        })
    return results


# ---------------------------------------------------------------------------
# Pre-processing helpers — each returns a uint8 grayscale image
# ---------------------------------------------------------------------------

def _prep_clahe_thresh(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )


def _prep_emboss(gray: np.ndarray) -> np.ndarray:
    """6-direction emboss with absolute max response + CLAHE."""
    kernels = [
        np.array([[-2, -1, 0], [-1, 0, 1], [0, 1, 2]], dtype=np.float32),
        np.array([[0, -1, -2], [1, 0, -1], [2, 1, 0]], dtype=np.float32),
        np.array([[2, 1, 0], [1, 0, -1], [0, -1, -2]], dtype=np.float32),
        np.array([[0, 1, 2], [-1, 0, 1], [-2, -1, 0]], dtype=np.float32),
        np.array([[-1, -1, -1], [0, 0, 0], [1, 1, 1]], dtype=np.float32),
        np.array([[-1, 0, 1], [-1, 0, 1], [-1, 0, 1]], dtype=np.float32),
    ]
    src = gray.astype(np.float32)
    acc = np.zeros(gray.shape, dtype=np.float32)
    for k in kernels:
        acc = np.maximum(acc, np.abs(cv2.filter2D(src, -1, k)))
    result = cv2.normalize(acc, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8)).apply(result)


def _prep_tophat(gray: np.ndarray) -> np.ndarray:
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
    th = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
    return cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8)).apply(th)


def _prep_blackhat(gray: np.ndarray) -> np.ndarray:
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
    bh = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    return cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8)).apply(bh)


def _prep_sobel(gray: np.ndarray) -> np.ndarray:
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.sqrt(gx ** 2 + gy ** 2)
    mag = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8)).apply(mag)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _iou(a: dict, b: dict) -> float:
    ax1, ay1 = a["px_x"], a["px_y"]
    ax2, ay2 = ax1 + a["px_w"], ay1 + a["px_h"]
    bx1, by1 = b["px_x"], b["px_y"]
    bx2, by2 = bx1 + b["px_w"], by1 + b["px_h"]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union else 0.0


def _merge(detections: list[dict]) -> list[dict]:
    merged, used = [], [False] * len(detections)
    for i, det in enumerate(detections):
        if used[i]:
            continue
        group = [det]
        used[i] = True
        for j, other in enumerate(detections):
            if not used[j] and i != j and det["number"] == other["number"] and _iou(det, other) > 0.3:
                group.append(other)
                used[j] = True
        merged.append(max(group, key=lambda d: d["confidence"]))
    return merged


# ---------------------------------------------------------------------------
# Profile-specific detection sets
# ---------------------------------------------------------------------------

def _detect_clear(gray: np.ndarray, sharp: np.ndarray) -> list[dict]:
    """2 passes — good for clear, well-lit photos."""
    thresh = _prep_clahe_thresh(sharp)
    return _run_tesseract(thresh) + _run_tesseract(cv2.bitwise_not(thresh))


def _detect_embossed(gray: np.ndarray, sharp: np.ndarray) -> list[dict]:
    """5 passes — emphasises surface relief features."""
    embossed = _prep_emboss(gray)
    _, emboss_bin = cv2.threshold(embossed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    results = (
        _run_tesseract(embossed)
        + _run_tesseract(emboss_bin)
        + _run_tesseract(_prep_tophat(gray))
        + _run_tesseract(_prep_blackhat(gray))
        + _run_tesseract(_prep_sobel(sharp))
    )
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _load_and_prep(image_path: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not load image: {image_path}")
    h0, w0 = img.shape[:2]
    if w0 > 2000:
        img = cv2.resize(img, (2000, int(h0 * 2000 / w0)), interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    gray_raw = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray_raw, d=9, sigmaColor=75, sigmaSpace=75)
    blur = cv2.GaussianBlur(gray, (0, 0), 3)
    sharp = cv2.addWeighted(gray, 1.5, blur, -0.5, 0)
    return gray_raw, gray, sharp, w, h


def process_image(image_path: str, profile: str = "auto") -> list[dict]:
    gray_raw, gray, sharp, w, h = _load_and_prep(image_path)

    if profile == "raw":
        raw = _run_tesseract(gray_raw)
    elif profile == "clear":
        raw = _detect_clear(gray, sharp)
    elif profile == "embossed":
        raw = _detect_embossed(gray, sharp)
    else:  # auto
        raw = _detect_clear(gray, sharp) + _detect_embossed(gray, sharp)

    return [
        {
            "number": d["number"],
            "x": d["px_x"] / w,
            "y": d["px_y"] / h,
            "width": d["px_w"] / w,
            "height": d["px_h"] / h,
            "confidence": d["confidence"],
        }
        for d in _merge(raw)
    ]


def get_debug_preview(image_path: str, profile: str = "auto") -> bytes:
    """
    Return a JPEG showing the key preprocessed images for the given profile.
    No OCR is re-run — this is a pure visual aid.
    """
    gray_raw, gray, sharp, _, _ = _load_and_prep(image_path)

    if profile == "raw":
        panels = [("Raw Grayscale (no preprocessing)", gray_raw)]
    elif profile == "clear":
        thresh = _prep_clahe_thresh(sharp)
        panels = [
            ("CLAHE + Adaptive Threshold", thresh),
            ("Inverted Threshold", cv2.bitwise_not(thresh)),
        ]
    elif profile == "embossed":
        panels = [
            ("Emboss (6-dir, abs-max)", _prep_emboss(gray)),
            ("Top-hat (raised features)", _prep_tophat(gray)),
            ("Black-hat (recessed features)", _prep_blackhat(gray)),
            ("Sobel Gradient Magnitude", _prep_sobel(sharp)),
        ]
    else:  # auto
        thresh = _prep_clahe_thresh(sharp)
        panels = [
            ("CLAHE + Adaptive Threshold", thresh),
            ("Inverted Threshold", cv2.bitwise_not(thresh)),
            ("Emboss (6-dir, abs-max)", _prep_emboss(gray)),
            ("Top-hat (raised features)", _prep_tophat(gray)),
        ]

    return _make_preview_grid(panels)


def _make_preview_grid(panels: list[tuple[str, np.ndarray]]) -> bytes:
    CELL_H = 480
    LABEL_H = 26

    cells = []
    for label, img in panels:
        h, w = img.shape[:2]
        cell_w = int(w * CELL_H / h)
        resized = cv2.resize(img, (cell_w, CELL_H), interpolation=cv2.INTER_AREA)
        bgr = cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR)
        bar = np.zeros((LABEL_H, cell_w, 3), dtype=np.uint8)
        cv2.putText(bar, label, (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 1, cv2.LINE_AA)
        cells.append(np.vstack([bar, bgr]))

    n = len(cells)
    if n <= 2:
        grid = np.hstack(cells)
    else:
        # 2-column grid — ensure all cells have the same width
        cw = cells[0].shape[1]
        row1 = np.hstack(cells[:2])
        row2_imgs = cells[2:4]
        # Pad last row to 2 if odd number of panels
        if len(row2_imgs) < 2:
            row2_imgs.append(np.zeros((cells[0].shape[0], cw, 3), dtype=np.uint8))
        row2 = np.hstack(row2_imgs)
        grid = np.vstack([row1, row2])

    _, buf = cv2.imencode(".jpg", grid, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return bytes(buf)
