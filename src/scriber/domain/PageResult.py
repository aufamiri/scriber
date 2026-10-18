from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from scriber.domain.ProcessedBlock import ProcessedBlock


@dataclass
class PageResult:
    """All processed blocks of one page (final pipeline output)."""
    id: str
    page_number: int
    image_path: Path
    width: int
    height: int
    blocks: list[ProcessedBlock] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "page_number": self.page_number,
            "image_path": str(self.image_path),
            "width": self.width,
            "height": self.height,
            "blocks": [b.as_dict() for b in self.blocks],
        }
