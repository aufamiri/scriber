"""Block processing.

Runs after OCR, per page:
- Type gate: only blocks of type Text / SectionHeader / Picture are
  processed; every other type (PageHeader, PageFooter, Other) is dropped
  with reason "excluded type ..." so it stays visible in the JSON dump.
- A page-number heuristic (surya has no PageNumber label — scan for a
  short digit/roman Text block hugging the bottom margin).
- Picture-type blocks -> always crop the bbox to a PNG and mark
  ``embed_as_image`` for the future EPUB stage.
- SectionHeader-type blocks (including promoted Titles) with confidence
  below the threshold -> crop the bbox as PNG and mark ``embed_as_image``
  (the OCR text is kept as best-effort metadata; the future EPUB stage
  embeds the image instead). Confident ones keep their text for the
  chapter TOC; un-OCR'd ones (``ocr is None``) always fall back to image
  embedding.
- Body Text (and other text labels) -> always kept as text regardless of
  confidence.

Each LayoutBlock (plus its optional OCRBlock) becomes a ProcessedBlock
(input models are never mutated). Dropped blocks stay in the page result
(``dropped=True`` + reason) so the JSON dump is fully inspectable; the
merge/structure stages will filter.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from scriber.config import ScriberConfig
from scriber.domain import LayoutBlock, OCRBlock, ProcessedBlock, RenderedPage
from scriber.enums import BlockType
from scriber.exceptions import ProcessingError

# The only block types that get processing decisions — every rule below
# keys on BlockType, never on the fine-grained surya label.
PROCESSED_TYPES = frozenset(
    {BlockType.TEXT, BlockType.SECTION_HEADER, BlockType.PICTURE}
)

# Page-number heuristic knobs (post-OCR, text-aware).
PAGE_NUM_MAX_LEN = 12
PAGE_NUM_BOTTOM_FRACTION = 0.10  # within the bottom 10% of the page

# Crop padding in pixels (mirrors surya's own block crop padding).
CROP_PAD = 4


def process_page(
        page: RenderedPage,
        layout_blocks: list[LayoutBlock],
        ocr_results: list[OCRBlock | None],
        config: ScriberConfig,
) -> list[ProcessedBlock]:
    crops_dir = config.cache_dir / "crops" / _job_dir(page.image_path)
    page_image = None  # loaded lazily on the first crop

    processed: list[ProcessedBlock] = []
    for block, ocr in zip(layout_blocks, ocr_results, strict=True):
        block_type = block.type

        if block_type not in PROCESSED_TYPES:
            processed.append(
                ProcessedBlock(
                    layout=block,
                    ocr=ocr,
                    dropped=True,
                    drop_reason=f"excluded type {block_type.value!r}",
                )
            )
            continue

        if _looks_like_page_number(block, ocr, page):
            processed.append(
                ProcessedBlock(
                    layout=block, ocr=ocr, dropped=True, drop_reason="page number"
                )
            )
            continue

        if block.type == BlockType.PICTURE:
            page_image = _load_page_image(page, page_image)
            processed.append(
                ProcessedBlock(
                    layout=block,
                    ocr=ocr,
                    crop_path=_crop(page_image, block, crops_dir, page.page_number),
                    embed_as_image=True,
                )
            )
            continue

        if block.type == BlockType.SECTION_HEADER and (
                ocr is None
                or ocr.confidence is None
                or ocr.confidence < config.title_confidence_threshold
        ):
            # Low-confidence (or un-OCR'd) title: keep whatever text we have
            # as best effort, but flag the block for image embedding in the
            # future EPUB stage.
            page_image = _load_page_image(page, page_image)
            processed.append(
                ProcessedBlock(
                    layout=block,
                    ocr=ocr,
                    crop_path=_crop(page_image, block, crops_dir, page.page_number),
                    embed_as_image=True,
                )
            )
            continue

        # Body Text and friends: always kept as text, regardless of confidence.
        processed.append(ProcessedBlock(layout=block, ocr=ocr))

    return processed


def _job_dir(page_image_path: Path) -> str:
    """Derive the job directory name from the page image path layout.

    Page images live at ``<cache_dir>/pages/<job_id>/page_NNNN.png``.
    """
    return page_image_path.parent.name


def _load_page_image(page: RenderedPage, current: Image.Image | None) -> Image.Image:
    if current is not None:
        return current
    try:
        return Image.open(page.image_path)
    except OSError as e:
        raise ProcessingError(
            f"failed to open page image {page.image_path}: {e}"
        ) from e


def _crop(
        image: Image.Image,
        block: LayoutBlock,
        crops_dir: Path,
        page_number: int,
) -> Path:
    x0, y0, x1, y1 = block.bbox
    try:
        left = max(0, int(x0) - CROP_PAD)
        top = max(0, int(y0) - CROP_PAD)
        right = min(image.width, int(x1) + CROP_PAD)
        bottom = min(image.height, int(y1) + CROP_PAD)
    except (TypeError, ValueError) as e:
        raise ProcessingError(
            f"bad crop bbox {block.bbox!r} on page {page_number}, "
            f"block {block.index} ({block.label}): {e}"
        ) from e
    if right <= left or bottom <= top:
        raise ProcessingError(
            f"degenerate crop bbox {block.bbox!r} on page {page_number}, "
            f"block {block.index} ({block.label})"
        )

    crops_dir.mkdir(parents=True, exist_ok=True)
    dest = crops_dir / f"p{page_number:04d}_b{block.index:03d}_{block.label}.png"
    try:
        image.crop((left, top, right, bottom)).save(dest)
    except (OSError, ValueError) as e:
        raise ProcessingError(
            f"failed to save crop {dest} (page {page_number}, "
            f"block {block.index}): {e}"
        ) from e
    return dest


def _looks_like_page_number(
        block: LayoutBlock, ocr: OCRBlock | None, page: RenderedPage
) -> bool:
    """Heuristic: short digit/roman text block near the bottom margin."""
    # Page numbers are Text-type blocks (Caption is excluded by the type
    # gate before processing ever runs).
    if block.type != BlockType.TEXT:
        return False
    if ocr is None:
        return False
    text = ocr.text.strip()
    if not text or len(text) > PAGE_NUM_MAX_LEN:
        return False

    digits = sum(ch.isdigit() for ch in text)
    letters = sum(ch.isalpha() for ch in text)
    if digits == 0 and letters == 0:
        return False
    # Roman numerals (iv, vii, xii) are letters-only — allow them.
    is_roman = letters == len(text.replace(" ", "")) and text.lower().rstrip() in (
        "i",
        "ii",
        "iii",
        "iv",
        "v",
        "vi",
        "vii",
        "viii",
        "ix",
        "x",
        "xi",
        "xii",
        "xiii",
        "xiv",
        "xv",
    )
    is_numberish = digits >= len(text.replace(" ", "")) / 2
    if not (is_roman or is_numberish):
        return False

    bbox = block.bbox
    block_height = bbox[3] - bbox[1]
    if block_height > 0.04 * page.height:
        return False
    return bbox[3] >= page.height * (1 - PAGE_NUM_BOTTOM_FRACTION)
