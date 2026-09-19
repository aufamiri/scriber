# PDF-to-EPUB OCR Converter — Project Plan

## 1. Background

Existing PDF-to-EPUB converters lack quality OCR for scanned documents, particularly for Indonesian language novels. Most solutions either rely on embedded PDF text (which scanned PDFs lack), use Tesseract (which performs poorly on Indonesian), or require extensive manual correction of OCR artifacts.

The goal is a converter specifically tuned for scanned novel PDFs with proper chapter structure and save/resume capability.

## 2. Scope

### 2.1 Functional requirement

- Create a PDF-to-EPUB converter for scanned (image-based) PDFs using OCR
- Support Indonesian and English languages
- Detect and preserve chapter headings / titles in the EPUB structure
- Save work-in-progress state per page, resume from any checkpoint

### 2.2 Non-functional requirement

- Modular architecture with replaceable components
- Clear interfaces between pipeline stages so we can swap OCR engines, layout detectors, or rasterizers later

## 3. Architecture & Modules

| Module | Responsibility |
| --- | --- |
| `Rasterizer` | PDF → per-page PNG images at a fixed DPI |
| `LayoutDetector` | Image → layout blocks + reading order |
| `OCR` | Image + blocks → recognized text + confidence |
| `Pipeline` | Orchestrate the full flow: SQLite state handling, block processing, page merging, chapter structuring, and EPUB assembly |

This way, if needed we can customize/ change `Rasterizer`, `LayoutDetector`, and `OCR`.

## 4. Bill of Materials

- **Language**: Python 3.10+
- **State database**: SQLite (per-page checkpointing)
- **PDF rasterizer**: PyMuPDF (`fitz`) — render pages to PNG at 200 DPI (default), 300 DPI max
- **Layout detection**: Surya (`surya_layout`, `surya_order`)
- **Text recognition**: Surya (`surya_ocr`)
- **Image cropper**: PIL (crop bounding boxes from rendered page PNGs)
- **EPUB assembly**: `ebooklib`

## 5. Configurations

- **Title Confidence threshold**: 0.5 (tunable) for image-embed fallback on titles
- **DPI**: 200 default
- **Cache directory**: `~/.cache/pdf-ocr/`

## 6. Configuration Schema

Configuration precedence (highest to lowest):

1. CLI arguments
2. Environment variables (`PDF_OCR_*`)
3. Config file (`~/.config/pdf-ocr/config.yaml`)
4. Hard-coded defaults

Tunable values:

- `dpi`
- `title_confidence_threshold`
- `cache_dir`
- `surya_inference_parallel` for the Surya VLM backend
- `detector_batch_size` for the Surya text-line detection model

## 7. CLI / Usage

Resume is auto-detected. If a state record for the same source file exists and has unmerged pages, the pipeline resumes from the first incomplete page. Otherwise, it starts a new job.

```bash
# Convert a PDF (auto-resumes if interrupted)
pdf-ocr convert Bumi.pdf --output Bumi.epub

# Provide EPUB metadata
pdf-ocr convert Bumi.pdf --output Bumi.epub --title "Bumi" --author "Tere Liye"

# Force a fresh start, ignoring any existing state
pdf-ocr convert Bumi.pdf --output Bumi.epub --force

# Use a custom cache / config
pdf-ocr convert Bumi.pdf --cache-dir /tmp/pdf-ocr --config ./config.yaml
```

## 8. Flow

