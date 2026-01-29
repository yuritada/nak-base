"""
Parser Service - Phase 1-2
Advanced PDF/TeX/ZIP parsing with structured output

Features:
- PDF: Text extraction with bounding boxes for UI highlighting
- TeX: Multi-file resolution with \input/\include support
- ZIP: Archive extraction and multi-format processing
- Chunks: Pre-split text for RAG/embedding
"""
import os
from fastapi import FastAPI, HTTPException, Query
from typing import Optional

from .schemas import (
    ParseRequest, ParseResponse, LegacyParseResponse, FileType
)
from .services.pdf_parser import PDFParser
from .services.archive_parser import ArchiveParser


app = FastAPI(
    title="nak-base Parser Service",
    description="Advanced document parsing with coordinate extraction and structure analysis",
    version="2.0.0"
)

# Debug mode
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# Initialize parsers
pdf_parser = PDFParser(debug=DEBUG_MODE)
archive_parser = ArchiveParser(debug=DEBUG_MODE)


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "parser",
        "version": "2.0.0",
        "features": ["pdf", "tex", "zip", "bbox", "chunks"]
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/parse", response_model=ParseResponse)
def parse_document(
    request: ParseRequest,
    file_type: Optional[FileType] = Query(
        None,
        description="File type hint (auto-detected if not provided)"
    )
):
    """
    Parse a document and extract structured data

    Supports:
    - PDF: Full text with bounding boxes
    - TeX: LaTeX source with structure extraction
    - ZIP: Archive with PDF/TeX files

    Returns:
    - content: Markdown-formatted full text
    - meta: Document metadata
    - pages: Per-page data with coordinates (PDF only)
    - chunks: Pre-split chunks for RAG/embedding
    """
    file_path = request.file_path

    if DEBUG_MODE:
        print(f"[Parser] Request received: {file_path}")
        print(f"[Parser] File type hint: {file_type or request.file_type or 'auto'}")

    # Validate file exists
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {file_path}"
        )

    # Determine file type
    detected_type = _detect_file_type(file_path)
    actual_type = file_type or request.file_type or detected_type

    if DEBUG_MODE:
        print(f"[Parser] Detected type: {detected_type}, Using type: {actual_type}")

    try:
        if actual_type == FileType.PDF:
            return pdf_parser.parse(file_path)

        elif actual_type == FileType.ZIP:
            return archive_parser.parse_zip(file_path)

        elif actual_type == FileType.TEX:
            return archive_parser.parse_tex(file_path)

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {actual_type}"
            )

    except HTTPException:
        raise
    except Exception as e:
        if DEBUG_MODE:
            import traceback
            traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse document: {str(e)}"
        )


@app.post("/parse/legacy", response_model=LegacyParseResponse)
def parse_document_legacy(request: ParseRequest):
    """
    Legacy endpoint for MVP compatibility

    Returns simple text and page_count format
    """
    file_path = request.file_path

    if DEBUG_MODE:
        print(f"[Parser] Legacy request: {file_path}")

    # Validate
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {file_path}"
        )

    # Only PDF supported in legacy mode
    if not file_path.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Legacy endpoint only supports PDF files"
        )

    try:
        result = pdf_parser.parse(file_path)

        return LegacyParseResponse(
            text=result.content,
            page_count=result.meta.num_pages
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse PDF: {str(e)}"
        )


def _detect_file_type(file_path: str) -> FileType:
    """Detect file type from extension"""
    lower_path = file_path.lower()

    if lower_path.endswith('.pdf'):
        return FileType.PDF
    elif lower_path.endswith('.zip'):
        return FileType.ZIP
    elif lower_path.endswith('.tex'):
        return FileType.TEX
    else:
        # Default to PDF for unknown types
        return FileType.PDF
