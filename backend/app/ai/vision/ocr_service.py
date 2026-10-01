"""OCR: read the text printed on an item.

Uses the vision model for now. EasyOCR / Tesseract can implement the same
``read`` method later (AI_STRUCTURE.md: ocr_service) without touching callers.
"""
from __future__ import annotations

from typing import Protocol

from PIL import Image


class OcrEngine(Protocol):
    def ocr(self, image: Image.Image) -> list[str]: ...


class OcrService:
    def __init__(self, engine: OcrEngine):
        self.engine = engine

    def read(self, image: Image.Image) -> list[str]:
        """Text segments in reading order; empty list when nothing is printed."""
        return self.engine.ocr(image)
