"""OCR text recognition.

Wraps surya's RecognitionPredictor in per-block mode: blocks whose type
is in ``OCR_TYPES`` are cropped from the rendered page image and recognized individually, producing
HTML output plus an average confidence. All other blocks get no OCRBlock
at all — no surya request is spent on them.
"""

from __future__ import annotations

from PIL import Image
from surya.inference import SuryaInferenceManager
from surya.layout.schema import LayoutBox, LayoutResult
from surya.recognition import RecognitionPredictor

from scriber.domain import LayoutBlock, OCRBlock, RenderedPage
from scriber.enums import BlockType
from scriber.exceptions import OCRError
from scriber.helpers import HtmlExtractor

# The only block types worth an OCR request. SectionHeaders (incl.
# promoted Titles) are OCR'd so chapter titles keep their text for the
# TOC — surya fully supports them (only Figure/Image/Diagram/BlankPage
# are ever skipped). Everything else — page headers, pictures, footers,
# out-of-scope labels — gets no OCRBlock, and no surya call is spent on it.
OCR_TYPES = frozenset({BlockType.TEXT, BlockType.SECTION_HEADER})


def _corner_polygon(bbox: tuple[float, float, float, float]) -> list[list[float]]:
    """Lay out a flat bbox as the 4-corner polygon PolygonBox expects."""
    x0, y0, x1, y1 = bbox
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


# Surya sizes each OCR request as min(count + 100, ceiling). We don't
# model per-block token estimates (surya runs locally — no need to
# conserve), so we saturate the count instead: any value at or above the
# ceiling yields the full budget and no block is ever truncated.
_SATURATING_TOKEN_COUNT = 10 ** 6


def _to_surya_layout_box(block: LayoutBlock) -> LayoutBox:
    """Convert one LayoutBlock into the surya LayoutBox consumed by the
    RecognitionPredictor: the pixel polygon to crop, the label it uses to
    skip visual blocks, and the reading order. The count is saturated so
    every OCR request gets surya's maximum token budget.
    """
    return LayoutBox(
        polygon=_corner_polygon(block.bbox),
        label=block.label,
        raw_label="",
        position=block.reading_order,
        count=_SATURATING_TOKEN_COUNT,
    )


class OCREngine:
    def __init__(self, manager: SuryaInferenceManager) -> None:
        self._predictor = RecognitionPredictor(manager)
        self.html_extractor = HtmlExtractor()

    def recognize(
            self, pages: list[RenderedPage], layout_blocks: list[list[LayoutBlock]]
    ) -> list[list[OCRBlock | None]]:
        """Run OCR on every page's layout blocks.

        Only blocks whose type is in ``OCR_TYPES`` (Text, SectionHeader)
        are sent to surya;
        every result list is positionally aligned with its layout-block
        list, with ``None`` wherever no OCR was requested.
        """
        if not pages:
            return []

        # Split each page into the blocks worth an OCR request.
        ocr_targets = [
            [block for block in blocks if block.type in OCR_TYPES]
            for blocks in layout_blocks
        ]

        layout_results = self.recreate_surya_layout_results(pages, ocr_targets)
        images: list[Image.Image] = [Image.open(p.image_path) for p in pages]
        results = self._predictor(images, layout_results, full_page=False)

        all_ocr_blocks: list[list[OCRBlock | None]] = []
        for page, blocks, targets, ocr_page in zip(
                pages, layout_blocks, ocr_targets, results, strict=True
        ):
            if len(ocr_page.blocks) != len(targets):
                raise OCRError(
                    f"OCR returned {len(ocr_page.blocks)} blocks for page "
                    f"{page.page_number}, expected {len(targets)}"
                )

            # surya's per-block results align with the target subset — index
            # them back onto the full block list by block index.
            ocr_by_index = {
                block.index: ocr_block
                for block, ocr_block in zip(targets, ocr_page.blocks, strict=True)
            }
            page_ocr = [
                self._to_ocr_block(block, ocr_by_index[block.index], page.page_number)
                if block.type in OCR_TYPES
                else None
                for block in blocks
            ]
            all_ocr_blocks.append(page_ocr)
        return all_ocr_blocks

    def _to_ocr_block(
            self, block: LayoutBlock, ocr_block, page_number: int
    ) -> OCRBlock:
        """Convert one surya BlockOCRResult into an OCRBlock.

        ``block`` is only used for error context — the OCRBlock itself is
        pure OCR output (no layout data).
        """
        if ocr_block.error:
            raise OCRError(
                f"OCR failed on page {page_number}, "
                f"block {block.index} ({block.label})"
            )
        if ocr_block.skipped:
            # Cannot legitimately happen: only Text-type blocks are sent,
            # and surya never skips those. Fail fast if it ever does.
            raise OCRError(
                f"surya unexpectedly skipped OCR on page {page_number}, "
                f"block {block.index} ({block.label})"
            )

        return OCRBlock(
            html=ocr_block.html,
            text=self.html_extractor.html_to_text(ocr_block.html),
            confidence=ocr_block.confidence,
        )

    @staticmethod
    def recreate_surya_layout_results(
            pages: list[RenderedPage], layout_blocks: list[list[LayoutBlock]]
    ) -> list[LayoutResult]:
        """Pages + per-page LayoutBlocks -> surya LayoutResults, one per page.

        LayoutBlock is the stable interface between pipeline stages, so
        surya types never leave this engine — this converts back just for
        the RecognitionPredictor call.
        """
        return [
            LayoutResult(
                bboxes=OCREngine.recreate_surya_layout_box(blocks),
                image_bbox=[0.0, 0.0, page.width, page.height],
            )
            for page, blocks in zip(pages, layout_blocks, strict=True)
        ]

    @staticmethod
    def recreate_surya_layout_box(blocks: list[LayoutBlock]) -> list[LayoutBox]:
        """LayoutBlocks -> surya LayoutBoxes, one per block."""
        return [_to_surya_layout_box(block) for block in blocks]
