"""
PDF Parser Service
Phase 1.3: Docling-based PDF parsing with semantic layout analysis

Uses Docling (IBM) for:
- Semantic element recognition (Paragraph, SectionHeader, Table, etc.)
- Bounding box extraction with correct 2-column reading order
- Markdown export
"""
import os
from typing import Dict, List, Optional, Tuple

from ..schemas import ChunkData, DocumentMeta, PageData, ParseResponse, TextItem

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


def _label_str(label) -> str:
    """Normalise a Docling DocItemLabel to a plain lowercase string."""
    if hasattr(label, "value"):
        return label.value.lower()
    return str(label).lower().split(".")[-1]


class PDFParser:
    """Docling-based PDF parser with semantic structure and coordinate extraction."""

    def __init__(self, debug: bool = False):
        self.debug = debug
        self._converter = None  # lazy-loaded to avoid slow import at startup

    @property
    def converter(self):
        if self._converter is None:
            from docling.document_converter import DocumentConverter
            self._converter = DocumentConverter()
        return self._converter

    def parse(self, file_path: str) -> ParseResponse:
        if self.debug:
            print(f"[PDFParser] Parsing with Docling: {file_path}")

        result = self.converter.convert(file_path)
        doc = result.document

        meta = self._extract_metadata(doc, file_path)
        pages, all_items = self._extract_pages(doc)
        content = doc.export_to_markdown()
        chunks = self._generate_chunks(pages)

        if self.debug:
            print(f"[PDFParser] {len(pages)} pages, {len(all_items)} items, {len(chunks)} chunks")

        return ParseResponse(
            content=content,
            meta=meta,
            pages=pages,
            chunks=chunks,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_metadata(self, doc, file_path: str) -> DocumentMeta:
        title: Optional[str] = None

        # Docling stores the document name / detected title
        if getattr(doc, "name", None):
            title = doc.name

        if not title:
            # Fall back to the first Title-labelled item in the document
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
        """
        Iterate Docling document items and group them by page.

        Docling already outputs items in correct reading order (handles
        2-column layouts internally), so we preserve that order.
        """
        # Collect page dimensions
        page_dims: Dict[int, Tuple[float, float]] = {}
        if doc.pages:
            for page_no, page in doc.pages.items():
                size = getattr(page, "size", None)
                w = float(size.width) if size else 595.0
                h = float(size.height) if size else 842.0
                page_dims[int(page_no)] = (w, h)

        # Collect items per page
        page_items: Dict[int, List[TextItem]] = {}
        all_items: List[TextItem] = []

        for item, _ in doc.iterate_items():
            label = _label_str(item.label)
            element_type = _LABEL_TYPE_MAP.get(label, "Paragraph")

            # Extract text; tables fall back to markdown representation
            text: Optional[str] = getattr(item, "text", None)
            if not text and label == "table" and hasattr(item, "export_to_markdown"):
                text = item.export_to_markdown()
            if not text or not text.strip():
                continue

            is_heading = element_type in _HEADING_TYPES

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
                    text=text.strip(),
                    bbox=bbox,
                    font_size=None,
                    is_heading=is_heading,
                    element_type=element_type,
                )
                all_items.append(text_item)
                page_items.setdefault(page_no, []).append(text_item)

        # Build sorted PageData list
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
                    text="\n".join(it.text for it in items),
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
        chunks: List[ChunkData] = []
        chunk_index = 0
        current_section: Optional[str] = None
        current_text = ""
        current_page = 1

        def flush(page_no: int) -> None:
            nonlocal chunk_index, current_text
            if current_text.strip():
                chunks.append(
                    ChunkData(
                        chunk_index=chunk_index,
                        section_title=current_section,
                        content=current_text.strip(),
                        page_number=page_no,
                        location_json={"page": page_no, "section": current_section},
                    )
                )
                chunk_index += 1
                current_text = ""

        for page in pages:
            current_page = page.page_number
            for item in page.items:
                if item.is_heading:
                    flush(current_page)
                    current_section = item.text
                    continue

                if len(current_text) + len(item.text) > max_chunk_size:
                    flush(current_page)
                    if overlap > 0 and len(current_text) > overlap:
                        current_text = current_text[-overlap:] + " " + item.text
                    else:
                        current_text = item.text
                else:
                    current_text += ("\n\n" if current_text else "") + item.text

        flush(current_page)
        return chunks
