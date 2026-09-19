from html.parser import HTMLParser
from typing import Any

# Tags whose content starts on a new visual line.
_NEWLINE_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}


class HtmlExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Any | None]]) -> None:
        if tag in _NEWLINE_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _NEWLINE_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        # Collapse the runs of whitespace each line down to single spaces,
        # drop empties, and keep line structure.
        lines = [line.strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)

    def html_to_text(self, html: str) -> str:
        """Convert a single block's OCR HTML to plain text"""
        if not html:
            return ""

        # This instance is reused across blocks — clear any state left
        # over from the previous block before feeding the next one.
        self._parts = []
        self.reset()

        self.feed(html)
        self.close()
        return self.text()
