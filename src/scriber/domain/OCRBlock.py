from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OCRBlock:
    """OCR result for a single block (OCREngine).

    Exists only when OCR actually ran — i.e. the block's type is in
    ``ocr.OCR_TYPES``. Blocks that weren't OCR'd simply have no OCRBlock
    (``ProcessedBlock.ocr is None``).
    """
    text: str = ""
    html: str = ""
    confidence: float | None = None

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "html": self.html,
            "confidence": self.confidence,
        }
