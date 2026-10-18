import xml.etree.ElementTree as ET
from collections.abc import Iterator

from ebooklib import epub
from xml.etree.ElementTree import Element

from scriber.config import ScriberConfig
from scriber.domain import PageResult, ProcessedBlock
from scriber.enums import BlockType
from scriber.exceptions import ProcessingError

TERMINAL_PUNCTUATION_MARK = ["?", ".", "!"]


class EpubCreator:
    def __init__(self, config: ScriberConfig) -> None:
        self._book = epub.EpubBook()
        self._config = config

    def create_epub(self, page_results: list[PageResult]) -> str:
        for chapter_number, chapter_pages in enumerate(self._get_chapters(page_results)):
            chapter = epub.EpubHtml(title=f"Chapter {chapter_number}",
                                    file_name=f"chap_{chapter_number:03d}.xhtml",
                                    lang=self._config.language)

            chapter_content = self._handle_chapter(chapter_number, chapter_pages)
            chapter.content = chapter_content

        # TODO: actually generate the epub here
        return xhtml_string

    def _get_chapters(self, page_results: list[PageResult]) -> Iterator[list[PageResult]]:
        """
        Split list of page results in to its relevant chapters.
        Will also filter dropped ProcessedBlocks

        :param page_results: List of PageResult objects
        :return: Iterator containing list of page results grouped by chapter
        """
        temp_pages: list[PageResult] = []

        for page_result in page_results:
            if page_result.blocks[0].layout.type == BlockType.SECTION_HEADER:
                yield temp_pages
                continue

            filtered_page_blocks = [block for block in page_result.blocks if self._is_valid_block(block)]
            page_result.blocks = filtered_page_blocks
            temp_pages.append(page_result)

    def _handle_chapter(self, chapter_number: int, chapter_pages: list[PageResult]) -> str:
        chapter_root = ET.Element('div')
        page_merged = False

        for page_index, page_result in enumerate(chapter_pages):
            for block_index, block in enumerate(page_result.blocks):
                if block_index == 0 and page_index > 0 and page_merged:
                    # the current block should be merged in the previous block
                    print("skipping current block as it has been merged in previous block")
                    page_merged = False
                    continue

                if block.layout.type == BlockType.SECTION_HEADER:
                    self._handle_section_header(chapter_number, block, chapter_root)
                    continue

                if block.embed_as_image and block.crop_path is not None:
                    filename = self._embed_image(block)
                    ET.SubElement(chapter_root, 'img', src=filename, alt=f"Fig. {block_index}")
                    continue

                if block_index == len(page_result.blocks) - 1:
                    next_block = chapter_pages[page_index + 1].blocks[0]
                    is_page_merge_needed = self._is_page_merge_needed(block, next_block)

                    if is_page_merge_needed:
                        page_merged = True
                        self._handle_page_merge(block, next_block, chapter_root)
                        continue

                if block.ocr is not None and block.ocr.html is not None:
                    p = ET.SubElement(chapter_root, 'p')
                    p.text = block.ocr.html
                    continue

        return ET.tostring(chapter_root, encoding='unicode', method='xml')

    def _handle_section_header(
            self,
            chapter_number: int,
            block: ProcessedBlock,
            chapter_root: Element
    ) -> None:
        """
        :param chapter_number: The number of the chapter.
        :param block: Chapter block
        :param chapter_root: Chapter root element
        """
        if block.embed_as_image and block.crop_path is not None:
            filename = self._embed_image(block)
            h1 = ET.SubElement(chapter_root, 'h1')
            ET.SubElement(h1, 'img', src=filename, alt=f"Chapter {chapter_number}")

        elif block.ocr is not None:
            h1 = ET.SubElement(chapter_root, 'h1')
            h1.text = block.ocr.text

        else:
            raise ProcessingError(f"failed to get chapter title in block {block.id}")

    def _embed_image(self, block: ProcessedBlock) -> str:
        """
        Embed image in a block into the created epub.

        :param block: Block to be embedded in the epub.
        :return: filename string
        """
        if block.crop_path is None:
            raise ProcessingError(f"attempt to embed an empty image in {block.id}")

        filename = f"crops/image_{block.id}.png"
        image_item = epub.EpubImage()
        image_item.file_name = filename
        image_item.media_type = 'image/png'
        image_item.content = block.crop_path.read_bytes()

        self._book.add_item(image_item)
        return filename

    @staticmethod
    def _is_page_merge_needed(current_block: ProcessedBlock, next_block: ProcessedBlock, ) -> bool:
        if current_block.ocr is None or next_block.ocr is None:
            raise ProcessingError(
                f"either first_block with id {next_block.id} or last_block with id {current_block.id} is empty")

        last_block_text = current_block.ocr.text.strip()
        last_block_char = last_block_text[-1]

        # continuation mark
        if last_block_char == '-':
            return True

        # terminal punctuation mark usually indicates that the sentence is ending
        if last_block_char not in TERMINAL_PUNCTUATION_MARK:
            return True

        first_block_text = next_block.ocr.text.strip()
        first_block_char = first_block_text[0]

        # a continuation usually start with a lower case characters
        if first_block_char.islower():
            return True

        return False

    @staticmethod
    def _handle_page_merge(
            current_block: ProcessedBlock,
            next_block: ProcessedBlock,
            chapter_root: Element
    ) -> None:
        if current_block.ocr is None or next_block.ocr is None:
            raise ProcessingError(
                f"either first_block with id {next_block.id} or last_block with id {current_block.id} is empty")

        cleaned_current_block_html = current_block.ocr.html.replace('</p>', '')
        cleaned_next_block_html = next_block.ocr.html.replace('<p>', '')

        if cleaned_current_block_html[-1] == "-":
            cleaned_current_block_html = cleaned_current_block_html[:-1]

        p = ET.SubElement(chapter_root, 'p')
        p.text = cleaned_current_block_html + cleaned_next_block_html

    @staticmethod
    def _is_valid_block(block: ProcessedBlock) -> bool:
        if block.dropped:
            return False

        if block.embed_as_image and block.crop_path is None:
            return False

        if (
                block.embed_as_image == False and
                (block.ocr is None or (block.ocr.html is None and block.ocr.text is None))
        ):
            return False

        return True
