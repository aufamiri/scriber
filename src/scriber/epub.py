import xml.etree.ElementTree as ET
from collections.abc import Iterator

from ebooklib import epub

from scriber.config import ScriberConfig
from scriber.domain import PageResult, ProcessedBlock
from scriber.enums import BlockType
from scriber.exceptions import ProcessingError


class EpubCreator:
    def __init__(self, config: ScriberConfig) -> None:
        self._book = epub.EpubBook()
        self._config = config
        self._content_root = ET.Element('div')

    def create_epub(self, page_results: list[PageResult]) -> str:

        for chapter_number, chapter_pages in enumerate(self._get_chapters(page_results)):
            for page_index, page_result in enumerate(chapter_pages):
                chapter = epub.EpubHtml(title=f"Chapter {chapter_number}",
                                        file_name=f"chap_{chapter_number:03d}.xhtml",
                                        lang=self._config.language)

                for block_index, block in enumerate(page_result.blocks):
                    if page_index == 0 and block_index == 0:
                        self._handle_section_header(chapter_number, block)
                        continue

                    # TODO: continue implement content creation
                    # TODO: implement epub merge logic, probably using punctuation heuristics and capitalization detection ( check gemini for more info )
                    p = ET.SubElement(self._content_root, 'p')
                    p.text = "This text is safely escaped. Characters like < and & are handled automatically."

        # 2. Convert the ElementTree structure directly to a string
        # Setting encoding='unicode' forces it to return a standard Python string instead of bytes
        xhtml_string = ET.tostring(self._content_root, encoding='unicode', method='xml')

        # 3. Inject it into ebooklib
        # ebooklib handles the outer <html>, <head>, and <body> wrappers automatically
        chapter = epub.EpubHtml(title='Chapter 1', file_name='chap_01.xhtml', lang='en')
        chapter.content = xhtml_string
        return xhtml_string

    @staticmethod
    def _get_chapters(page_results: list[PageResult]) -> Iterator[list[PageResult]]:
        temp_pages: list[PageResult] = []

        for page_result in page_results:
            if page_result.blocks[0].layout.type == BlockType.SECTION_HEADER:
                yield temp_pages
                continue

            filtered_page_blocks = [block for block in page_result.blocks if not block.dropped]
            page_result.blocks = filtered_page_blocks
            temp_pages.append(page_result)

    def _handle_section_header(self, chapter_number: int, block: ProcessedBlock) -> None:
        if block.embed_as_image and block.crop_path is not None:
            filename = f"crops/title_{chapter_number:03d}.png"
            image_item = epub.EpubImage()
            image_item.file_name = filename
            image_item.media_type = 'image/png'
            image_item.content = block.crop_path.read_bytes()

            self._book.add_item(image_item)

            h1 = ET.SubElement(self._content_root, 'h1')
            ET.SubElement(h1, 'img', src=filename, alt=f"Chapter {chapter_number}")
        elif block.ocr is not None:
            h1 = ET.SubElement(self._content_root, 'h1')
            h1.text = block.ocr.text
        else:
            raise ProcessingError(f"failed to get chapter title in block {block.id}")
