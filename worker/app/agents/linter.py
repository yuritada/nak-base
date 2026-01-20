"""
Linter Agent: 形式チェック、誤字脱字、学会フォーマット違反の検出
"""
import google.generativeai as genai
from typing import Dict, List, Any


LINTER_PROMPT = """あなたは学術論文の形式チェックを行う専門家です。
以下の論文テキストを分析し、形式的な問題点を指摘してください。

チェック項目:
1. 誤字脱字
2. 文法エラー
3. フォーマットの一貫性（見出しの形式、引用スタイルなど）
4. 学会フォーマット要件との適合性

学会フォーマット要件:
{format_rules}

論文テキスト:
{paper_text}

以下のJSON形式で回答してください:
{{
    "typos": [
        {{"location": "場所の説明", "original": "原文", "suggested": "修正案", "severity": "low/medium/high"}}
    ],
    "grammar_issues": [
        {{"location": "場所の説明", "issue": "問題の説明", "suggestion": "修正案", "severity": "low/medium/high"}}
    ],
    "format_issues": [
        {{"location": "場所の説明", "issue": "問題の説明", "suggestion": "修正案", "severity": "low/medium/high"}}
    ],
    "conference_compliance": {{
        "compliant": true/false,
        "issues": ["問題1", "問題2"]
    }},
    "overall_score": 0-100
}}
"""


def run_linter_agent(
    model: genai.GenerativeModel,
    paper_text: str,
    format_rules: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Run the linter agent to check formatting and typos.
    """
    format_rules_str = "\n".join([f"- {k}: {v}" for k, v in format_rules.items()])

    prompt = LINTER_PROMPT.format(
        format_rules=format_rules_str,
        paper_text=paper_text[:15000]  # Limit text length
    )

    try:
        response = model.generate_content(prompt)
        response_text = response.text

        # Try to parse JSON from response
        import json
        import re

        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            result = json.loads(json_match.group())
            return result
        else:
            return {
                "typos": [],
                "grammar_issues": [],
                "format_issues": [],
                "conference_compliance": {"compliant": True, "issues": []},
                "overall_score": 70,
                "raw_response": response_text
            }

    except Exception as e:
        return {
            "error": str(e),
            "typos": [],
            "grammar_issues": [],
            "format_issues": [],
            "conference_compliance": {"compliant": True, "issues": []},
            "overall_score": 0
        }
