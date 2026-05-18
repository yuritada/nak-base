"""
PDF Parser Service
Phase 1.3: Docling-based PDF parsing with semantic layout analysis

Uses Docling (IBM) for:
- Semantic element recognition (Paragraph, SectionHeader, Table, etc.)
- Bounding box extraction with correct 2-column reading order
- Markdown export

Memory/performance notes:
- OCR is disabled by default (PARSER_USE_OCR=true to enable).
  Digital PDFs already contain embedded text; OCR adds ~1-2 GB of model
  weights AND renders every page as a full-resolution image – the dominant
  cause of memory pressure for academic PDF workloads.
- GPU acceleration is configured explicitly via AcceleratorOptions so that
  layout-analysis and table-structure models run on CUDA when available.
- gc.collect() + torch.cuda.empty_cache() are called after every parse to
  release intermediate tensors and prevent accumulation across requests.

Debug/memory logging:
- Set PARSER_DEBUG_MEMORY=true to enable per-stage RSS memory snapshots.
  These are printed to stderr and do NOT require debug=True.
- Set PARSER_DEBUG=true (or pass debug=True) for detailed pipeline traces.
"""
import gc
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple

from ..schemas import ChunkData, DocumentMeta, PageData, ParseResponse, TextItem

# ── Runtime knobs (set via environment variables) ─────────────────────────────
# Set PARSER_USE_OCR=true only for scanned (image-only) PDFs.
# Enabling OCR for digital PDFs causes 3-5× memory overhead and 10× slowdown.
_USE_OCR: bool = os.getenv("PARSER_USE_OCR", "false").lower() == "true"

# Set PARSER_DEBUG_MEMORY=true to print RSS memory snapshots at each stage.
_DEBUG_MEMORY: bool = os.getenv("PARSER_DEBUG_MEMORY", "false").lower() == "true"
# Set PARSER_DEBUG=true as an alternative to passing debug=True at construction.
_DEBUG_ENV: bool = os.getenv("PARSER_DEBUG", "false").lower() == "true"


# ── Memory snapshot helper ─────────────────────────────────────────────────────

def _rss_mb() -> float:
    """Return current process RSS in MB. Uses psutil when available, otherwise
    falls back to /proc/self/status (Linux) or resource module."""
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1024 ** 2
    except ImportError:
        pass
    try:
        import resource
        # ru_maxrss is KB on Linux, bytes on macOS
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        import platform
        return raw / 1024 if platform.system() == "Darwin" else raw / 1024
    except Exception:
        return -1.0


_mem_baseline: float = 0.0  # set at module import time
_mem_baseline = _rss_mb()


def _mlog(label: str, extra: str = "") -> None:
    """Print a memory snapshot line to stderr (only when _DEBUG_MEMORY is set)."""
    if not _DEBUG_MEMORY:
        return
    rss = _rss_mb()
    delta = rss - _mem_baseline
    parts = [
        f"[MEM] {label:<50}",
        f"RSS={rss:7.0f} MB",
        f"delta={delta:+7.0f} MB",
    ]
    if extra:
        parts.append(extra)
    print("  ".join(parts), file=sys.stderr, flush=True)

# Docling label → our element_type string
_LABEL_TYPE_MAP: Dict[str, str] = {
    "text": "Paragraph",
    "section_header": "SectionHeader",
    "title": "Title",
    "table": "Table",
    "picture": "Figure",
    "figure": "Figure",
    "list_item": "ListItem",
    "code": "Code",
    "formula": "Formula",
    "page_header": "PageHeader",
    "page_footer": "PageFooter",
    "caption": "Caption",
    "footnote": "Footnote",
}

_HEADING_TYPES = {"SectionHeader", "Title"}
_NOISE_TYPES = {"PageHeader", "PageFooter"}
# Elements that must not be split or filtered by figure containment
_ATOMIC_TYPES = {"Table", "Formula"}


def _label_str(label) -> str:
    """Normalise a Docling DocItemLabel to a plain lowercase string."""
    if hasattr(label, "value"):
        return label.value.lower()
    return str(label).lower().split(".")[-1]


