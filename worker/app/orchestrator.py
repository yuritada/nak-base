"""
Orchestrator: 各エージェントを並列/順次実行し、結果を最終 Feedback へ統合する。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from .config import get_settings
from .agents import LinterAgent, LogicAgent, RagAgent, DiffAwareAgent, AgentResult

settings = get_settings()

# エージェント名 → ユーザー向けの表示ラベル（SSE通知に使う）
AGENT_LABELS = {
    "linter": "Linter (フォーマット・誤字脱字)",
    "logic": "Logic (論理整合性)",
    "rag": "RAG (過去論文ナレッジ)",
    "diff": "Diff-Aware (改稿レビュー)",
}


def run_agents(
    context: dict,
    *,
    notify: Optional[Callable[[str, str], None]] = None,
) -> dict[str, AgentResult]:
    """4エージェントを実行し、name → AgentResult のdictを返す。

    Args:
        context: 全エージェントが共有するコンテキスト（paper_text, conference_context, ...）
        notify(agent_name, label): フェーズ通知用コールバック（並列時は各完了後に呼ばれる）
    """
    agents = [LinterAgent(), LogicAgent(), RagAgent(), DiffAwareAgent()]
    results: dict[str, AgentResult] = {}

    if settings.agents_parallel:
        with ThreadPoolExecutor(max_workers=len(agents)) as ex:
            future_map = {ex.submit(agent.run, context): agent for agent in agents}
            # 開始通知（一括）
            if notify:
                notify("agents_start", "マルチエージェント解析開始 (Linter / Logic / RAG / Diff)")
            for future in as_completed(future_map):
                agent = future_map[future]
                result = future.result()
                results[agent.name] = result
                if notify:
                    label = AGENT_LABELS.get(agent.name, agent.name)
                    status_icon = "✅" if result.ok else "⚠"
                    notify(agent.name, f"{status_icon} {label} 完了 ({result.elapsed_sec:.1f}s)")
    else:
        for agent in agents:
            if notify:
                notify(agent.name, f"{AGENT_LABELS.get(agent.name, agent.name)} 実行中")
            result = agent.run(context)
            results[agent.name] = result
            if notify:
                status_icon = "✅" if result.ok else "⚠"
                notify(agent.name, f"{status_icon} {AGENT_LABELS.get(agent.name, agent.name)} 完了 ({result.elapsed_sec:.1f}s)")

    return results


def merge_results(results: dict[str, AgentResult]) -> dict:
    """各エージェントのJSON出力を、Feedback.comments_json + overall_summary 互換の形にマージする。"""
    linter = results.get("linter").output if "linter" in results else {}
    logic = results.get("logic").output if "logic" in results else {}
    rag = results.get("rag").output if "rag" in results else {}
    diff = results.get("diff").output if "diff" in results else {}

    # ----- typos: Linter から平坦化 -----
    typos: list[str] = []
    for t in (linter.get("typos") or []):
        if isinstance(t, dict):
            text = t.get("text", "")
            sug = t.get("suggestion", "")
            loc = t.get("location", "")
            line = " → ".join([x for x in [text, sug] if x])
            if loc:
                line = f"[{loc}] {line}"
            typos.append(line)
        elif isinstance(t, str):
            typos.append(t)

    # ----- suggestions: 全エージェントから収集 -----
    suggestions: list[str] = []
    for fv in (linter.get("format_violations") or []):
        if isinstance(fv, dict):
            suggestions.append(
                f"[Linter/{fv.get('rule', 'format')}] {fv.get('detail', '')} → {fv.get('suggestion', '')}".strip()
            )
    for gap in (logic.get("logical_gaps") or []):
        if isinstance(gap, dict):
            suggestions.append(
                f"[Logic/{gap.get('location', '?')}] {gap.get('issue', '')} → {gap.get('suggestion', '')}".strip()
            )
    for issue in (logic.get("structural_issues") or []):
        suggestions.append(f"[Logic/構成] {issue}")
    for hint in (rag.get("improvement_hints") or []):
        suggestions.append(f"[RAG] {hint}")
    for nc in (diff.get("new_concerns") or []):
        suggestions.append(f"[Diff/新規懸念] {nc}")
    for ri in (diff.get("remaining_issues") or []):
        suggestions.append(f"[Diff/未対応] {ri}")

    # ----- 前回からの改善点: Diff-Awareから -----
    improvements_from_previous: list[str] = []
    for imp in (diff.get("improvements") or []):
        if isinstance(imp, dict) and imp.get("addressed"):
            improvements_from_previous.append(
                f"{imp.get('previous_issue', '')} → {imp.get('evidence', '対応済み')}"
            )

    # ----- 総評の合成 -----
    summary_parts = []
    for name, label in [("linter", "Linter"), ("logic", "Logic"), ("rag", "RAG"), ("diff", "Diff")]:
        agent_summary = (results.get(name).output if name in results else {}).get("summary")
        if agent_summary:
            summary_parts.append(f"【{label}】{agent_summary}")
    overall_summary = "\n\n".join(summary_parts) if summary_parts else "解析結果なし"

    return {
        "summary": overall_summary,
        "typos": typos,
        "suggestions": suggestions,
        "improvements_from_previous": improvements_from_previous,
        "agents": {
            "linter": linter,
            "logic": logic,
            "rag": rag,
            "diff": diff,
        },
        "agent_meta": {
            name: {
                "ok": r.ok,
                "error": r.error,
                "elapsed_sec": round(r.elapsed_sec, 2),
            }
            for name, r in results.items()
        },
    }
