import hashlib
from pathlib import Path


class JobIdUtil:
    def __init__(self):
        self._job_id = None

    def get_job_id(self, pdf_path: Path) -> str:
        """Stable job identifier from the source file's content hash.

        Used to namespace all temporary artifacts for this PDF. This is the
        same key the future save-state handler will use for the job table.
        """
        if self._job_id is not None:
            return self._job_id

        digest = hashlib.sha256()
        try:
            with open(pdf_path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    digest.update(chunk)
        except OSError as e:
            raise OSError(f"failed to hash source PDF {pdf_path}: {e}") from e
        hex_digest = digest.hexdigest()[:16]
        self._job_id = hex_digest

        return hex_digest
