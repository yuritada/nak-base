"""
RAG Agent: Vector DBから類似研究を検索し、参考情報を提供
"""
import google.generativeai as genai
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, List, Any
import numpy as np


def get_embedding(model: genai.GenerativeModel, text: str) -> List[float]:
    """Get embedding vector for text using Gemini."""
    try:
        result = genai.embed_content(
            model="models/embedding-001",
            content=text[:8000],
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        print(f"Embedding error: {e}")
        return [0.0] * 768


def search_similar_documents(
    db: Session,
    query_vector: List[float],
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Search for similar documents in the seminars table using pgvector.
    """
    try:
        # Convert vector to string format for pgvector
        vector_str = f"[{','.join(map(str, query_vector))}]"

        query = text("""
            SELECT doc_id, content, meta_data, doc_type,
                   1 - (content_vector <=> :vector::vector) as similarity
            FROM seminars
            WHERE content_vector IS NOT NULL
            ORDER BY content_vector <=> :vector::vector
            LIMIT :limit
        """)

        result = db.execute(query, {"vector": vector_str, "limit": limit})

        documents = []
        for row in result:
            documents.append({
                "doc_id": row.doc_id,
                "content": row.content[:1000],  # Truncate for display
                "meta_data": row.meta_data,
                "doc_type": row.doc_type,
                "similarity": float(row.similarity) if row.similarity else 0
            })

        return documents

    except Exception as e:
        print(f"RAG search error: {e}")
        return []


RAG_PROMPT = """あなたは研究論文の分析専門家です。
以下の論文と、過去の類似研究を比較分析してください。

対象論文の概要:
{paper_summary}

類似研究（過去のゼミ資料より）:
{similar_docs}

以下の観点で分析し、JSON形式で回答してください:
{{
    "similar_research_analysis": [
        {{
            "doc_id": "参照文書ID",
            "relevance": "高/中/低",
            "comparison": "比較内容",
            "suggestions": "この研究を参考にできる点"
        }}
    ],
    "novelty_assessment": {{
        "score": 0-100,
        "explanation": "新規性の説明",
        "suggestions": ["差別化のための提案1", "提案2"]
    }},
    "reference_suggestions": [
        "参考にすべき点1",
        "参考にすべき点2"
    ]
}}
"""


def run_rag_agent(
    model: genai.GenerativeModel,
    db: Session,
    paper_text: str,
    paper_title: str
) -> Dict[str, Any]:
    """
    Run the RAG agent to find and analyze similar research.
    """
    # Get embedding for the paper
    query_text = f"{paper_title}\n{paper_text[:3000]}"
    query_vector = get_embedding(model, query_text)

    # Search for similar documents
    similar_docs = search_similar_documents(db, query_vector, limit=5)

    if not similar_docs:
        return {
            "similar_research_analysis": [],
            "novelty_assessment": {
                "score": 80,
                "explanation": "類似研究が見つかりませんでした。新規性が高い可能性があります。",
                "suggestions": []
            },
            "reference_suggestions": []
        }

    # Format similar docs for prompt
    similar_docs_str = ""
    for i, doc in enumerate(similar_docs, 1):
        similar_docs_str += f"\n--- 文書{i} (類似度: {doc['similarity']:.2f}) ---\n"
        similar_docs_str += f"種類: {doc['doc_type']}\n"
        similar_docs_str += f"内容: {doc['content']}\n"

    prompt = RAG_PROMPT.format(
        paper_summary=paper_text[:5000],
        similar_docs=similar_docs_str
    )

    try:
        response = model.generate_content(prompt)
        response_text = response.text

        import json
        import re

        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            result = json.loads(json_match.group())
            return result
        else:
            return {
                "similar_research_analysis": [],
                "novelty_assessment": {"score": 70, "explanation": response_text[:500], "suggestions": []},
                "reference_suggestions": [],
                "raw_response": response_text
            }

    except Exception as e:
        return {
            "error": str(e),
            "similar_research_analysis": [],
            "novelty_assessment": {"score": 0, "explanation": "分析中にエラーが発生", "suggestions": []},
            "reference_suggestions": []
        }
