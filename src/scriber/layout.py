"""Layout detection + reading order.

Wraps surya's LayoutPredictor (VLM-based) which classifies each page into
blocks with canonical labels (Text, SectionHeader, PageHeader, PageFooter,
Picture, Caption, ...) and emits them with a reading-order position.
"""

from __future__ import annotations

import math
from statistics import median

from PIL import Image
from surya.inference import SuryaInferenceManager
from surya.layout import LayoutPredictor

from scriber.domain import LayoutBlock, RenderedPage
from scriber.enums import BlockType
from scriber.exceptions import LayoutError

# Heuristic tuning knobs (geometry-only, applied pre-OCR).
TITLE_HEIGHT_RATIO = 1.4  # block height vs median Text-block height
TITLE_CENTER_TOLERANCE = 0.08  # block center vs page center, as page-width fraction
TITLE_ISOLATION_RATIO = 0.75  # vertical gap to nearest neighbour vs block height


class LayoutDetector:
    def __init__(self, manager: SuryaInferenceManager) -> None:
        self._predictor = LayoutPredictor(manager)

    def detect(self, pages: list[RenderedPage]) -> list[list[LayoutBlock]]:
        """Detect layout blocks for each rendered page.

        Returns one list of LayoutBlocks per page, sorted by reading order.
        """
        if not pages:
            return []

        images: list[Image.Image] = [Image.open(p.image_path) for p in pages]
        results = self._predictor(images)

        all_blocks: list[list[LayoutBlock]] = []
        for page, result in zip(pages, results, strict=True):
            if result.error:
                raise LayoutError(
                    f"layout detection failed on page {page.page_number}"
                )

            blocks = [
                LayoutBlock(
                    index=i,
                    label=box.label,
                    type=BlockType.from_surya_label(box.label),
                    bbox=_bbox_xyxy(box),
                    reading_order=box.position,
                )
                for i, box in enumerate(result.bboxes)
            ]
            blocks.sort(key=lambda b: b.reading_order)
            # Re-index after sorting so index == position in reading order.
            for i, block in enumerate(blocks):
                block.index = i

            _promote_titles(blocks, page.width, page.height)
            all_blocks.append(blocks)
        return all_blocks


def _bbox_xyxy(box) -> tuple[float, float, float, float]:
    """Copy the LayoutBox bbox into a plain tuple (already pixel floats)."""
    x0, y0, x1, y1 = box.bbox
    return (x0, y0, x1, y1)


def _promote_titles(blocks: list[LayoutBlock], page_width: int, page_height: int) -> None:
    """Relabel centered + large + isolated Text blocks to Title.

    Only runs when the page has no SectionHeader blocks — if surya already
    found an explicit section header, we trust it and don't guess.
    """
    if any(b.label == "SectionHeader" for b in blocks):
        return

    text_blocks = [b for b in blocks if b.label == "Text"]
    if len(text_blocks) < 2:
        return

    median_h = median(_height(b) for b in text_blocks)
    page_center_x = page_width / 2

    for block in text_blocks:
        w, h = _width(block), _height(block)
        if h < TITLE_HEIGHT_RATIO * max(median_h, 1):
            continue

        center_x = block.bbox[0] + w / 2
        if abs(center_x - page_center_x) > TITLE_CENTER_TOLERANCE * page_width:
            continue

        if not _is_isolated(block, blocks):
            continue

        block.label = "Title"


def _is_isolated(block: LayoutBlock, all_blocks: list[LayoutBlock]) -> bool:
    """True when the vertical gap to the nearest neighbour is large."""
    _, y0, _, y1 = block.bbox
    h = _height(block)
    gaps = [
        # Neighbour below: gap = its top - our bottom.
        other.bbox[1] - y1
        if other.bbox[1] >= y1
        # Neighbour above: gap = our top - its bottom.
        else y0 - other.bbox[3]
        for other in all_blocks
        if other is not block and _overlaps_horizontally(block, other)
    ]
    nearest_gap = min(gaps) if gaps else math.inf
    return nearest_gap >= TITLE_ISOLATION_RATIO * max(h, 1)


def _overlaps_horizontally(a: LayoutBlock, b: LayoutBlock) -> bool:
    return a.bbox[0] < b.bbox[2] and b.bbox[0] < a.bbox[2]


def _width(block: LayoutBlock) -> float:
    return block.bbox[2] - block.bbox[0]


def _height(block: LayoutBlock) -> float:
    return block.bbox[3] - block.bbox[1]
