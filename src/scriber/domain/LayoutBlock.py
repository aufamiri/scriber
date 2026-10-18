from __future__ import annotations

from dataclasses import dataclass

from scriber.enums.BlockType import BlockType


@dataclass
class LayoutBlock:
    """One detected layout block on a page (LayoutDetector).

    ``bbox`` is pixel ``[x0, y0, x1, y1]`` in the rendered page image's
    coordinate space. ``type`` is the coarse category derived from
    ``label`` (see ``BlockType.LABEL_TO_TYPE``)
    """
    index: int
    label: str
    bbox: tuple[float, float, float, float]
    reading_order: int
    # Coarse category (BlockType).
    type: BlockType = BlockType.OTHER

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "type": self.type.value,
            "bbox": list(self.bbox),
            "reading_order": self.reading_order,
        }
