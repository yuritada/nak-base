"""
Conference Rules CRUD API
Phase 1-3: 学会ルール管理

学会ごとのフォーマット規定やスタイルガイドを管理
Workerがプロンプト生成時にこれらのルールを参照
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..models import ConferenceRule
from ..schemas import (
    ConferenceRuleCreate,
    ConferenceRuleUpdate,
    ConferenceRuleResponse
)
from ..services.embedding_service import generate_conference_rule_embedding

router = APIRouter(prefix="/conferences", tags=["conferences"])


@router.get("/", response_model=List[ConferenceRuleResponse])
def list_conference_rules(db: Session = Depends(get_db)):
    """
    学会ルール一覧を取得
    フロントエンドのドロップダウン用
    """
    rules = db.query(ConferenceRule).order_by(ConferenceRule.name).all()
    return rules


@router.get("/{rule_id}", response_model=ConferenceRuleResponse)
def get_conference_rule(rule_id: str, db: Session = Depends(get_db)):
    """
    特定の学会ルールを取得
    """
    rule = db.query(ConferenceRule).filter(ConferenceRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail=f"Conference rule '{rule_id}' not found")
    return rule


@router.post("/", response_model=ConferenceRuleResponse, status_code=201)
def create_conference_rule(
    rule_data: ConferenceRuleCreate,
    db: Session = Depends(get_db)
):
    """
    新しい学会ルールを作成

    format_rules の例:
    {
        "max_pages": 8,
        "font_size": 10,
        "margin_cm": 2.5,
        "columns": 2,
        "references_format": "IEEE"
    }

    style_guide の例:
    \"\"\"
    ## 論文の構成
    1. 概要（Abstract）: 200語以内
    2. はじめに（Introduction）
    3. 関連研究（Related Work）
    ...
    \"\"\"
    """
    # Check if rule_id already exists
    existing = db.query(ConferenceRule).filter(ConferenceRule.rule_id == rule_data.rule_id).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Conference rule '{rule_data.rule_id}' already exists"
        )

    # Embedding生成（セマンティック検索用）
    embedding = generate_conference_rule_embedding(
        name=rule_data.name,
        style_guide=rule_data.style_guide or "",
        format_rules=rule_data.format_rules
    )

    rule = ConferenceRule(
        rule_id=rule_data.rule_id,
        name=rule_data.name,
        format_rules=rule_data.format_rules,
        style_guide=rule_data.style_guide,
        embedding=embedding
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    return rule


@router.put("/{rule_id}", response_model=ConferenceRuleResponse)
def update_conference_rule(
    rule_id: str,
    rule_data: ConferenceRuleUpdate,
    db: Session = Depends(get_db)
):
    """
    学会ルールを更新（部分更新対応）
    """
    rule = db.query(ConferenceRule).filter(ConferenceRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail=f"Conference rule '{rule_id}' not found")

    # 部分更新: 指定されたフィールドのみ更新
    embedding_needs_update = False

    if rule_data.name is not None:
        rule.name = rule_data.name
        embedding_needs_update = True
    if rule_data.format_rules is not None:
        rule.format_rules = rule_data.format_rules
        embedding_needs_update = True
    if rule_data.style_guide is not None:
        rule.style_guide = rule_data.style_guide
        embedding_needs_update = True

    # Embeddingを再生成
    if embedding_needs_update:
        rule.embedding = generate_conference_rule_embedding(
            name=rule.name,
            style_guide=rule.style_guide or "",
            format_rules=rule.format_rules
        )

    db.commit()
    db.refresh(rule)

    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_conference_rule(rule_id: str, db: Session = Depends(get_db)):
    """
    学会ルールを削除

    注意: 関連する論文やタスクのconference_idはNULLになる
    """
    rule = db.query(ConferenceRule).filter(ConferenceRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail=f"Conference rule '{rule_id}' not found")

    db.delete(rule)
    db.commit()

    return None
