"""
nak-base マルチエージェント・パイプライン

各エージェントは BaseAgent を継承し、`run(context)` で JSON dict を返す。
Orchestrator (worker.process_task) からまとめて呼び出される。
"""
from .base import BaseAgent, AgentResult
from .linter import LinterAgent
from .logic import LogicAgent
from .rag import RagAgent
from .diff_aware import DiffAwareAgent

__all__ = [
    "BaseAgent",
    "AgentResult",
    "LinterAgent",
    "LogicAgent",
    "RagAgent",
    "DiffAwareAgent",
]
