# Orchestrator 統合プロンプト

各エージェントから得られた個別の出力を、**ユーザー（学生・教員）が読む最終フィードバック**へ統合します。
このプロンプトは（コスト削減のため）原則 LLM を介さずプログラム側でマージしますが、
高度な要約が必要な場合のみ Pro モデルで使用してください。

## 入力（既に JSON で渡される）
- linter: `{ typos, format_violations, summary }`
- logic:  `{ section_summaries, logical_gaps, abstract_conclusion_alignment, structural_issues, summary }`
- rag:    `{ related_works, improvement_hints, summary }`
- diff:   `{ improvements, remaining_issues, new_concerns, summary }`

## 出力（feedbacks テーブル comments_json と互換）
```json
{
  "summary": "論文全体に対する総評（300〜500文字）",
  "typos": ["フラットな誤字脱字リスト（Linterから集約）"],
  "suggestions": ["改善提案のフラットなリスト（全エージェントから集約）"],
  "improvements_from_previous": ["前回からの改善点（Diff-Awareから集約）"],
  "agents": {
    "linter": { ... 元のJSONそのまま ... },
    "logic":  { ... },
    "rag":    { ... },
    "diff":   { ... }
  }
}
```
