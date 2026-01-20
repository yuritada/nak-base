"""
Logic Agent: AbstractとConclusionの整合性、章立ての論理チェック
"""
import google.generativeai as genai
from typing import Dict, List, Any


LOGIC_PROMPT = """あなたは学術論文の論理構造を分析する専門家です。
以下の論文を分析し、論理的な問題点を指摘してください。

チェック項目:
1. Abstractと結論の整合性
2. 章立ての論理的な流れ
3. 主張と根拠の対応
4. 議論の一貫性

論文の概要:
タイトル: {title}

Abstract:
{abstract}

本文の構成:
{sections}

結論:
{conclusion}

全文（抜粋）:
{full_text}

以下のJSON形式で回答してください:
{{
    "abstract_conclusion_consistency": {{
        "score": 0-100,
        "issues": ["問題点1", "問題点2"],
        "suggestions": ["改善案1", "改善案2"]
    }},
    "structure_analysis": {{
        "score": 0-100,
        "logical_flow": "良好/改善の余地あり/問題あり",
        "issues": ["問題点1", "問題点2"],
        "suggestions": ["改善案1", "改善案2"]
    }},
    "argument_analysis": {{
        "score": 0-100,
        "issues": ["問題点1", "問題点2"],
        "suggestions": ["改善案1", "改善案2"]
    }},
    "overall_logic_score": 0-100,
    "summary": "全体的な論理構造についての短いコメント"
}}
"""


def run_logic_agent(
    model: genai.GenerativeModel,
    parsed_doc: Dict[str, Any],
    abstract: str,
    conclusion: str
) -> Dict[str, Any]:
    """
    Run the logic agent to analyze logical structure.
    """
    title = parsed_doc.get("metadata", {}).get("title", "不明")
    sections = parsed_doc.get("sections", [])
    sections_str = "\n".join([f"- {s.get('title', 'セクション')}" for s in sections[:20]])
    full_text = parsed_doc.get("full_text", "")[:10000]

    prompt = LOGIC_PROMPT.format(
        title=title,
        abstract=abstract[:2000] if abstract else "（Abstractが見つかりませんでした）",
        sections=sections_str if sections_str else "（セクション情報が見つかりませんでした）",
        conclusion=conclusion[:2000] if conclusion else "（結論が見つかりませんでした）",
        full_text=full_text
    )

    try:
        response = model.generate_content(prompt)
        response_text = response.text

        # Try to parse JSON from response
        import json
        import re

        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            result = json.loads(json_match.group())
            return result
        else:
            return {
                "abstract_conclusion_consistency": {"score": 70, "issues": [], "suggestions": []},
                "structure_analysis": {"score": 70, "logical_flow": "不明", "issues": [], "suggestions": []},
                "argument_analysis": {"score": 70, "issues": [], "suggestions": []},
                "overall_logic_score": 70,
                "summary": response_text[:500],
                "raw_response": response_text
            }

    except Exception as e:
        return {
            "error": str(e),
            "abstract_conclusion_consistency": {"score": 0, "issues": [], "suggestions": []},
            "structure_analysis": {"score": 0, "logical_flow": "エラー", "issues": [], "suggestions": []},
            "argument_analysis": {"score": 0, "issues": [], "suggestions": []},
            "overall_logic_score": 0,
            "summary": "分析中にエラーが発生しました"
        }