1. **PDF to image rasterizer** — PyMuPDF renders each page to PNG; scan quality is the hard ceiling (cannot upscale what isn't there)
2. **Save-state handler** — track per-page status (`pending` → `layout_done` → `ocr_done` → `merged`); resume from last incomplete page
3. **Layout detection + reading order** — Surya classifies blocks per page (Text, Title, SectionHeader, Picture, Header, Footer, PageNumber); fallback heuristic forces Title on centered + large + isolated blocks
4. **OCR text** — per Text/Title/SectionHeader block; output text + avg_confidence + per_char_confidences; stored in state DB
5. **Block processing** — drop Header/Footer/PageNumber blocks entirely; Title/SectionHeader with confidence < 0.5 -> crop bbox as PNG and embed as `<img>`; Picture blocks → always embed; Body Text → always keep as text regardless of confidence
6. **Page merge** — merge consecutive Body Text blocks across page boundaries into single paragraphs (strip hard newlines, fix hyphenation). Hyphenation correction is language-aware: for English, strip trailing `-` and join (`"exam- ple" → "example"`); for Indonesian, trailing `-` is rare, so only join when the next token starts with a lowercase letter or is a known continuation. If the language is uncertain, keep the newline and let the reader handle it.
7. **Structure detection** — Title/SectionHeader blocks (text or image-embedded) mark chapter boundaries; group Body blocks into chapters; cover page is always separate. Page 0 is assumed to be the cover page.
   > **Known risk**: Title/SectionHeader blocks with OCR confidence below the threshold are embedded as images, so their text is invisible to the TOC generator. If this becomes common, fall back to numbering chapters in the TOC (e.g., "Chapter 1", "Chapter 2") instead of using the title text.
8. **EPUB assembly** — one XHTML per chapter, TOC from detected boundaries, manifest includes all XHTML and referenced image crops, basic novel CSS
9. **Delete data in SQLite and temp folder** — delete SQLite rows and temp folders after all jobs completed

## 9. Error Handling

The pipeline is intentionally fail-fast for the MVP. If a page or stage encounters an error, the CLI raises the exception and exits with a non-zero status. The user can re-run the command; resume will pick up from the last successfully checkpointed page. Per-page failure tracking, retries, and skip-and-continue behavior are deferred to future versions.

## 10. Resume & State Machine

- Resume is auto-detected based on the source file:
  - If a job for the same PDF already exists ( detected by content hash ) and has unmerged pages, resume from the first incomplete page.
  - If no job exists, create a new job and start from page 0.
  - Use `--force` to delete existing job and start fresh.
- Page statuses: `pending`, `layout_done`, `ocr_done`, `merged`
- On startup, find the first page to process:

  ```sql
  SELECT MIN(page_number) FROM pages
  WHERE job_id = ? AND status != 'merged';
  ```

- Re-processing a page is idempotent: update the same row with new results

## 11. SQLite Tables

### 11.1 Job

Stores list of pending/completed jobs.

| name | type | usage / notes |
| --- | --- | --- |
| id | text | based on content hash, primary key |
| created_at | integer | unix seconds |
| updated_at | integer | unix seconds |
| source_path | text | original file path |
| filename | text | filename |
| total_pages | integer | |

```sql
CREATE UNIQUE INDEX idx_job ON job(id);
```

### 11.2 Pages

Stores per-page status for checkpointing.

| name          | type    | usage / notes                                  |
| ------------- | ------- | ---------------------------------------------- |
| id            | integer | primary key, auto-increment                    |
| created_at    | integer | unix seconds                                   |
| updated_at    | integer | unix seconds                                   |
| job_id        | text    | foreign key to `job` table                     |
| page_number   | integer |                                                |
| status        | text    | `pending`, `layout_done`, `ocr_done`, `merged` |
| layout_result | text    | layout detection result (JSON)                 |
| ocr_result    | text    | OCR result (JSON)                              |
| image_path    | text    | temporary page PNG path                        |

```sql
CREATE UNIQUE INDEX idx_pages_job_page ON pages(job_id, page_number);
CREATE INDEX idx_pages_job_status ON pages(job_id, status);
CREATE INDEX idx_pages_job_page_status ON pages(job_id, page_number, status);
```

## 12. File Path

Temporary files are stored in `~/.cache/pdf-ocr/*`. This follows the standard XDG cache convention.

Sample:

```
~/.cache/pdf-ocr/
  ├── pages/<job_hash>/page_000.png
  ├── pages/<job_hash>/page_001.png
  ├── crops/<job_hash>/title_000.png
  └── state.db
```

## 13. Output EPUB Specification

- EPUB version: 3.2
- One XHTML file per detected chapter
- Cover page is always its own chapter
- Table of Contents built from chapter boundaries
- Metadata: title, author
- Basic novel CSS: readable font, paragraph spacing, no justified hyphenation
- Images embedded in EPUB manifest and referenced from XHTML

## 14. Future Improvements

- Binarization, deskew, and other image pre-processing — **future work only**; neural OCR is trained on grayscale/color and binarization may destroy signal
- Inline text styling (bold, italic) — **out of scope for v1; all output is plain text**
