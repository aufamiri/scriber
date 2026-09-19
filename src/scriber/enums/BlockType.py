from __future__ import annotations

from enum import StrEnum


class BlockType(StrEnum):
    """Coarse block category derived from the surya layout label (novel
    scope — the full surya-label correspondence is in ``LABEL_TO_TYPE``
    just below this class).

    Stages gate on this: OCR runs on TEXT and SECTION_HEADER; block
    processing handles only TEXT / SECTION_HEADER / PICTURE. StrEnum members
    are plain strings, so comparisons and the JSON dump behave exactly
    like the raw string values.
    """

    TEXT = "Text"
    SECTION_HEADER = "SectionHeader"
    PAGE_HEADER = "PageHeader"
    PAGE_FOOTER = "PageFooter"
    PICTURE = "Picture"
    OTHER = "Other"

    @classmethod
    def from_surya_label(cls, surya_label: str) -> BlockType:
        """Coarse type for a surya layout label (OTHER if unmapped).

        Everything unmapped (Caption, Footnote, Code, Bibliography, Table,
        Equation, ListGroup, Form, TableOfContents, BlankPage) is out of
        scope for novels and lands on OTHER.
        """
        return LABEL_TO_TYPE.get(surya_label, cls.OTHER)


# surya layout label -> BlockType, grounded in surya's own label tiers
# (layout.label.TEXT_LABELS = text-bearing; inference.prompts
# SKIP_OCR_LABELS = purely visual).
LABEL_TO_TYPE: dict[str, BlockType] = {
    "Text": BlockType.TEXT,
    # Promoted chapter titles (our layout heuristic) behave as section
    # headers downstream.
    "Title": BlockType.SECTION_HEADER,
    "SectionHeader": BlockType.SECTION_HEADER,
    "PageHeader": BlockType.PAGE_HEADER,
    "PageFooter": BlockType.PAGE_FOOTER,
    "Picture": BlockType.PICTURE,
    "Figure": BlockType.PICTURE,
    "Diagram": BlockType.PICTURE,
    # Chemistry diagrams — structured, but for our purposes a visual to
    # embed as an image (same treatment as the rest of the picture family).
    "ChemicalBlock": BlockType.PICTURE,
}
