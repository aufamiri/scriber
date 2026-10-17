from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scriber.domain.LayoutBlock import LayoutBlock
from scriber.domain.OCRBlock import OCRBlock


@dataclass
class ProcessedBlock:
    """Block-processing decision for one LayoutBlock (process_page).

    ``ocr`` is present only when OCR ran
    for the block (its type is in ``ocr.OCR_TYPES``).
    """

    layout: LayoutBlock
    # Deterministic uuid5 over the page id + block reading-order index
    # (see utils.IdUtil) — stable across runs of the same PDF, and the
    # future DB key for a processed block.
    id: str = ""
    ocr: OCRBlock | None = None
    crop_path: Path | None = None
    embed_as_image: bool = False
    dropped: bool = False
    drop_reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "dropped": self.dropped,
            "drop_reason": self.drop_reason,
            "embed_as_image": self.embed_as_image,
            "crop_path": str(self.crop_path) if self.crop_path else None,
            "layout": self.layout.as_dict(),
            "ocr": self.ocr.as_dict() if self.ocr is not None else None,
        }