def _clean_japanese_text(text: str) -> str:
    """Remove unnecessary whitespace inserted between Japanese characters.

    Docling sometimes inserts a space at line-wrap points inside Japanese text,
    breaking search and embedding quality.
    """
    jp = r'[ぁ-んァ-ヶー一-龠々〆〇]'
    jp_punct = r'[ぁ-んァ-ヶー一-龠々〆〇、。！？…―]'
    # Remove spaces/newlines between two Japanese chars
    text = re.sub(rf'({jp})\s+({jp})', r'\1\2', text)
    # Remove spaces between Japanese char and full-width punctuation (both directions)
    text = re.sub(rf'({jp})\s+({jp_punct})', r'\1\2', text)
    text = re.sub(rf'({jp_punct})\s+({jp})', r'\1\2', text)
    return text


def _bbox_overlap_ratio(inner: List[float], outer: List[float]) -> float:
    """Return the fraction of the inner bbox area that is covered by outer bbox.

    Works regardless of coordinate orientation (PDF vs screen space) because we
    normalise each bbox so that min <= max before computing the intersection.
    """
    l1, t1, r1, b1 = inner
    l2, t2, r2, b2 = outer

    il, ir = min(l1, r1), max(l1, r1)
    it, ib = min(t1, b1), max(t1, b1)
    ol, or_ = min(l2, r2), max(l2, r2)
    ot, ob = min(t2, b2), max(t2, b2)

    xi = max(il, ol)
    xa = min(ir, or_)
    yi = max(it, ot)
    ya = min(ib, ob)

    if xi >= xa or yi >= ya:
        return 0.0

    inner_area = (ir - il) * (ib - it)
    if inner_area <= 0:
        return 0.0

    return (xa - xi) * (ya - yi) / inner_area


