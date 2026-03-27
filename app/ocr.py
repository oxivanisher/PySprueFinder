import re

import cv2
import numpy as np
import pytesseract

PROFILES: dict[str, str] = {
    "auto": "Auto (all profiles, font-filtered union)",
    "clear": "Clear Photo",
    "retinex": "Retinex (illumination normalisation)",
    "embossed": "Embossed Plastic",
    "bw": "Black & White (Otsu threshold)",
    "raw": "Raw (no preprocessing)",
}

# Profiles combined in "auto" mode.
_AUTO_CANDIDATES = ("clear", "retinex", "embossed", "bw", "raw")

# Upscale factor applied before every Tesseract call.
# Doubles the apparent size of text — critical for small sprue numbers.
_OCR_UPSCALE = 2.0


# ---------------------------------------------------------------------------
# Tesseract wrapper
# ---------------------------------------------------------------------------

def _run_tesseract(img: np.ndarray, psm: int = 11) -> list[dict]:
    """
    Upscale the image by _OCR_UPSCALE before passing to Tesseract, then map
    bounding boxes back to the original pixel space.  Upscaling is the single
    most effective way to improve detection of small sprue numbers.
    """
    scale = _OCR_UPSCALE
    h, w = img.shape[:2]
    large = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    data = pytesseract.image_to_data(
        large,
        config=f"--psm {psm} --oem 3 -c tessedit_char_whitelist=0123456789",
        output_type=pytesseract.Output.DICT,
    )
    results = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = int(data["conf"][i])
        if not text or conf < 15:
            continue
        if not re.fullmatch(r"\d+", text):
            continue
        num = int(text)
        if not (1 <= num <= 999):
            continue
        results.append({
            "number": num,
            # Map coordinates back to the original (pre-upscale) pixel space
            "px_x": int(data["left"][i] / scale),
            "px_y": int(data["top"][i] / scale),
            "px_w": int(data["width"][i] / scale),
            "px_h": int(data["height"][i] / scale),
            "confidence": conf,
        })
    return results


# ---------------------------------------------------------------------------
# Pre-processing helpers — each returns a uint8 grayscale image
# ---------------------------------------------------------------------------

def _prep_clahe_thresh(gray: np.ndarray, block_size: int = 11) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, 2
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


def _prep_bw_fixed(gray: np.ndarray, threshold: int) -> np.ndarray:
    """Binary threshold at a fixed intensity value after a mild Gaussian blur."""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, bw = cv2.threshold(blurred, threshold, 255, cv2.THRESH_BINARY)
    return bw


# Threshold values swept by _detect_bw.
# Covers the full range from mid-tone (catches dark parts vs grey sprue) up to
# near-white (separates embossed numbers from the sprue background).
# Steps of ~18 give 7 levels; both polarities → 14 Tesseract passes total.
_BW_THRESHOLDS: tuple[int, ...] = tuple(range(110, 219, 18))  # 110,128,146,164,182,200,218


