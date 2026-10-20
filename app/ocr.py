"""
Sprue-number OCR.

Uses RapidOCR — PaddleOCR's PP-OCRv4 text detector + recogniser running on
ONNX Runtime (CPU, models bundled in the wheel, no network access needed).

Why not Tesseract: sprue numbers are tiny, sparse labels scattered across a
cluttered photo. Tesseract's page-layout analysis is built for documents and
returns mostly noise on that input no matter how the image is preprocessed.
A scene-text detector finds the labels directly; the only thing it needs is
for the digits to be large enough in pixels, so the pipeline is:

  1. Coarse pass at native resolution. Finds the bold, plated numbers and
     tells us how tall a number label is in this particular photo.
  2. Fine pass, upscaled so labels reach ~_TARGET_LABEL_PX tall. This is what
     picks up the thin, low-contrast numbers moulded directly into the frame.
  3. Union both passes, keep the best-scoring reading per location, drop
     low-score and wrong-size detections.

Both passes run tile-by-tile, so memory stays bounded (~1.5 GB peak) even when
a 4000 px photo is upscaled 2-3x.
"""

import math
import re
import threading

import cv2
import numpy as np

from app.config import settings

PROFILES: dict[str, str] = {
    "auto": "Auto (adaptive upscale)",
}

# Label height (detector box, which includes some padding) the fine pass
# upscales to. Measured on full-sprue phone photos: ~100 px gives the best
# recall; much larger starts splitting numbers into single digits.
_TARGET_LABEL_PX = 100.0
_MIN_SCALE, _MAX_SCALE = 1.0, 4.0
# Skip the fine pass when the computed upscale is this close to 1.
_SKIP_FINE_BELOW = 1.15
# Fallback label-height estimate when the coarse pass finds too few numbers:
# on a photo of a whole sprue a label is roughly 2.3% of the short side.
_FALLBACK_LABEL_FRACTION = 0.023

# Tiling, in upscaled (detector input) pixels. The overlap must exceed the
# widest label (3 digits at _TARGET_LABEL_PX) so every number lies fully
# inside at least one tile.
_TILE_PX = 2400
_TILE_OVERLAP_PX = 320
_TILE_EDGE_PX = 4

_engine = None
# RapidOCR mutates per-call state (detector preprocess op), so calls must
# not interleave. Also caps concurrent OCR memory to one image at a time.
_engine_lock = threading.Lock()


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR

        # We resize ourselves; stop RapidOCR from rescaling the input
        # (its defaults shrink a 4000 px photo until the digits vanish).
        _engine = RapidOCR(
            max_side_len=100_000,
            det_limit_type="min",
            det_limit_side_len=32,
        )
    return _engine


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _tiles(length: int, max_tile: int, overlap: int) -> tuple[list[int], int]:
    """Split one axis into the fewest equal tiles of at most `max_tile` that
    overlap by `overlap`. Returns (tile origins, tile length)."""
    if length <= max_tile:
        return [0], length
    n = math.ceil((length - overlap) / (max_tile - overlap))
    tile = math.ceil((length + (n - 1) * overlap) / n)
    step = (length - tile) / (n - 1)
    return [round(i * step) for i in range(n)], tile


def _detect(img: np.ndarray, scale: float) -> list[dict]:
    """
    Run detection + recognition over `img` upscaled by `scale`, tile by tile.
    Returns raw text detections with boxes in original-image pixels.
    """
    h, w = img.shape[:2]
    max_tile = int(_TILE_PX / scale)
    overlap = int(_TILE_OVERLAP_PX / scale)
    edge = _TILE_EDGE_PX / scale
    y_origins, tile_h = _tiles(h, max_tile, overlap)
    x_origins, tile_w = _tiles(w, max_tile, overlap)
    engine = _get_engine()

    out = []
    for y0 in y_origins:
        for x0 in x_origins:
            crop = img[y0:y0 + tile_h, x0:x0 + tile_w]
            ch, cw = crop.shape[:2]
            if scale != 1.0:
                crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            with _engine_lock:
                result, _ = engine(crop, use_cls=False)
            for quad, text, score in result or []:
                xs = [p[0] / scale for p in quad]
                ys = [p[1] / scale for p in quad]
                x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
                # A box touching an inner tile edge is probably a number cut
                # in half; the overlapping neighbour tile sees it whole.
                if (x0 > 0 and x1 < edge) or (y0 > 0 and y1 < edge) \
                        or (x0 + cw < w and x2 > cw - edge) or (y0 + ch < h and y2 > ch - edge):
                    continue
                out.append({
                    "text": text,
                    "score": float(score),
                    "px_x": x0 + x1,
                    "px_y": y0 + y1,
                    "px_w": x2 - x1,
                    "px_h": y2 - y1,
                })
    return out


_EDGE_PUNCT = "-_.,:;'\"`|()[]"


def _parse_number(text: str) -> int | None:
    """Sprue labels are 1-3 digits. Tolerate stray edge punctuation ("79-")."""
    t = text.replace(" ", "").strip(_EDGE_PUNCT)
    if not re.fullmatch(r"\d{1,3}", t):
        return None
    n = int(t)
    return n if 1 <= n <= 999 else None


