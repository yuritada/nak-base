"""
Parser Service - Phase 1
構造化データ出力: markdown_text, coordinates, chunks
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import fitz  # pymupdf
import os
import re

app = FastAPI(
    title="nak-base Parser Service",
    description="PDF構造化テキスト抽出サービス（Phase 1）",
    version="2.0.0"
)


class ParseRequest(BaseModel):
    file_path: str


class Coordinate(BaseModel):
    page: int
    bbox: List[float]  # [x0, y0, x1, y1]
    text: str
    type: str  # header/paragraph


class ParseResponse(BaseModel):
    markdown_text: str
    coordinates: List[Coordinate]
    chunks: List[str]
    page_count: int


class LegacyParseResponse(BaseModel):
    """MVP互換用レスポンス"""
    text: str
    page_count: int


def classify_block_type(block_text: str, font_size: float, avg_font_size: float) -> str:
    """Classify text block as header or paragraph based on font size and patterns"""
    # Larger font = likely header
    if font_size > avg_font_size * 1.2:
        return "header"
    # Numbered sections are headers
    if re.match(r'^[\d]+[.\s]', block_text.strip()):
        return "header"
    # Roman numerals
    if re.match(r'^[IVX]+[.\s]', block_text.strip()):
        return "header"
    return "paragraph"


def chunk_text(text: str, max_chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Split text into chunks with overlap for RAG.
    Uses sentence boundaries when possible.
    """
    # Split on sentence boundaries (Japanese and English)
    sentences = re.split(r'(?<=[。.!?])\s*', text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if not sentence.strip():
            continue

        if len(current_chunk) + len(sentence) <= max_chunk_size:
            current_chunk += sentence + " "
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            # Start new chunk with overlap from previous
            if len(current_chunk) > overlap:
                overlap_text = current_chunk[-overlap:]
            else:
                overlap_text = ""
            current_chunk = overlap_text + sentence + " "

    # Add final chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    # Fallback: if no chunks created, split by character count
    if not chunks and text.strip():
        for i in range(0, len(text), max_chunk_size - overlap):
            chunk = text[i:i + max_chunk_size]
            if chunk.strip():
                chunks.append(chunk.strip())

    return chunks if chunks else [text[:max_chunk_size]] if text else []


@app.get("/")
def root():
    return {"status": "ok", "service": "parser", "version": "2.0.0"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/parse", response_model=ParseResponse)
def parse_pdf(request: ParseRequest):
    """
    PDFファイルから構造化データを抽出

    出力:
    - markdown_text: 全文のMarkdownテキスト
    - coordinates: 座標情報付きテキストブロック（ハイライト表示用）
    - chunks: RAG用チャンク分割テキスト
    - page_count: 総ページ数
    """
    file_path = request.file_path
    debug_mode = os.getenv("DEBUG_MODE") == "true"

    if debug_mode:
        print(f"[DEBUG] Parse request: {file_path}")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    if not file_path.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        doc = fitz.open(file_path)
        page_count = len(doc)

        markdown_parts = []
        coordinates = []
        all_font_sizes = []

        # First pass: collect font sizes for average calculation
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            if span["size"] > 0:
                                all_font_sizes.append(span["size"])

        avg_font_size = sum(all_font_sizes) / len(all_font_sizes) if all_font_sizes else 12.0

        # Second pass: extract structured data
        for page_num, page in enumerate(doc, 1):
            blocks = page.get_text("dict")["blocks"]
            page_markdown = []

            for block in blocks:
                if "lines" not in block:
                    continue

                block_text = ""
                block_font_size = 0.0

                for line in block["lines"]:
                    line_text = ""
                    for span in line["spans"]:
                        line_text += span["text"]
                        block_font_size = max(block_font_size, span["size"])
                    block_text += line_text + " "

                block_text = block_text.strip()
                if not block_text:
                    continue

                # Skip very short blocks (likely noise)
                if len(block_text) < 3:
                    continue

                block_type = classify_block_type(block_text, block_font_size, avg_font_size)

                # Add to markdown with appropriate formatting
                if block_type == "header":
                    page_markdown.append(f"\n## {block_text}\n")
                else:
                    page_markdown.append(block_text + "\n")

                # Store coordinate info for highlighting
                bbox = block["bbox"]  # [x0, y0, x1, y1]
                coordinates.append(Coordinate(
                    page=page_num,
                    bbox=[round(b, 2) for b in bbox],
                    text=block_text[:300],  # Truncate for storage
                    type=block_type
                ))

            if page_markdown:
                markdown_parts.append("".join(page_markdown))

        doc.close()

        # Combine all pages
        markdown_text = "\n\n".join(markdown_parts)

        # Generate chunks for RAG
        chunks = chunk_text(markdown_text)

        if debug_mode:
            print(f"[DEBUG] Parsed: {len(markdown_text)} chars, {len(coordinates)} blocks, {len(chunks)} chunks, {page_count} pages")

        return ParseResponse(
            markdown_text=markdown_text,
            coordinates=coordinates,
            chunks=chunks,
            page_count=page_count
        )

    except Exception as e:
        if debug_mode:
            print(f"[DEBUG] Parse error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {str(e)}")


@app.post("/parse/legacy", response_model=LegacyParseResponse)
def parse_pdf_legacy(request: ParseRequest):
    """
    MVP互換用エンドポイント
    プレーンテキストのみを返す
    """
    result = parse_pdf(request)
    return LegacyParseResponse(
        text=result.markdown_text,
        page_count=result.page_count
    )