class PDFParser:
    """Docling-based PDF parser with semantic structure and coordinate extraction."""

    def __init__(self, debug: bool = False):
        self.debug = debug or _DEBUG_ENV
        self._converter = None  # lazy-loaded on first request
        _mlog("PDFParser.__init__")

    @property
    def converter(self):
        """Return the singleton DocumentConverter, creating it on first access.

        Pipeline options are chosen for digital (born-digital) PDFs:
        - do_ocr=False : avoids EasyOCR model loading and full-page rasterisation,
                         the single largest source of RAM pressure.
        - do_table_structure=True : table cell recognition via TableFormer (GPU).
        - AcceleratorOptions : explicitly routes layout and table models to CUDA
                               so PyTorch infers on the GPU when available.
        """
        if self._converter is None:
            _mlog("converter init: before imports")
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
            from docling.datamodel.base_models import InputFormat
            _mlog("converter init: after docling imports")

            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_table_structure = True
            pipeline_options.do_ocr = _USE_OCR

            if self.debug or _DEBUG_MEMORY:
                print(
                    f"[PDFParser] Pipeline opts: do_ocr={pipeline_options.do_ocr}  "
                    f"do_table_structure={pipeline_options.do_table_structure}",
                    file=sys.stderr,
                )

            # ── GPU acceleration ──────────────────────────────────────────
            # AcceleratorOptions was introduced in docling ≥ 2.5.
            # Fall back silently for older versions; docling defaults to AUTO.
            try:
                import torch
                _mlog("converter init: torch imported")

                cuda_avail = torch.cuda.is_available()
                if self.debug or _DEBUG_MEMORY:
                    print(f"[PDFParser] CUDA available: {cuda_avail}", file=sys.stderr)

                if cuda_avail:
                    device = AcceleratorDevice.CUDA
                else:
                    print(
                        "[PDFParser] WARNING: CUDA not available – running Docling on CPU (slow)",
                        file=sys.stderr,
                    )
                    device = AcceleratorDevice.CPU

                pipeline_options.accelerator_options = AcceleratorOptions(
                    num_threads=1,
                    device=device,
                )
                if self.debug:
                    print(f"[PDFParser] Accelerator device: {device.value}", file=sys.stderr)
            except (ImportError, AttributeError):
                if self.debug:
                    print("[PDFParser] AcceleratorOptions unavailable; using docling default", file=sys.stderr)

            # Formula enrichment is available in docling ≥ 2.7 (OCR mode only)
            if _USE_OCR:
                try:
                    pipeline_options.do_formula_enrichment = True
                except AttributeError:
                    pass

            _mlog("converter init: before DocumentConverter()")
            _t0 = time.perf_counter()
            self._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
            _elapsed = time.perf_counter() - _t0
            _mlog(f"converter init: after DocumentConverter()", extra=f"elapsed={_elapsed:.1f}s")

            if self.debug:
                print(f"[PDFParser] Converter ready (OCR={'on' if _USE_OCR else 'off'})", file=sys.stderr)
        return self._converter

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, file_path: str) -> ParseResponse:
        fname = os.path.basename(file_path)
        if self.debug:
            print(f"[PDFParser] Parsing: {file_path}", file=sys.stderr)
        _mlog(f"parse() start  {fname}")

        try:
            # ── Stage 1: convert PDF ──────────────────────────────────
            _mlog(f"parse() before convert()  {fname}")
            _t0 = time.perf_counter()
            result = self.converter.convert(file_path)
            doc = result.document
            _elapsed = time.perf_counter() - _t0
            _mlog(f"parse() after  convert()  {fname}", extra=f"elapsed={_elapsed:.1f}s")

            # ── Stage 2: metadata ──────────────────────────────────────
            _mlog(f"parse() before _extract_metadata  {fname}")
            meta = self._extract_metadata(doc, file_path)

            # ── Stage 3: extract pages/items ──────────────────────────
            _mlog(f"parse() before _extract_pages  {fname}")
            _t1 = time.perf_counter()
            pages, all_items = self._extract_pages(doc)
            _elapsed = time.perf_counter() - _t1
            _mlog(
                f"parse() after  _extract_pages  {fname}",
                extra=f"pages={len(pages)} items={len(all_items)} elapsed={_elapsed:.1f}s",
            )

            # ── Stage 4: markdown export ───────────────────────────────
            _mlog(f"parse() before export_to_markdown  {fname}")
            content = _clean_japanese_text(doc.export_to_markdown())
            _mlog(
                f"parse() after  export_to_markdown  {fname}",
                extra=f"md_len={len(content)}",
            )

            # ── Stage 5: free the heavy doc object ─────────────────────
            # Release the Docling document (and the result) *before* chunking
            # so that ML model tensors and page images are freed early.
            _mlog(f"parse() before del result/doc  {fname}")
            del result, doc
            gc.collect()
            _mlog(f"parse() after  del result/doc  {fname}")

            # ── Stage 6: chunking ──────────────────────────────────────
            _mlog(f"parse() before _generate_chunks  {fname}")
            chunks = self._generate_chunks(pages)
            _mlog(
                f"parse() after  _generate_chunks  {fname}",
                extra=f"chunks={len(chunks)}",
            )

            if self.debug:
                print(
                    f"[PDFParser] Done – {len(pages)} pages, "
                    f"{len(all_items)} items, {len(chunks)} chunks",
                    file=sys.stderr,
                )

            return ParseResponse(
                content=content,
                meta=meta,
                pages=pages,
                chunks=chunks,
            )
        finally:
            # Always release intermediate GPU tensors and Python objects so
            # that sequential multi-document parsing does not accumulate RAM.
            _mlog(f"parse() before _cleanup_memory  {fname}")
            self._cleanup_memory()
            _mlog(f"parse() after  _cleanup_memory  {fname}")

    # ------------------------------------------------------------------
    # Memory management
    # ------------------------------------------------------------------

    def _cleanup_memory(self) -> None:
        """Free intermediate GPU tensors and trigger Python GC."""
        _before = _rss_mb()
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                alloc = torch.cuda.memory_allocated() / 1024 ** 2
                resv = torch.cuda.memory_reserved() / 1024 ** 2
                if self.debug or _DEBUG_MEMORY:
                    print(
                        f"[PDFParser] VRAM after GC – "
                        f"allocated={alloc:.0f} MB  reserved={resv:.0f} MB",
                        file=sys.stderr,
                    )
        except ImportError:
            pass
        _after = _rss_mb()
        if _DEBUG_MEMORY:
            print(
                f"[MEM] _cleanup_memory  RSS before={_before:.0f} MB  "
                f"after={_after:.0f} MB  freed={_before - _after:+.0f} MB",
                file=sys.stderr,
                flush=True,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_metadata(self, doc, file_path: str) -> DocumentMeta:
        title: Optional[str] = None

        if getattr(doc, "name", None):
            title = doc.name

        if not title:
            for item, _ in doc.iterate_items():
                if _label_str(item.label) == "title":
                    text = getattr(item, "text", None)
                    if text:
                        title = text.strip()
                        break

        num_pages = len(doc.pages) if doc.pages else 0

        return DocumentMeta(
            title=title or os.path.basename(file_path),
            author=None,
            num_pages=num_pages,
            file_type="pdf",
            source_files=[os.path.basename(file_path)],
        )

    def _extract_pages(
        self, doc
    ) -> Tuple[List[PageData], List[TextItem]]:
        """Iterate Docling document items and group them by page.

        Two-pass approach:
        1. Collect all items with bboxes and apply Japanese text cleanup.
        2. Mark items whose bboxes fall inside a Figure region as non-content,
           preventing figure caption fragments from polluting the body text.
        """
        # Collect page dimensions
        page_dims: Dict[int, Tuple[float, float]] = {}
        if doc.pages:
            for page_no, page in doc.pages.items():
                size = getattr(page, "size", None)
                w = float(size.width) if size else 595.0
                h = float(size.height) if size else 842.0
                page_dims[int(page_no)] = (w, h)

        # ── Pass 1: collect raw items ─────────────────────────────────
        _mlog("_extract_pages: before iterate_items() pass-1")
        raw_items: List[Tuple[int, TextItem]] = []
        _item_count_by_type: Dict[str, int] = {}

        for item, _ in doc.iterate_items():
            label = _label_str(item.label)
            element_type = _LABEL_TYPE_MAP.get(label, "Paragraph")
            _item_count_by_type[element_type] = _item_count_by_type.get(element_type, 0) + 1

            text: Optional[str] = getattr(item, "text", None)
            if not text and label == "table" and hasattr(item, "export_to_markdown"):
                text = item.export_to_markdown()
            if not text or not text.strip():
                continue

            stripped = _clean_japanese_text(text.strip())
            is_heading = element_type in _HEADING_TYPES
            is_content_body = element_type not in _NOISE_TYPES

            # Short purely-numeric strings are likely page numbers
            if is_content_body and len(stripped) <= 5 and stripped.isdigit():
                is_content_body = False

            for prov in (item.prov or []):
                page_no = int(prov.page_no)
                bbox_obj = prov.bbox
                bbox = [
                    float(bbox_obj.l),
                    float(bbox_obj.t),
                    float(bbox_obj.r),
                    float(bbox_obj.b),
                ]

                text_item = TextItem(
                    text=stripped,
                    bbox=bbox,
                    font_size=None,
                    is_heading=is_heading,
                    element_type=element_type,
                    is_content_body=is_content_body,
                )
                raw_items.append((page_no, text_item))

        _mlog(
            "_extract_pages: after  iterate_items() pass-1",
            extra=f"raw_items={len(raw_items)} type_counts={_item_count_by_type}",
        )

        # ── Build Figure bbox index per page ──────────────────────────
        figure_bboxes: Dict[int, List[List[float]]] = {}
        for page_no, item in raw_items:
            if item.element_type == "Figure" and item.bbox:
                figure_bboxes.setdefault(page_no, []).append(item.bbox)

        # ── Pass 2: filter items that lie inside Figure regions ───────
        _mlog("_extract_pages: before pass-2 figure-filter")
        page_items: Dict[int, List[TextItem]] = {}
        all_items: List[TextItem] = []

        for page_no, item in raw_items:
            if (
                item.is_content_body
                and item.element_type not in _ATOMIC_TYPES
                and item.element_type != "Figure"
                and item.bbox
            ):
                for fig_bbox in figure_bboxes.get(page_no, []):
                    if _bbox_overlap_ratio(item.bbox, fig_bbox) >= 0.5:
                        item.is_content_body = False
                        break

            all_items.append(item)
            page_items.setdefault(page_no, []).append(item)

        _mlog(
            "_extract_pages: after  pass-2 figure-filter",
            extra=f"all_items={len(all_items)} pages_with_items={len(page_items)}",
        )

        # ── Build sorted PageData list ────────────────────────────────
        all_page_nos = sorted(
            set(list(page_dims.keys()) + list(page_items.keys()))
        )
        pages: List[PageData] = []
        for page_no in all_page_nos:
            items = page_items.get(page_no, [])
            w, h = page_dims.get(page_no, (595.0, 842.0))
            pages.append(
                PageData(
                    page_number=page_no,
                    width=w,
                    height=h,
                    text="\n".join(it.text for it in items if it.is_content_body),
                    items=items,
                )
            )

        return pages, all_items

    def _generate_chunks(
        self,
        pages: List[PageData],
        max_chunk_size: int = 500,
        overlap: int = 50,
    ) -> List[ChunkData]:
        """Semantic chunking with section-aware splitting.

        Key behaviours:
        - Page boundaries are ignored; text flows continuously across pages.
        - A new chunk is always started at each section heading.
        - Splits prefer Japanese/English sentence endings (。 . ! ?), never colons.
        - Tables and Formulas are kept intact (not split mid-element).
        - The last `overlap` characters of a completed chunk are carried into the
          next chunk as context, starting from a clean sentence boundary.
        """
        chunks: List[ChunkData] = []
        chunk_index = 0
        current_section: Optional[str] = None
        buffer: List[str] = []
        current_page: int = 1
        overlap_prefix: str = ""

        def buffer_len() -> int:
            return sum(len(p) for p in buffer)

        def flush(page_no: int) -> None:
            nonlocal chunk_index, buffer, overlap_prefix
            content = "\n\n".join(p for p in buffer if p.strip()).strip()
            if content:
                chunks.append(
                    ChunkData(
                        chunk_index=chunk_index,
                        section_title=current_section,
                        content=content,
                        page_number=page_no,
                        location_json={"page": page_no, "section": current_section},
                    )
                )
                chunk_index += 1
                if overlap > 0:
                    tail = content[-overlap:]
                    # Start overlap at a clean sentence boundary when possible
                    m = re.search(r'(?<=[。.!?！？])\s*\S', tail)
                    overlap_prefix = tail[m.start():] if m else tail
                else:
                    overlap_prefix = ""
            buffer = []

        # Flatten all content items in reading order, ignoring page boundaries
        all_items: List[Tuple[TextItem, int]] = [
            (item, page.page_number)
            for page in pages
            for item in page.items
        ]

        for item, page_no in all_items:
            if not item.is_content_body:
                continue

            current_page = page_no

            # ── Section heading: always start a new chunk ─────────────
            if item.is_heading:
                flush(page_no)
                level = 1 if item.element_type == "Title" else 2
                current_section = item.text
                buffer = [f"{'#' * level} {item.text}"]
                overlap_prefix = ""  # do not carry context across section boundary
                continue

            # ── Atomic elements: keep intact, flush first if needed ───
            if item.element_type in _ATOMIC_TYPES:
                if buffer_len() + len(item.text) > max_chunk_size and buffer_len() > 0:
                    flush(page_no)
                    if overlap_prefix:
                        buffer = [overlap_prefix]
                        overlap_prefix = ""
                buffer.append(item.text)
                continue

            # ── Regular text: split at sentence boundaries if needed ──
            text = item.text
            while text:
                available = max_chunk_size - buffer_len()
                if len(text) <= available:
                    buffer.append(text)
                    text = ""
                    break

                # Find the last sentence-ending position within available space.
                # Colons are intentionally excluded from split candidates.
                split_pos = -1
                for m in re.finditer(r'[。.!?！？]', text[:available]):
                    split_pos = m.end()

                if split_pos > 0:
                    buffer.append(text[:split_pos].strip())
                    text = text[split_pos:].lstrip()
                    flush(page_no)
                    if overlap_prefix:
                        buffer = [overlap_prefix]
                        overlap_prefix = ""
                elif buffer_len() > 0:
                    # No sentence boundary fits; flush what we have and retry
                    flush(page_no)
                    if overlap_prefix:
                        buffer = [overlap_prefix]
                        overlap_prefix = ""
                else:
                    # A single sentence exceeds max_chunk_size; accept as-is
                    buffer.append(text)
                    text = ""

        flush(current_page)
        return chunks
