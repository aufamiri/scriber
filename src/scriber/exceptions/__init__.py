"""Custom exceptions, one class per file.
"""

from scriber.exceptions.LayoutError import LayoutError
from scriber.exceptions.OCRError import OCRError
from scriber.exceptions.ProcessingError import ProcessingError

__all__ = ["LayoutError", "OCRError", "ProcessingError"]
