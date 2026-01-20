"""
Diff Checker Agent: 前回のFBを踏まえた改善確認
"""
import google.generativeai as genai
from typing import Dict, List, Any, Optional


DIFF_CHECK_PROMPT = """あなたは論文の改善状況を確認する専門家です。
前回のフィードバックと今回の論文を比較し、改善状況を分析してください。

前回のフィードバック:
{previous_feedback}

今回の論文（抜粋）:
{current_paper}

以下のJSON形式で回答してください:
{{
    "resolved_issues": [
        {{
            "original_issue": "元の指摘内容",
            "status": "resolved/partially_resolved/unresolved",
            "comment": "改善状況についてのコメント"
        }}
    ],
    "new_issues": [
        "新たに発見された問題点1",
        "新たに発見された問題点2"
    ],
    "improvement_score": 0-100,
    "summary": "全体的な改善状況についてのコメント"
}}
"""


def run_diff_checker(
    model: genai.GenerativeModel,
    current_paper_text: str,
    previous_feedback: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Check if previous feedback issues have been resolved.
    """
    if not previous_feedback:
        return {
            "resolved_issues": [],
            "new_issues": [],
            "improvement_score": None,
            "summary": "これが最初のバージョンのため、前回との比較はありません。"
        }

    # Format previous feedback
    feedback_str = ""

    if "linter_result" in previous_feedback:
        linter = previous_feedback["linter_result"]
        if linter.get("typos"):
            feedback_str += "\n誤字脱字の指摘:\n"
            for t in linter["typos"][:5]:
                feedback_str += f"- {t.get('original', '')} → {t.get('suggested', '')}\n"

        if linter.get("format_issues"):
            feedback_str += "\nフォーマットの指摘:\n"
            for f in linter["format_issues"][:5]:
                feedback_str += f"- {f.get('issue', '')}\n"

    if "logic_result" in previous_feedback:
        logic = previous_feedback["logic_result"]
        if logic.get("structure_analysis", {}).get("issues"):
            feedback_str += "\n論理構造の指摘:\n"
            for i in logic["structure_analysis"]["issues"][:5]:
                feedback_str += f"- {i}\n"

    if not feedback_str:
        feedback_str = "前回のフィードバック: 特に重大な指摘はありませんでした。"

    prompt = DIFF_CHECK_PROMPT.format(
        previous_feedback=feedback_str,
        current_paper=current_paper_text[:10000]
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
                "resolved_issues": [],
                "new_issues": [],
                "improvement_score": 70,
                "summary": response_text[:500],
                "raw_response": response_text
            }

    except Exception as e:
        return {
            "error": str(e),
            "resolved_issues": [],
            "new_issues": [],
            "improvement_score": 0,
            "summary": "分析中にエラーが発生しました"
        }
