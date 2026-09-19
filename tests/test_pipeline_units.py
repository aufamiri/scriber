"""Unit tests for the pure-Python pipeline stages.

Tests the title promotion heuristic, the label→type mapping, the block
processing rules, the HTML-to-text conversion, and the job-id
memoization. No surya needed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image

from scriber.config import ScriberConfig
from scriber.domain import LayoutBlock, OCRBlock, RenderedPage
from scriber.enums import BlockType
from scriber.helpers import HtmlExtractor
from scriber.layout import _promote_titles
from scriber.processing import process_page
from scriber.utils import JobIdUtil

PAGE_W, PAGE_H = 1000, 1600


def make_layout_block(index, label, bbox, **kwargs) -> LayoutBlock:
    """LayoutBlock with the type auto-derived from the label, as
    LayoutDetector would produce it."""
    return LayoutBlock(
        index=index,
        label=label,
        bbox=bbox,
        reading_order=index,
        type=BlockType.from_surya_label(label),
        **kwargs,
    )


def make_block_with_ocr(
    index, label, bbox, text="", confidence=None, ocr=True
) -> tuple[LayoutBlock, OCRBlock | None]:
    """(LayoutBlock, OCRBlock|None) pair as the pipeline hands them to
    processing — ``ocr=False`` for block types that are never OCR'd
    (Picture, headers, chapter markers: anything outside ocr.OCR_TYPES).
    """
    block = make_layout_block(index, label, bbox)
    result = OCRBlock(text=text, confidence=confidence) if ocr else None
    return block, result


# ---- Label -> type mapping (novel scope) ------------------------------------


def test_label_to_type_mapping():
    assert BlockType.from_surya_label("Text") == BlockType.TEXT
    # Promoted chapter titles behave as section headers.
    assert BlockType.from_surya_label("Title") == BlockType.SECTION_HEADER
    assert BlockType.from_surya_label("SectionHeader") == BlockType.SECTION_HEADER
    assert BlockType.from_surya_label("PageHeader") == BlockType.PAGE_HEADER
    assert BlockType.from_surya_label("PageFooter") == BlockType.PAGE_FOOTER
    # The visual family collapses into one type.
    assert BlockType.from_surya_label("Picture") == BlockType.PICTURE
    assert BlockType.from_surya_label("Figure") == BlockType.PICTURE
    assert BlockType.from_surya_label("Diagram") == BlockType.PICTURE
    assert BlockType.from_surya_label("ChemicalBlock") == BlockType.PICTURE
    # Out-of-scope labels (novels don't have these).
    assert BlockType.from_surya_label("Caption") == BlockType.OTHER
    assert BlockType.from_surya_label("Footnote") == BlockType.OTHER
    assert BlockType.from_surya_label("Code") == BlockType.OTHER
    assert BlockType.from_surya_label("Table") == BlockType.OTHER
    assert BlockType.from_surya_label("Equation") == BlockType.OTHER
    assert BlockType.from_surya_label("TableOfContents") == BlockType.OTHER
    assert BlockType.from_surya_label("BlankPage") == BlockType.OTHER


def test_block_type_is_str_compatible():
    # StrEnum members are plain strings — the closed vocabulary comes for
    # free without changing comparisons or the JSON dump.
    assert BlockType.TEXT == "Text"
    assert BlockType.SECTION_HEADER == "SectionHeader"
    assert {BlockType.TEXT, BlockType.PICTURE} == {"Text", "Picture"}


# ---- Title promotion heuristic ---------------------------------------------


def test_promotes_centered_large_isolated_text_to_title():
    # Tall centered block with big vertical gaps, among normal body text.
    blocks = [
        make_layout_block(0, "Text", (100, 200, 900, 300)),  # normal body text
        make_layout_block(1, "Text", (300, 600, 700, 780)),  # centered + tall + isolated
        make_layout_block(2, "Text", (100, 1200, 900, 1300)),  # normal body text
    ]
    _promote_titles(blocks, PAGE_W, PAGE_H)
    assert blocks[1].label == "Title"
    assert blocks[0].label == "Text" and blocks[2].label == "Text"


def test_does_not_promote_offcenter_tall_block():
    blocks = [
        make_layout_block(0, "Text", (100, 200, 900, 300)),
        make_layout_block(1, "Text", (60, 600, 500, 780)),  # tall but left-aligned
        make_layout_block(2, "Text", (100, 1200, 900, 1300)),
    ]
    _promote_titles(blocks, PAGE_W, PAGE_H)
    assert all(b.label == "Text" for b in blocks)


def test_does_not_promote_without_section_header_when_not_large():
    # All blocks similar height — nothing stands out.
    blocks = [
        make_layout_block(i, "Text", (100, 200 + i * 100, 900, 260 + i * 100))
        for i in range(5)
    ]
    _promote_titles(blocks, PAGE_W, PAGE_H)
    assert all(b.label == "Text" for b in blocks)


def test_skips_heuristic_when_section_header_present():
    blocks = [
        make_layout_block(0, "SectionHeader", (100, 100, 900, 180)),
        make_layout_block(1, "Text", (300, 600, 700, 780)),  # would qualify otherwise
        make_layout_block(2, "Text", (100, 1200, 900, 1300)),
    ]
    _promote_titles(blocks, PAGE_W, PAGE_H)
    assert blocks[1].label == "Text"


# ---- Block processing -------------------------------------------------------


def _make_page(tmp: Path) -> tuple[RenderedPage, ScriberConfig]:
    image_path = tmp / "pages" / "job" / "page_0000.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (PAGE_W, PAGE_H), "white").save(image_path)
    config = ScriberConfig(
        dpi=200, title_confidence_threshold=0.5, cache_dir=tmp, page_batch_size=1
    )
    page = RenderedPage(
        page_number=0,
        image_path=image_path,
        width=PAGE_W,
        height=PAGE_H,
    )
    return page, config


def test_block_processing_rules(tmp_path: Path):
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        block_inputs = [
            # PageHeader: never OCR'd, excluded by the type gate (like
            # PageFooter — no per-label drop rule anymore).
            make_block_with_ocr(0, "PageHeader", (100, 20, 900, 60), ocr=False),
            # Text page number at the bottom: OCR'd, dropped by heuristic.
            make_block_with_ocr(1, "Text", (430, 1540, 570, 1570), text="12"),
            # Picture: never OCR'd, always cropped + image-embedded.
            make_block_with_ocr(2, "Picture", (200, 200, 800, 500), ocr=False),
            # Title with low-confidence OCR: image-embedded.
            make_block_with_ocr(
                3, "Title", (300, 700, 700, 760), text="Bab 1", confidence=0.3
            ),
            # Title with confident OCR: kept as text for the chapter TOC.
            make_block_with_ocr(
                4, "Title", (300, 900, 700, 960), text="Bab 2", confidence=0.95
            ),
            # Title with no OCR at all: the un-OCR'd fallback — always
            # image-embedded.
            make_block_with_ocr(5, "Title", (300, 1100, 700, 1160), ocr=False),
            # Low-confidence body text: still kept as text.
            make_block_with_ocr(
                6, "Text", (100, 1000, 900, 1050), text="body", confidence=0.1
            ),
            # PageFooter: excluded type, never OCR'd.
            make_block_with_ocr(7, "PageFooter", (100, 1580, 900, 1595), ocr=False),
            # Caption -> type Other: excluded, never OCR'd.
            make_block_with_ocr(8, "Caption", (100, 300, 900, 340), ocr=False),
            # ChemicalBlock -> type Picture: cropped + image-embedded like
            # any visual.
            make_block_with_ocr(9, "ChemicalBlock", (150, 400, 850, 480), ocr=False),
        ]
        layout_blocks = [block for block, _ in block_inputs]
        ocr_results = [ocr for _, ocr in block_inputs]
        page, config = _make_page(tmp)

        processed = process_page(page, layout_blocks, ocr_results, config)
        (header, page_num, picture, low_title, high_title, no_ocr_title, body, footer, caption, chem) = (
            processed
        )

        assert header.dropped
        assert header.drop_reason is not None and "PageHeader" in header.drop_reason
        assert header.ocr is None  # never OCR'd
        assert page_num.dropped and page_num.drop_reason == "page number"
        assert picture.crop_path is not None and picture.embed_as_image
        assert picture.ocr is None
        assert low_title.crop_path is not None and low_title.embed_as_image
        assert high_title.crop_path is None and not high_title.embed_as_image
        assert no_ocr_title.crop_path is not None and no_ocr_title.embed_as_image
        assert no_ocr_title.ocr is None
        assert not body.dropped and body.crop_path is None
        assert footer.dropped and "PageFooter" in (footer.drop_reason or "")
        assert caption.dropped and "Other" in (caption.drop_reason or "")
        assert chem.crop_path is not None and chem.embed_as_image
        assert (tmp / "crops" / "job").is_dir()
        assert Path(picture.crop_path).is_file()
        assert Path(low_title.crop_path).is_file()


def test_processing_does_not_mutate_input_models(tmp_path: Path):
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        ocr = OCRBlock(text="Bab 1", confidence=0.3)
        layout_blocks = [make_layout_block(0, "Title", (300, 700, 700, 760))]
        ocr_results: list[OCRBlock | None] = [ocr]
        page, config = _make_page(tmp)

        processed = process_page(page, layout_blocks, ocr_results, config)

        # The LayoutBlock and OCRBlock are untouched — all decisions live
        # on the ProcessedBlock, which references the same objects.
        assert ocr.confidence == 0.3
        assert layout_blocks[0].label == "Title"
        assert processed[0].embed_as_image
        assert processed[0].layout is layout_blocks[0]
        assert processed[0].ocr is ocr


def test_bottom_text_that_is_not_a_page_number_is_kept(tmp_path: Path):
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        layout_blocks = [make_layout_block(0, "Text", (100, 1530, 900, 1570))]
        ocr_results: list[OCRBlock | None] = [
            OCRBlock(text="Selesai bab pertama, bersambung ke bab berikutnya")
        ]
        page, config = _make_page(tmp)
        processed = process_page(page, layout_blocks, ocr_results, config)
        assert not processed[0].dropped


# ---- HTML -> text -----------------------------------------------------------


def test_html_to_text():
    # Fresh extractor per call — documents the intended per-block usage.
    def to_text(html: str) -> str:
        return HtmlExtractor().html_to_text(html)

    html = "<p>Hello <i>world</i>,</p><p>selamat <b>pagi</b>!</p>"
    assert to_text(html) == "Hello world,\nselamat pagi!"

    assert to_text("line one<br/>line two") == "line one\nline two"
    assert to_text("caf&eacute; &amp; kopi") == "café & kopi"
    assert to_text("") == ""
    assert to_text("<div>   </div><div></div>") == ""


def test_html_extractor_state_does_not_leak_between_calls():
    # OCREngine holds ONE HtmlExtractor for the whole run — a reused
    # instance must not carry text from earlier blocks into later ones.
    extractor = HtmlExtractor()
    first = extractor.html_to_text("<p>first block</p>")
    second = extractor.html_to_text("<p>second block</p>")

    assert first == "first block"
    assert second == "second block", (
        "HtmlExtractor accumulates state across calls — every block after "
        "the first would contain all previous blocks' text"
    )


# ---- JobIdUtil: job id memoization ------------------------------------------


def test_job_id_is_memoized_and_content_sensitive(tmp_path: Path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"hello")
    util = JobIdUtil()

    first = util.get_job_id(pdf)
    assert util.get_job_id(pdf) == first  # memo hit, no re-hash

    # A different file hashed by a fresh util yields a different id.
    other = tmp_path / "b.pdf"
    other.write_bytes(b"hello world, different content")
    assert JobIdUtil().get_job_id(other) != first
