"""Domain data — one model per pipeline stage, composed downstream.

Each stage produces its own model and never mutates the upstream one:

    Rasterizer        -> RenderedPage
    LayoutDetector    -> LayoutBlock
    OCREngine         -> OCRBlock      (only for blocks it actually OCR'd)
    block processing  -> ProcessedBlock (LayoutBlock + optional OCRBlock
                                        + the processing decision)

Provenance is explicit: every field on a model is set by exactly one
stage, and the JSON dump nests blocks per stage, so a bad value can
always be traced back to the stage that produced it.

Every model is re-exported here — importers write
``from scriber.domain import LayoutBlock, OCRBlock`` instead of
module-per-class imports.
"""

from scriber.domain.LayoutBlock import LayoutBlock
from scriber.domain.OCRBlock import OCRBlock
from scriber.domain.PageResult import PageResult
from scriber.domain.ProcessedBlock import ProcessedBlock
from scriber.domain.RenderedPage import RenderedPage

__all__ = [
    "LayoutBlock",
    "OCRBlock",
    "PageResult",
    "ProcessedBlock",
    "RenderedPage",
]
