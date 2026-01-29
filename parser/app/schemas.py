"""
Parser Service - Pydantic Schemas
Phase 1-2: Advanced parsing with structured output
"""
from pydantic import BaseModel
from typing import List, Optional, Any
from enum import Enum


class FileType(str, Enum):
    PDF = "pdf"
    ZIP = "zip"
    TEX = "tex"


# ================== Request Schemas ==================

class ParseRequest(BaseModel):
    """Parse request with file path and optional type hint"""
    file_path: str
    file_type: Optional[FileType] = None  # Auto-detect if not provided


# ================== Response Schemas ==================

class TextItem(BaseModel):
    """Individual text item with optional bounding box coordinates"""
    text: str
    bbox: Optional[List[float]] = None  # [x0, y0, x1, y1] in PDF points
    font_size: Optional[float] = None
    is_heading: bool = False


class PageData(BaseModel):
    """Data for a single page"""
    page_number: int
    width: float
    height: float
    text: str  # Plain text for the page
    items: List[TextItem] = []  # Individual text items with coordinates


class ChunkData(BaseModel):
    """Text chunk for RAG/embedding"""
    chunk_index: int
    section_title: Optional[str] = None
    content: str
    page_number: Optional[int] = None
    line_number: Optional[int] = None
    location_json: Optional[dict] = None  # For DB storage


class DocumentMeta(BaseModel):
    """Document metadata"""
    title: Optional[str] = None
    author: Optional[str] = None
    num_pages: int
    file_type: str
    source_files: List[str] = []  # For ZIP/TeX: list of processed files


class ParseResponse(BaseModel):
    """
    Full parse response with structured data

    - content: Markdown-formatted full text for LLM inference
    - meta: Document metadata
    - pages: Per-page data with text items and coordinates (for UI highlighting)
    - chunks: Pre-split chunks for RAG/embedding
    """
    content: str  # Markdown formatted full text
    meta: DocumentMeta
    pages: List[PageData] = []
    chunks: List[ChunkData] = []


# ================== Legacy Compatibility ==================

class LegacyParseResponse(BaseModel):
    """MVP-compatible response format"""
    text: str
    page_count: int
