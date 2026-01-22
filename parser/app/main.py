"""
Parser Service - MVP版
PDFからプレーンテキストを抽出するのみ
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pypdf import PdfReader
import os

app = FastAPI(
    title="nak-base Parser Service",
    description="PDFからテキストを抽出するシンプルなサービス",
    version="1.0.0"
)


class ParseRequest(BaseModel):
    file_path: str


class ParseResponse(BaseModel):
    text: str
    page_count: int


@app.get("/")
def root():
    return {"status": "ok", "service": "parser"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/parse", response_model=ParseResponse)
def parse_pdf(request: ParseRequest):
    """
    PDFファイルからテキストを抽出する

    - 入力: ファイルパス
    - 出力: プレーンテキストのみ
    - 禁止事項: 座標抽出、Markdown変換、章立ての構造化
    """
    file_path = request.file_path

    if os.getenv("DEBUG_MODE") == "true":
        print(f"【デバッグ】パースリクエスト受信: {file_path}")

    # ファイル存在確認
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    if not file_path.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        reader = PdfReader(file_path)

        # 全ページのテキストを連結
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

        full_text = "\n\n".join(text_parts)

        if os.getenv("DEBUG_MODE") == "true":
            print(f"【デバッグ】パース完了: {len(full_text)}文字抽出、全{len(reader.pages)}ページ")

        return ParseResponse(
            text=full_text,
            page_count=len(reader.pages)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {str(e)}")
