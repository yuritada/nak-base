"""
PDF Parser Service
Phase 1-2: Advanced PDF parsing with coordinate extraction

Uses PyMuPDF (fitz) for:
- Text extraction with bounding boxes
- Font size detection for heading identification
- Page layout analysis
"""
import os
import re
from typing import List, Optional, Tuple
import fitz  # PyMuPDF

from ..schemas import (
    ParseResponse, DocumentMeta, PageData, TextItem, ChunkData
)


class PDFParser:
    """Advanced PDF parser with coordinate and structure extraction"""

    # Common section titles to detect
    SECTION_PATTERNS = [
        r"^abstract\s*$",
        r"^introduction\s*$",
        r"^background\s*$",
        r"^related\s+work\s*$",
        r"^methodology\s*$",
        r"^method[s]?\s*$",
        r"^experiment[s]?\s*$",
        r"^result[s]?\s*$",
        r"^discussion\s*$",
        r"^conclusion[s]?\s*$",
        r"^reference[s]?\s*$",
        r"^acknowledg[e]?ment[s]?\s*$",
        r"^appendix\s*$",
        r"^\d+\.?\s+\w+",  # Numbered sections like "1. Introduction"
    ]

    # Font size thresholds for heading detection
    HEADING_FONT_SIZE_RATIO = 1.2  # 20% larger than average = heading

    def __init__(self, debug: bool = False):
        self.debug = debug

    def parse(self, file_path: str) -> ParseResponse:
        """
        Parse a PDF file and extract structured data

        Args:
            file_path: Path to the PDF file

        Returns:
            ParseResponse with content, meta, pages, and chunks
        """
        if self.debug:
            print(f"[PDFParser] Parsing: {file_path}")

        doc = fitz.open(file_path)

        try:
            # Extract metadata
            meta = self._extract_metadata(doc, file_path)

            # Extract pages with text items
            pages, all_items = self._extract_pages(doc)

            # Generate markdown content
            content = self._generate_markdown(pages, all_items)

            # Generate chunks for RAG
            chunks = self._generate_chunks(pages, all_items)

            if self.debug:
                print(f"[PDFParser] Extracted {len(pages)} pages, {len(chunks)} chunks")

            return ParseResponse(
                content=content,
                meta=meta,
                pages=pages,
                chunks=chunks
            )

        finally:
            doc.close()

    def _extract_metadata(self, doc: fitz.Document, file_path: str) -> DocumentMeta:
        """Extract document metadata"""
        metadata = doc.metadata or {}

        title = metadata.get("title", "")
        if not title:
            # Try to extract title from first page (often the largest text)
            title = self._detect_title_from_first_page(doc)

        return DocumentMeta(
            title=title or os.path.basename(file_path),
            author=metadata.get("author"),
            num_pages=len(doc),
            file_type="pdf",
            source_files=[os.path.basename(file_path)]
        )

    def _detect_title_from_first_page(self, doc: fitz.Document) -> Optional[str]:
        """Try to detect title from the first page (largest font text)"""
        if len(doc) == 0:
            return None

        page = doc[0]
        blocks = page.get_text("dict")["blocks"]

        max_font_size = 0
        title_text = ""

        for block in blocks:
            if "lines" not in block:
                continue

            for line in block["lines"]:
                for span in line["spans"]:
                    font_size = span.get("size", 0)
                    text = span.get("text", "").strip()

                    # Title is usually in top 1/3 of page and has large font
                    if font_size > max_font_size and len(text) > 3:
                        # Check if it's in upper portion of page
                        if line["bbox"][1] < page.rect.height * 0.4:
                            max_font_size = font_size
                            title_text = text

        return title_text if title_text else None

    def _extract_pages(self, doc: fitz.Document) -> Tuple[List[PageData], List[TextItem]]:
        """Extract text and coordinates from all pages"""
        pages = []
        all_items = []

        # First pass: calculate average font size
        font_sizes = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        size = span.get("size", 0)
                        if size > 0:
                            font_sizes.append(size)

        avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 12
        heading_threshold = avg_font_size * self.HEADING_FONT_SIZE_RATIO

        # Second pass: extract with heading detection
        for page_num, page in enumerate(doc):
            page_text_parts = []
            page_items = []

            blocks = page.get_text("dict")["blocks"]

            for block in blocks:
                if "lines" not in block:
                    continue

                for line in block["lines"]:
                    line_text = ""
                    line_bbox = line["bbox"]  # [x0, y0, x1, y1]

                    for span in line["spans"]:
                        text = span.get("text", "")
                        font_size = span.get("size", 0)
                        span_bbox = span.get("bbox", line_bbox)

                        if text.strip():
                            is_heading = (
                                font_size >= heading_threshold or
                                self._is_section_title(text)
                            )

                            item = TextItem(
                                text=text,
                                bbox=list(span_bbox),
                                font_size=font_size,
                                is_heading=is_heading
                            )
                            page_items.append(item)
                            all_items.append(item)
                            line_text += text

                    if line_text.strip():
                        page_text_parts.append(line_text)

            page_data = PageData(
                page_number=page_num + 1,
                width=page.rect.width,
                height=page.rect.height,
                text="\n".join(page_text_parts),
                items=page_items
            )
            pages.append(page_data)

        return pages, all_items

    def _is_section_title(self, text: str) -> bool:
        """Check if text matches common section title patterns"""
        text_lower = text.lower().strip()
        for pattern in self.SECTION_PATTERNS:
            if re.match(pattern, text_lower, re.IGNORECASE):
                return True
        return False

    def _generate_markdown(self, pages: List[PageData], all_items: List[TextItem]) -> str:
        """Generate markdown-formatted content from extracted text"""
        lines = []
        current_section = None

        for page in pages:
            for item in page.items:
                text = item.text.strip()
                if not text:
                    continue

                if item.is_heading:
                    # Detect heading level based on font size or pattern
                    if self._is_main_section(text):
                        lines.append(f"\n## {text}\n")
                        current_section = text
                    else:
                        lines.append(f"\n### {text}\n")
                else:
                    lines.append(text)

        # Join with appropriate spacing
        content = " ".join(lines)

        # Clean up excessive whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)
        content = re.sub(r' {2,}', ' ', content)

        return content.strip()

    def _is_main_section(self, text: str) -> bool:
        """Check if this is a main section (level 2 heading)"""
        text_lower = text.lower().strip()
        main_sections = [
            "abstract", "introduction", "background", "related work",
            "methodology", "methods", "experiments", "results",
            "discussion", "conclusion", "conclusions", "references"
        ]
        return any(section in text_lower for section in main_sections)

    def _generate_chunks(
        self,
        pages: List[PageData],
        all_items: List[TextItem],
        max_chunk_size: int = 500,
        overlap: int = 50
    ) -> List[ChunkData]:
        """
        Generate text chunks for RAG/embedding

        Args:
            pages: List of page data
            all_items: All text items
            max_chunk_size: Maximum characters per chunk
            overlap: Character overlap between chunks

        Returns:
            List of ChunkData for embedding
        """
        chunks = []
        chunk_index = 0
        current_section = None

        for page in pages:
            page_text = page.text
            page_num = page.page_number

            # Split page text into sentences/paragraphs
            paragraphs = re.split(r'\n\s*\n', page_text)

            current_chunk_text = ""
            chunk_start_line = 0

            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue

                # Check if this is a section header
                if self._is_section_title(para):
                    # Save current chunk if not empty
                    if current_chunk_text.strip():
                        chunks.append(ChunkData(
                            chunk_index=chunk_index,
                            section_title=current_section,
                            content=current_chunk_text.strip(),
                            page_number=page_num,
                            line_number=chunk_start_line,
                            location_json={
                                "page": page_num,
                                "section": current_section
                            }
                        ))
                        chunk_index += 1
                        current_chunk_text = ""

                    current_section = para
                    continue

                # Add to current chunk
                if len(current_chunk_text) + len(para) > max_chunk_size:
                    # Save current chunk
                    if current_chunk_text.strip():
                        chunks.append(ChunkData(
                            chunk_index=chunk_index,
                            section_title=current_section,
                            content=current_chunk_text.strip(),
                            page_number=page_num,
                            line_number=chunk_start_line,
                            location_json={
                                "page": page_num,
                                "section": current_section
                            }
                        ))
                        chunk_index += 1

                    # Start new chunk with overlap
                    if overlap > 0 and len(current_chunk_text) > overlap:
                        current_chunk_text = current_chunk_text[-overlap:] + " " + para
                    else:
                        current_chunk_text = para
                else:
                    current_chunk_text += "\n\n" + para if current_chunk_text else para

            # Save remaining chunk for this page
            if current_chunk_text.strip():
                chunks.append(ChunkData(
                    chunk_index=chunk_index,
                    section_title=current_section,
                    content=current_chunk_text.strip(),
                    page_number=page_num,
                    line_number=chunk_start_line,
                    location_json={
                        "page": page_num,
                        "section": current_section
                    }
                ))
                chunk_index += 1
                current_chunk_text = ""

        return chunks
