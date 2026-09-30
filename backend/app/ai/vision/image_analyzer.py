"""Image analyzer: customer photo → ImageAnalysis (via Qwen3-VL) → cropped main item."""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from app.ai.llm.qwen_vision import QwenVision
from app.ai.prompts.vision_prompt import ImageAnalysis

BBOX_SCALE = 1000  # qwen3-vl returns 0-1000 relative coordinates
MIN_BBOX_AREA = 0.10  # smaller boxes are more likely wrong than a tiny item
BBOX_MARGIN = 0.05


@dataclass
class AnalyzedImage:
    analysis: ImageAnalysis
    original: Image.Image
    cropped: Image.Image  # main item, or the original when the box is unusable
    was_cropped: bool


def crop_to_bbox(img: Image.Image, bbox: list[float] | None) -> tuple[Image.Image, bool]:
    """Crop to a 0-1000 bbox with a small margin. Falls back to the full image."""
    if not bbox:
        return img, False
    x1, y1, x2, y2 = (max(0.0, min(1.0, v / BBOX_SCALE)) for v in bbox)
    if (x2 - x1) * (y2 - y1) < MIN_BBOX_AREA:
        return img, False
    mx, my = (x2 - x1) * BBOX_MARGIN, (y2 - y1) * BBOX_MARGIN
    w, h = img.size
    box = (
        int(max(0.0, x1 - mx) * w), int(max(0.0, y1 - my) * h),
        int(min(1.0, x2 + mx) * w), int(min(1.0, y2 + my) * h),
    )
    return img.crop(box), True


class ImageAnalyzer:
    def __init__(self, vision: QwenVision | None = None):
        self.vision = vision or QwenVision()

    def analyze(self, img: Image.Image, message: str | None = None) -> AnalyzedImage:
        analysis = self.vision.analyze(img, message)
        cropped, was_cropped = crop_to_bbox(img, analysis.bbox)
        return AnalyzedImage(analysis, img, cropped, was_cropped)