def _numbers(raw: list[dict]) -> list[dict]:
    out = []
    for d in raw:
        n = _parse_number(d["text"])
        if n is not None:
            out.append({**d, "number": n})
    return out


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def _overlaps(a: dict, b: dict) -> bool:
    """True if either box's centre lies inside the other box."""
    def centre_in(p, q):
        cx, cy = p["px_x"] + p["px_w"] / 2, p["px_y"] + p["px_h"] / 2
        return q["px_x"] <= cx <= q["px_x"] + q["px_w"] and q["px_y"] <= cy <= q["px_y"] + q["px_h"]
    return centre_in(a, b) or centre_in(b, a)


def _merge(detections: list[dict]) -> list[dict]:
    """One detection per location: the highest-scoring reading wins, so a
    coarse-pass misread ("50") loses to a confident fine-pass read ("60")."""
    kept: list[dict] = []
    for d in sorted(detections, key=lambda d: d["score"], reverse=True):
        if not any(_overlaps(d, k) for k in kept):
            kept.append(d)
    return kept


def _dominant_height(heights: list[float], tolerance: float) -> float | None:
    """
    Centre of the densest height cluster: the height with the most other
    heights within ±tolerance. All numbers on a sprue share one font size, so
    this is the label height even when outliers (logos, part details) are
    numerous. Returns None with fewer than 3 samples.
    """
    if len(heights) < 3:
        return None
    best, best_count = None, 0
    for h in heights:
        count = sum(1 for x in heights if h * (1 - tolerance) <= x <= h * (1 + tolerance))
        if count > best_count:
            best, best_count = h, count
    return best


def _filter_by_font_size(detections: list[dict], tolerance: float) -> list[dict]:
    centre = _dominant_height([d["px_h"] for d in detections], tolerance)
    if centre is None:
        return detections
    lo, hi = centre * (1 - tolerance), centre * (1 + tolerance)
    return [d for d in detections if lo <= d["px_h"] <= hi]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _fine_scale(img: np.ndarray, coarse_numbers: list[dict]) -> float:
    confident = [d["px_h"] for d in coarse_numbers if d["score"] >= 0.9]
    label_h = _dominant_height(confident, settings.OCR_FONT_SIZE_TOLERANCE)
    if label_h is None:
        label_h = _FALLBACK_LABEL_FRACTION * min(img.shape[:2])
    return min(max(_TARGET_LABEL_PX / label_h, _MIN_SCALE), _MAX_SCALE)


def _analyse(img: np.ndarray, profile: str) -> tuple[list[dict], list[dict], float]:
    """Returns (accepted, rejected_numbers, fine_scale)."""
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile: {profile!r}")

    candidates = _numbers(_detect(img, 1.0))
    scale = _fine_scale(img, candidates)
    if scale >= _SKIP_FINE_BELOW:
        candidates += _numbers(_detect(img, scale))

    merged = _merge(candidates)
    scored = [d for d in merged if d["score"] >= settings.OCR_MIN_SCORE]
    accepted = _filter_by_font_size(scored, settings.OCR_FONT_SIZE_TOLERANCE)
    accepted_ids = {id(d) for d in accepted}
    rejected = [d for d in merged if id(d) not in accepted_ids]
    return accepted, rejected, scale


def _load(image_path: str) -> np.ndarray:
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not load image: {image_path}")
    return img


def process_image(image_path: str, profile: str = "auto") -> tuple[list[dict], str]:
    """
    Returns (detections, profile). Each detection has `number`, relative box
    coords `x`/`y`/`width`/`height` (0.0-1.0) and `confidence` (0-100).
    """
    img = _load(image_path)
    h, w = img.shape[:2]
    accepted, _, _ = _analyse(img, profile)
    return [
        {
            "number": d["number"],
            "x": d["px_x"] / w,
            "y": d["px_y"] / h,
            "width": d["px_w"] / w,
            "height": d["px_h"] / h,
            "confidence": round(d["score"] * 100),
        }
        for d in sorted(accepted, key=lambda d: d["number"])
    ], profile


def get_debug_preview(image_path: str, profile: str = "auto") -> bytes:
    """
    JPEG of the photo with every numeric candidate drawn: green = accepted,
    red = rejected (low score, wrong size, or lost to a better overlapping
    reading). Re-runs OCR, so it takes as long as a reprocess.
    """
    img = _load(image_path)
    accepted, rejected, scale = _analyse(img, profile)

    thickness = max(2, img.shape[1] // 800)
    font_scale = img.shape[1] / 2500
    for dets, colour in ((rejected, (0, 0, 230)), (accepted, (0, 180, 0))):
        for d in dets:
            x, y = int(d["px_x"]), int(d["px_y"])
            x2, y2 = int(d["px_x"] + d["px_w"]), int(d["px_y"] + d["px_h"])
            cv2.rectangle(img, (x, y), (x2, y2), colour, thickness)
            cv2.putText(img, f"{d['number']} {d['score']:.2f}", (x, max(0, y - 2 * thickness)),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, colour, thickness, cv2.LINE_AA)

    label = f"{profile}: {len(accepted)} accepted, {len(rejected)} rejected, fine-pass upscale {scale:.2f}x"
    cv2.putText(img, label, (10, int(40 * font_scale) + 10), cv2.FONT_HERSHEY_SIMPLEX,
                font_scale * 1.2, (200, 0, 200), thickness + 1, cv2.LINE_AA)

    max_w = 2000
    if img.shape[1] > max_w:
        img = cv2.resize(img, (max_w, int(img.shape[0] * max_w / img.shape[1])), interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return bytes(buf)
