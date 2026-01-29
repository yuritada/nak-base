"""
DOCX Parser Service
Phase 1.5: Microsoft Word document parsing

Uses python-docx for:
- Paragraph text extraction
- Heading detection
- Basic structure analysis
"""
import os
from typing import List, Optional
from docx import Document
from docx.shared import Pt

from ..schemas import (
    ParseResponse, DocumentMeta, PageData, TextItem, ChunkData
)


class DOCXParser:
    """DOCX parser with structure extraction"""

    # Chunk size for RAG (characters)
    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 100

    def __init__(self, debug: bool = False):
        self.debug = debug

    def parse(self, file_path: str) -> ParseResponse:
        """
        Parse a DOCX file and extract structured data

        Args:
            file_path: Path to the DOCX file

        Returns:
            ParseResponse with content, meta, pages, and chunks
        """
        if self.debug:
            print(f"[DOCXParser] Parsing: {file_path}")

        doc = Document(file_path)

        # Extract metadata
        meta = self._extract_metadata(doc, file_path)

        # Extract paragraphs
        paragraphs, text_items = self._extract_paragraphs(doc)

        # Generate markdown content
        content = self._generate_markdown(paragraphs)

        # Create single page (DOCX doesn't have strict page boundaries)
        pages = [
            PageData(
                page_number=1,
                width=612,  # Letter size default
                height=792,
                text=content,
                items=text_items
            )
        ]

        # Generate chunks for RAG
        chunks = self._generate_chunks(content)

        if self.debug:
            print(f"[DOCXParser] Extracted {len(paragraphs)} paragraphs, {len(chunks)} chunks")

        return ParseResponse(
            content=content,
            meta=meta,
            pages=pages,
            chunks=chunks
        )

    def _extract_metadata(self, doc: Document, file_path: str) -> DocumentMeta:
        """Extract document metadata"""
        core_props = doc.core_properties

        return DocumentMeta(
            title=core_props.title if core_props.title else os.path.basename(file_path),
            author=core_props.author,
            num_pages=1,  # DOCX doesn't have fixed pages
            file_type="docx",
            source_files=[os.path.basename(file_path)]
        )

    def _extract_paragraphs(self, doc: Document) -> tuple[List[dict], List[TextItem]]:
        """Extract paragraphs and convert to text items"""
        paragraphs = []
        text_items = []

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # Check if it's a heading
            is_heading = para.style.name.startswith('Heading')

            # Get font size if available
            font_size = None
            if para.runs:
                run = para.runs[0]
                if run.font.size:
                    font_size = run.font.size.pt

            paragraphs.append({
                "text": text,
                "is_heading": is_heading,
                "style": para.style.name,
                "font_size": font_size
            })

            text_items.append(TextItem(
                text=text,
                bbox=None,  # DOCX doesn't provide coordinates
                font_size=font_size,
                is_heading=is_heading
            ))

        return paragraphs, text_items

    def _generate_markdown(self, paragraphs: List[dict]) -> str:
        """Generate markdown from paragraphs"""
        lines = []

        for para in paragraphs:
            text = para["text"]
            style = para.get("style", "")

            if para["is_heading"]:
                # Determine heading level from style name
                if "Heading 1" in style:
                    lines.append(f"# {text}")
                elif "Heading 2" in style:
                    lines.append(f"## {text}")
                elif "Heading 3" in style:
                    lines.append(f"### {text}")
                else:
                    lines.append(f"## {text}")  # Default to H2
            else:
                lines.append(text)

            lines.append("")  # Empty line between paragraphs

        return "\n".join(lines)

    def _generate_chunks(self, content: str) -> List[ChunkData]:
        """Generate chunks for RAG/embedding"""
        chunks = []
        text = content

        # Simple chunking by character count with overlap
        start = 0
        chunk_index = 0

        while start < len(text):
            end = min(start + self.CHUNK_SIZE, len(text))

            # Try to break at paragraph boundary
            if end < len(text):
                # Look for paragraph break near end
                para_break = text.rfind("\n\n", start, end)
                if para_break > start + self.CHUNK_SIZE // 2:
                    end = para_break + 2

            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append(ChunkData(
                    chunk_index=chunk_index,
                    section_title=None,
                    content=chunk_text,
                    page_number=1,
                    line_number=None,
                    location_json={"char_start": start, "char_end": end}
                ))
                chunk_index += 1

            # Move start with overlap
            start = end - self.CHUNK_OVERLAP if end < len(text) else len(text)

        return chunks
