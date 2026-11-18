"""Hybrid NSFW detection: NudeNet regions decide, a WD tagger votes, YOLO boxes only locate.

This file is shared verbatim between Bubba Media Viewer (backend/services/nsfw_detect.py) and Bubba Nodes
(src/bubba_nodes/utils/nsfw_detect.py). Keep the two copies identical.

Evidence is a list of regions: {label, score, box: [x1, y1, x2, y2] normalised 0-1, source}
    source "nudenet"  NudeNet 640m detections, e.g. FEMALE_BREAST_EXPOSED / FEMALE_BREAST_COVERED
    source "wd"       WD tagger image-level votes, e.g. rating:explicit, tag:nude (box = whole image)
    source "yolo"     location-only boxes (breast/nipple YOLO models fire on clothed bodies too)
`classify()` turns evidence into a rating under the user's sensitivity, so stored evidence can be
re-judged later without re-running any model.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

NUDENET_LABELS = [
    "FEMALE_GENITALIA_COVERED",
    "FACE_FEMALE",
    "BUTTOCKS_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_BREAST_EXPOSED",
    "ANUS_EXPOSED",
    "FEET_EXPOSED",
    "BELLY_COVERED",
    "FEET_COVERED",
    "ARMPITS_COVERED",
    "ARMPITS_EXPOSED",
    "FACE_MALE",
    "BELLY_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "ANUS_COVERED",
    "FEMALE_BREAST_COVERED",
    "BUTTOCKS_COVERED",
]
EXPOSED_NSFW = {"FEMALE_BREAST_EXPOSED", "FEMALE_GENITALIA_EXPOSED", "MALE_GENITALIA_EXPOSED", "BUTTOCKS_EXPOSED", "ANUS_EXPOSED"}
COVERED_SENSITIVE = {"FEMALE_BREAST_COVERED", "FEMALE_GENITALIA_COVERED", "BUTTOCKS_COVERED", "ANUS_COVERED"}
STORED_NUDENET = EXPOSED_NSFW | COVERED_SENSITIVE
NUDENET_INPUT = 640
NUDENET_MIN_SCORE = 0.2

WD_INPUT = 448
WD_NUDITY_TAGS = {"nude", "completely_nude", "topless", "bottomless", "nipples", "areolae", "pussy", "penis", "anus", "sex", "breasts_out", "nipple_slip", "areola_slip"}
WD_SEE_THROUGH_TAGS = {"see-through", "see-through_shirt", "see-through_clothes", "covered_nipples", "wet_clothes"}
WD_MIN_SCORE = 0.1

PRESETS: dict[str, dict[str, Any]] = {
    "cautious": {"sensitivity": 75, "see_through": True, "tagger": "nudity"},
    "balanced": {"sensitivity": 50, "see_through": True, "tagger": "nudity"},
    "strict": {"sensitivity": 33, "see_through": False, "tagger": "explicit"},
}
DEFAULT_PRESET = "strict"
NUDENET_MODEL_FILE = "640m.onnx"
WD_MODEL_FILE = "wd-vit-tagger-v3.onnx"
WD_TAGS_FILE = "selected_tags.csv"


def default_model_dir() -> Path:
    """Shared model folder: %APPDATA%/Bubba Media Viewer/models/nsfw (override with BUBBA_NSFW_MODEL_DIR)."""
    override = os.environ.get("BUBBA_NSFW_MODEL_DIR")
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) / "Bubba Media Viewer" if appdata else Path.home() / ".config" / "bubba-media-viewer"
    return base / "models" / "nsfw"


def thresholds(sensitivity: float) -> tuple[float, float]:
    """(NudeNet EXPOSED threshold, tagger threshold). 0 = least sensitive, 100 = most."""
    level = min(100.0, max(0.0, float(sensitivity)))
    exposed = round(0.85 - 0.6 * level / 100.0, 3)
    return exposed, round(min(0.95, exposed + 0.1), 3)


def resolve_options(preset: str = DEFAULT_PRESET, sensitivity: float | None = None, see_through: bool | None = None) -> dict[str, Any]:
    base = PRESETS.get(preset) or PRESETS[DEFAULT_PRESET]
    return {
        "sensitivity": base["sensitivity"] if sensitivity is None else float(sensitivity),
        "see_through": base["see_through"] if see_through is None else bool(see_through),
        "tagger": base["tagger"],
    }


def _pad_box(box: list[float], amount: float = 0.04) -> list[float]:
    x1, y1, x2, y2 = box
    return [max(0.0, x1 - amount), max(0.0, y1 - amount), min(1.0, x2 + amount), min(1.0, y2 + amount)]


def classify(regions: list[dict[str, Any]], sensitivity: float = 33, see_through: bool = False, tagger: str = "explicit") -> dict[str, Any]:
    """Rate evidence: {rating: sfw|questionable|nsfw, score, regions: boxes to blur, reasons}."""
    exposed_t, tagger_t = thresholds(sensitivity)
    nudenet = [region for region in regions if region.get("source") == "nudenet"]
    votes = {str(region.get("label")): float(region.get("score", 0)) for region in regions if region.get("source") == "wd"}
    exposed = [region for region in nudenet if region.get("label") in EXPOSED_NSFW]
    covered = [region for region in nudenet if region.get("label") in COVERED_SENSITIVE]
    best_exposed = max((float(region["score"]) for region in exposed), default=0.0)
    explicit = votes.get("rating:explicit", 0.0)
    questionable = votes.get("rating:questionable", 0.0)
    nudity_vote = max((score for label, score in votes.items() if label.removeprefix("tag:") in WD_NUDITY_TAGS), default=0.0)
    see_through_vote = max((score for label, score in votes.items() if label.removeprefix("tag:") in WD_SEE_THROUGH_TAGS), default=0.0)

    reasons = []
    if best_exposed >= exposed_t:
        reasons.append("exposed")
    tagger_vote = explicit if tagger == "explicit" else max(explicit, nudity_vote)
    if tagger_vote >= tagger_t:
        reasons.append("tagger")
    if see_through and see_through_vote >= tagger_t:
        reasons.append("see-through")

    if reasons:
        rating = "nsfw"
        score = max(best_exposed, tagger_vote, see_through_vote if "see-through" in reasons else 0.0)
        blur = [region for region in exposed if float(region["score"]) >= exposed_t * 0.75]
        if "see-through" in reasons or "tagger" in reasons:
            blur += [region for region in covered if float(region["score"]) >= exposed_t * 0.75]
        blur += [region for region in regions if region.get("source") == "yolo"]
    else:
        flagged = questionable >= tagger_t or best_exposed >= exposed_t * 0.6 or see_through_vote >= tagger_t
        rating = "questionable" if flagged else "sfw"
        score = max(best_exposed, questionable, see_through_vote if flagged else 0.0)
        blur = []
    return {
        "rating": rating,
        "score": round(min(1.0, score), 4),
        "regions": [{"label": region.get("label", ""), "box": _pad_box(list(region["box"]))} for region in blur],
        "reasons": reasons,
    }


def _session(path: Path):
    import onnxruntime as ort

    providers = [provider for provider in ("CUDAExecutionProvider", "CPUExecutionProvider") if provider in ort.get_available_providers()]
    return ort.InferenceSession(str(path), providers=providers or None)


def _nms(boxes, scores, iou_threshold: float = 0.45) -> list[int]:
    import numpy as np

    order = np.argsort(scores)[::-1]
    keep = []
    while order.size:
        index = int(order[0])
        keep.append(index)
        x1 = np.maximum(boxes[index, 0], boxes[order[1:], 0])
        y1 = np.maximum(boxes[index, 1], boxes[order[1:], 1])
        x2 = np.minimum(boxes[index, 2], boxes[order[1:], 2])
        y2 = np.minimum(boxes[index, 3], boxes[order[1:], 3])
        intersection = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
        area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        union = area[index] + area[order[1:]] - intersection
        order = order[1:][intersection / np.maximum(union, 1e-9) < iou_threshold]
    return keep


class NudeNetDetector:
    """NudeNet v3 (640m) ONNX detector."""

    def __init__(self, model_path: Path):
        self.session = _session(model_path)
        self.input_name = self.session.get_inputs()[0].name

    def detect(self, image) -> list[dict[str, Any]]:
        import numpy as np

        rgb = image.convert("RGB")
        width, height = rgb.size
        scale = NUDENET_INPUT / max(width, height)
        resized = rgb.resize((max(1, round(width * scale)), max(1, round(height * scale))))
        canvas = np.zeros((NUDENET_INPUT, NUDENET_INPUT, 3), dtype=np.float32)
        pad_x, pad_y = (NUDENET_INPUT - resized.width) // 2, (NUDENET_INPUT - resized.height) // 2
        canvas[pad_y : pad_y + resized.height, pad_x : pad_x + resized.width] = np.asarray(resized, dtype=np.float32) / 255.0
        output = self.session.run(None, {self.input_name: canvas.transpose(2, 0, 1)[None]})[0]
        rows = np.squeeze(output, 0).T  # (anchors, 4 + classes)
        class_scores = rows[:, 4:]
        class_ids = class_scores.argmax(1)
        scores = class_scores.max(1)
        mask = scores >= NUDENET_MIN_SCORE
        if not mask.any():
            return []
        rows, class_ids, scores = rows[mask], class_ids[mask], scores[mask]
        cx, cy, w, h = rows[:, 0], rows[:, 1], rows[:, 2], rows[:, 3]
        boxes = np.stack([cx - w / 2 - pad_x, cy - h / 2 - pad_y, cx + w / 2 - pad_x, cy + h / 2 - pad_y], 1) / scale
        regions = []
        for index in _nms(boxes, scores):
            label = NUDENET_LABELS[int(class_ids[index])]
            if label not in STORED_NUDENET:
                continue
            x1, y1, x2, y2 = boxes[index]
            box = [float(min(1, max(0, value))) for value in (x1 / width, y1 / height, x2 / width, y2 / height)]
            regions.append({"label": label, "score": round(float(scores[index]), 4), "box": [round(v, 4) for v in box], "source": "nudenet"})
        return regions


class WdTagger:
    """SmilingWolf WD v3 tagger; only rating and nudity / see-through tags are kept as votes."""

    def __init__(self, model_path: Path, tags_path: Path):
        self.session = _session(model_path)
        self.input_name = self.session.get_inputs()[0].name
        with open(tags_path, newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        wanted = WD_NUDITY_TAGS | WD_SEE_THROUGH_TAGS
        self.keep = {}
        for index, row in enumerate(rows):
            name = row["name"]
            if row.get("category") == "9" and name in {"questionable", "explicit"}:
                self.keep[index] = f"rating:{name}"
            elif name in wanted:
                self.keep[index] = f"tag:{name}"

    def votes(self, image) -> list[dict[str, Any]]:
        import numpy as np
        from PIL import Image

        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        rgb = Image.alpha_composite(background, rgba).convert("RGB")
        side = max(rgb.size)
        square = Image.new("RGB", (side, side), (255, 255, 255))
        square.paste(rgb, ((side - rgb.width) // 2, (side - rgb.height) // 2))
        array = np.asarray(square.resize((WD_INPUT, WD_INPUT), Image.BICUBIC), dtype=np.float32)[:, :, ::-1]  # BGR, 0-255
        probabilities = self.session.run(None, {self.input_name: np.ascontiguousarray(array)[None]})[0][0]
        return [
            {"label": label, "score": round(float(probabilities[index]), 4), "box": [0.0, 0.0, 1.0, 1.0], "source": "wd"}
            for index, label in self.keep.items()
            if float(probabilities[index]) >= WD_MIN_SCORE
        ]


class Ensemble:
    """Loads whichever models are present in `model_dir`; NudeNet is required."""

    def __init__(self, model_dir: Path | None = None):
        self.model_dir = Path(model_dir) if model_dir else default_model_dir()
        nudenet_path = self.model_dir / NUDENET_MODEL_FILE
        if not nudenet_path.is_file():
            raise FileNotFoundError(f"NudeNet model not found: {nudenet_path}")
        self.detector = NudeNetDetector(nudenet_path)
        wd_path, tags_path = self.model_dir / WD_MODEL_FILE, self.model_dir / WD_TAGS_FILE
        self.tagger = WdTagger(wd_path, tags_path) if wd_path.is_file() and tags_path.is_file() else None

    def analyze(self, image) -> list[dict[str, Any]]:
        regions = self.detector.detect(image)
        if self.tagger is not None:
            regions += self.tagger.votes(image)
        return regions


def models_available(model_dir: Path | None = None) -> dict[str, Any]:
    directory = Path(model_dir) if model_dir else default_model_dir()
    try:
        import onnxruntime  # noqa: F401

        runtime = True
    except ImportError:
        runtime = False
    return {
        "model_dir": str(directory),
        "onnxruntime": runtime,
        "nudenet": (directory / NUDENET_MODEL_FILE).is_file(),
        "tagger": (directory / WD_MODEL_FILE).is_file() and (directory / WD_TAGS_FILE).is_file(),
    }