def _prep_retinex(gray: np.ndarray, sigma: float) -> np.ndarray:
    """
    Single-scale Retinex: log(I) - gaussian_blur(log(I)), then rescaled to 0-255.

    Retinex separates illumination from reflectance.  On a sprue the background
    is a smooth, slowly-varying illumination field while the embossed numbers are
    sharp local reflectance changes.  Subtracting the blurred log image removes
    the low-frequency illumination and leaves the fine text detail behind, making
    numbers visible even where contrast is very low.

    sigma controls the scale of the illumination estimate:
      - small sigma (~30)  → tight local normalisation, catches fine structure
      - large sigma (~60)  → broader normalisation, preserves more contrast range
    """
    log_img = np.log1p(gray.astype(np.float32))
    log_blur = cv2.GaussianBlur(log_img, (0, 0), sigma)
    ret = log_img - log_blur
    return cv2.normalize(ret, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


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
# Font-size filter
# ---------------------------------------------------------------------------

def _filter_by_font_size(detections: list[dict], tolerance: float = 0.20) -> list[dict]:
    """
    Discard detections whose bounding-box height deviates more than
    `tolerance` from the median height of all detections.

    All numbers on a sprue share the same font size, so outliers
    (e.g. a stray digit read from a part feature) will have a noticeably
    different bounding-box height and should be removed.

    Requires at least 3 detections to establish a reliable baseline;
    returns the input unchanged when fewer are present.

    tolerance=0.20 allows for ±20% variation — enough to handle moderate
    perspective/focus differences across a large sprue photo while still
    catching obvious false-positive text.
    """
    if len(detections) < 3:
        return detections

    heights = sorted(d["px_h"] for d in detections)
    median_h = heights[len(heights) // 2]
    lo = median_h * (1.0 - tolerance)
    hi = median_h * (1.0 + tolerance)

    filtered = [d for d in detections if lo <= d["px_h"] <= hi]
    # Safety net: if tolerance is somehow too tight, keep originals.
    return filtered if filtered else detections


# ---------------------------------------------------------------------------
# Profile-specific raw detection (before merge + filter)
# ---------------------------------------------------------------------------

def _detect_clear(gray: np.ndarray, sharp: np.ndarray) -> list[dict]:
    """4 passes — CLAHE + adaptive threshold at two block sizes (bs=11 and bs=7).
    The finer bs=7 grid resolves small closely-spaced numbers that bs=11 merges."""
    thresh11 = _prep_clahe_thresh(sharp, block_size=11)
    thresh7 = _prep_clahe_thresh(sharp, block_size=7)
    return (
        _run_tesseract(thresh11)
        + _run_tesseract(cv2.bitwise_not(thresh11))
        + _run_tesseract(thresh7)
        + _run_tesseract(cv2.bitwise_not(thresh7))
    )


def _detect_bw(gray: np.ndarray) -> list[dict]:
    """14 passes — threshold sweep across _BW_THRESHOLDS, both polarities each.

    Rather than relying on a single Otsu value, we threshold the image at a
    range of fixed intensities from mid-tone up to near-white.  Each level is
    like "dialling the exposure" to a different point: lower values isolate
    dark features against the grey sprue; higher values separate subtle
    embossed relief (near background brightness) from the sprue surface.
    Running both polarities at each level ensures text is found whether it
    appears darker or lighter than the local background at that threshold.
    The individual results are merged and deduplicated by the caller.
    """
    results: list[dict] = []
    for t in _BW_THRESHOLDS:
        bw = _prep_bw_fixed(gray, t)
        results += _run_tesseract(bw)
        results += _run_tesseract(cv2.bitwise_not(bw))
    return results


def _detect_retinex(gray: np.ndarray) -> list[dict]:
    """4 passes — single-scale Retinex at two sigmas, each in both polarities.

    Retinex illumination normalisation is uniquely effective for same-colour
    embossed text (sprue numbers) where the only contrast cue is a faint shadow.
    sigma=30 catches tight local detail; sigma=60 captures broader relief.
    Running both polarities handles text that is either raised (lighter than
    surroundings after normalisation) or recessed (darker).
    """
    r30 = _prep_retinex(gray, sigma=30)
    r60 = _prep_retinex(gray, sigma=60)

    def _adapt(img: np.ndarray) -> np.ndarray:
        return cv2.adaptiveThreshold(
            img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

    return (
        _run_tesseract(_adapt(r30))
        + _run_tesseract(cv2.bitwise_not(_adapt(r30)))
        + _run_tesseract(_adapt(r60))
        + _run_tesseract(cv2.bitwise_not(_adapt(r60)))
    )


def _detect_embossed(gray: np.ndarray, sharp: np.ndarray) -> list[dict]:
    """5 passes — emphasises surface relief features."""
    embossed = _prep_emboss(gray)
    _, emboss_bin = cv2.threshold(embossed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return (
        _run_tesseract(embossed)
        + _run_tesseract(emboss_bin)
        + _run_tesseract(_prep_tophat(gray))
        + _run_tesseract(_prep_blackhat(gray))
        + _run_tesseract(_prep_sobel(sharp))
    )


def _run_profile(profile: str, gray_raw: np.ndarray, gray: np.ndarray, sharp: np.ndarray) -> list[dict]:
    """Run a single named profile through merge + font-size filter."""
    if profile == "raw":
        raw = _run_tesseract(gray_raw)
    elif profile == "clear":
        raw = _detect_clear(gray, sharp)
    elif profile == "embossed":
        raw = _detect_embossed(gray, sharp)
    elif profile == "bw":
        raw = _detect_bw(gray)
    elif profile == "retinex":
        raw = _detect_retinex(gray)
    else:
        raise ValueError(f"Unknown profile: {profile!r}")
    return _filter_by_font_size(_merge(raw))


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


def _to_relative(detections: list[dict], w: int, h: int) -> list[dict]:
    return [
        {
            "number": d["number"],
            "x": d["px_x"] / w,
            "y": d["px_y"] / h,
            "width": d["px_w"] / w,
            "height": d["px_h"] / h,
            "confidence": d["confidence"],
        }
        for d in detections
    ]


def process_image(image_path: str, profile: str = "auto") -> tuple[list[dict], str]:
    """
    Returns (detections, effective_profile).

    For 'auto', runs all candidate profiles independently, applies font-size
    filtering to each, and returns the result with the most detections.
    Ties are broken by average confidence, then by the order in
    _AUTO_CANDIDATES (clear > embossed > raw).

    For all other profiles the font-size filter is still applied, so
    effective_profile == profile.
    """
    gray_raw, gray, sharp, w, h = _load_and_prep(image_path)

    if profile == "auto":
        # Run every candidate profile independently (each gets its own
        # merge + font-filter pass), then union all results, re-merge
        # duplicates, and apply a final font-filter to catch any
        # cross-profile false positives that survived their own filter.
        union: list[dict] = []
        for p in _AUTO_CANDIDATES:
            union.extend(_run_profile(p, gray_raw, gray, sharp))
        final = _filter_by_font_size(_merge(union))
        return _to_relative(final, w, h), "auto"

    dets = _run_profile(profile, gray_raw, gray, sharp)
    return _to_relative(dets, w, h), profile


def get_debug_preview(image_path: str, profile: str = "auto") -> bytes:
    """
    Return a JPEG grid showing the key preprocessed images for the given profile.
    No OCR is re-run — purely visual.
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
    elif profile == "bw":
        # Show 4 evenly-spaced steps from the sweep so the preview grid stays readable
        sample_thresholds = [_BW_THRESHOLDS[i] for i in (0, 2, 4, 6)]  # 110, 146, 182, 218
        panels = []
        for t in sample_thresholds:
            bw = _prep_bw_fixed(gray, t)
            panels.append((f"B&W thresh={t}", bw))
            panels.append((f"B&W thresh={t} inv", cv2.bitwise_not(bw)))
    elif profile == "retinex":
        def _adapt(img: np.ndarray) -> np.ndarray:
            return cv2.adaptiveThreshold(
                img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )
        r30 = _prep_retinex(gray, sigma=30)
        r60 = _prep_retinex(gray, sigma=60)
        panels = [
            ("Retinex σ=30 (raw)", r30),
            ("Retinex σ=30 + Adapt Thresh", _adapt(r30)),
            ("Retinex σ=60 (raw)", r60),
            ("Retinex σ=60 + Adapt Thresh", _adapt(r60)),
        ]
    else:  # auto — show one representative panel per candidate
        thresh = _prep_clahe_thresh(sharp)
        r60 = _prep_retinex(gray, sigma=60)
        panels = [
            ("Clear: CLAHE + Threshold", thresh),
            ("Retinex σ=60 + Adapt Thresh",
             cv2.adaptiveThreshold(r60, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 11, 2)),
            ("B&W: Otsu Threshold", cv2.threshold(cv2.GaussianBlur(gray, (5, 5), 0), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
            ("Embossed: Emboss (6-dir)", _prep_emboss(gray)),
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

    if len(cells) <= 2:
        grid = np.hstack(cells)
    else:
        cw = cells[0].shape[1]
        row1 = np.hstack(cells[:2])
        row2_imgs = cells[2:4]
        if len(row2_imgs) < 2:
            row2_imgs.append(np.zeros((cells[0].shape[0], cw, 3), dtype=np.uint8))
        grid = np.vstack([row1, np.hstack(row2_imgs)])

    _, buf = cv2.imencode(".jpg", grid, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return bytes(buf)
