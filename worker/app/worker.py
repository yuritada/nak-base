"""
nak-base AI Inference Worker
Phase 1-3: 完全RAGパイプライン実装

機能:
- Embedding生成（Ollama API / Mockモード対応）
- チャンクのベクトル保存
- コサイン類似度によるセマンティック検索
- コンテキスト収集 → プロンプト組み立て → LLM呼び出し
"""
import redis
import time
import json
import requests
import difflib
from datetime import datetime
from typing import Optional, List

from sqlalchemy import text

from .config import get_settings
from .database import get_db_session
from .models import (
    InferenceTask, File, Feedback, Paper, Version,
    TaskStatus, PaperStatus, ConferenceRule, Embedding
)

settings = get_settings()

TASK_QUEUE = "tasks"
NOTIFICATION_CHANNEL = "task_notifications"


def publish_notification(task_id: int, status: str, phase: str | None = None, error_message: str | None = None):
    """
    タスク通知をRedis Pub/Subに発行
    フロントエンドのSSEに中継される
    """
    try:
        client = get_redis_client()
        notification = {
            "task_id": task_id,
            "status": status,
            "phase": phase,
            "error_message": error_message,
        }
        client.publish(NOTIFICATION_CHANNEL, json.dumps(notification))
        if settings.debug_mode:
            print(f"【デバッグ】通知発行: {notification}")
    except Exception as e:
        print(f"Failed to publish notification: {e}")


def get_redis_client():
    return redis.from_url(settings.redis_url)


# ================== Embedding Generation (Phase 1-3 RAG) ==================

def generate_embedding(text_input: str) -> List[float]:
    """
    テキストからベクトルを生成

    Args:
        text_input: ベクトル化するテキスト

    Returns:
        768次元のベクトル（List[float]）

    Note:
        - Mockモード: 全要素0.1のダミーベクトルを即座に返す
        - 本番モード: Ollama /api/embeddings を呼び出す
    """
    # Mockモード: ダミーベクトルを返す（開発用）
    if settings.mock_mode:
        if settings.debug_mode:
            print(f"【デバッグ】Mock Embedding生成: {len(text_input)}文字 -> {settings.embedding_dim}次元ダミーベクトル")
        return [0.1] * settings.embedding_dim

    # 本番モード: Ollama Embedding API を呼び出す
    try:
        response = requests.post(
            f"{settings.ollama_url}/api/embeddings",
            json={
                "model": settings.embedding_model,
                "prompt": text_input[:8000]  # テキスト長制限
            },
            timeout=60
        )
        response.raise_for_status()
        result = response.json()

        embedding = result.get("embedding", [])
        if settings.debug_mode:
            print(f"【デバッグ】Embedding生成完了: {len(text_input)}文字 -> {len(embedding)}次元")

        return embedding

    except Exception as e:
        print(f"Embedding generation failed: {e}")
        # エラー時はダミーベクトルを返す
        return [0.0] * settings.embedding_dim


def save_chunk_embeddings(db, file_id: int, chunks: List[dict]) -> int:
    """
    パース結果のチャンクをEmbeddingテーブルに保存

    Args:
        db: DBセッション
        file_id: ファイルID
        chunks: Parserから返されたチャンクリスト

    Returns:
        保存したチャンク数
    """
    saved_count = 0

    for chunk in chunks:
        content = chunk.get("content", "")
        if not content.strip():
            continue

        # Embedding生成
        embedding_vector = generate_embedding(content)

        # section_title の取得と切り詰め処理
        # DB制限（VARCHAR(255)）を超える場合は切り詰める
        raw_section_title = chunk.get("section_title")
        if raw_section_title and len(raw_section_title) > 255:
            section_title = raw_section_title[:250] + "..."
        else:
            section_title = raw_section_title

        # DBに保存
        embedding_record = Embedding(
            file_id=file_id,
            chunk_index=chunk.get("chunk_index", saved_count),
            section_title=section_title,
            page_number=chunk.get("page_number"),
            line_number=chunk.get("line_number"),
            content_chunk=content,
            location_json=chunk.get("location_json"),
            embedding=embedding_vector
        )
        db.add(embedding_record)
        saved_count += 1

    db.commit()
    return saved_count


# ================== Semantic Search (Phase 1-3 RAG) ==================

def semantic_search_chunks(db, query_text: str, exclude_file_id: Optional[int] = None, top_k: int = 5) -> List[dict]:
    """
    コサイン類似度によるセマンティック検索

    Args:
        db: DBセッション
        query_text: 検索クエリテキスト
        exclude_file_id: 除外するファイルID（現在の論文を除外）
        top_k: 取得する上位件数

    Returns:
        類似チャンクのリスト [{"content": str, "section": str, "similarity": float}, ...]
    """
    # クエリのベクトルを生成
    query_embedding = generate_embedding(query_text)

    # pgvector のコサイン類似度検索
    # <=> はコサイン距離（1 - 類似度）なので、小さいほど類似
    query = text("""
        SELECT
            e.content_chunk,
            e.section_title,
            e.page_number,
            f.original_filename,
            p.title as paper_title,
            1 - (e.embedding <=> :query_vector) as similarity
        FROM embeddings e
        JOIN files f ON e.file_id = f.file_id
        JOIN versions v ON f.version_id = v.version_id
        JOIN papers p ON v.paper_id = p.paper_id
        WHERE e.embedding IS NOT NULL
        AND (:exclude_file_id IS NULL OR e.file_id != :exclude_file_id)
        ORDER BY e.embedding <=> :query_vector
        LIMIT :top_k
    """)

    results = db.execute(query, {
        "query_vector": str(query_embedding),
        "exclude_file_id": exclude_file_id,
        "top_k": top_k
    }).fetchall()

    return [
        {
            "content": row[0],
            "section": row[1],
            "page_number": row[2],
            "filename": row[3],
            "paper_title": row[4],
            "similarity": float(row[5]) if row[5] else 0.0
        }
        for row in results
    ]


def semantic_search_conference_rules(db, query_text: str, top_k: int = 3) -> List[dict]:
    """
    学会ルールのセマンティック検索

    Args:
        db: DBセッション
        query_text: 検索クエリテキスト
        top_k: 取得する上位件数

    Returns:
        類似ルールのリスト [{"rule_id": str, "name": str, "style_guide": str, "similarity": float}, ...]
    """
    query_embedding = generate_embedding(query_text)

    query = text("""
        SELECT
            rule_id,
            name,
            style_guide,
            format_rules,
            1 - (embedding <=> :query_vector) as similarity
        FROM conference_rules
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> :query_vector
        LIMIT :top_k
    """)

    results = db.execute(query, {
        "query_vector": str(query_embedding),
        "top_k": top_k
    }).fetchall()

    return [
        {
            "rule_id": row[0],
            "name": row[1],
            "style_guide": row[2],
            "format_rules": row[3],
            "similarity": float(row[4]) if row[4] else 0.0
        }
        for row in results
    ]


# ================== Context Gathering (Phase 1-3) ==================

def get_conference_context(db, conference_rule_id: Optional[str]) -> dict:
    """
    学会ルールのコンテキストを取得
    """
    if not conference_rule_id:
        return {}

    rule = db.query(ConferenceRule).filter(
        ConferenceRule.rule_id == conference_rule_id
    ).first()

    if not rule:
        return {}

    return {
        "name": rule.name,
        "format_rules": rule.format_rules or {},
        "style_guide": rule.style_guide or ""
    }


def get_previous_feedback_context(db, paper: Paper) -> dict:
    """
    前回提出のフィードバックを取得（再提出の場合）
    """
    if not paper.parent_paper_id:
        return {}

    parent_paper = db.query(Paper).filter(
        Paper.paper_id == paper.parent_paper_id
    ).first()

    if not parent_paper:
        return {}

    parent_version = db.query(Version).filter(
        Version.paper_id == parent_paper.paper_id
    ).order_by(Version.version_number.desc()).first()

    if not parent_version:
        return {}

    feedback = db.query(Feedback).filter(
        Feedback.version_id == parent_version.version_id
    ).first()

    if not feedback:
        return {}

    return {
        "parent_title": parent_paper.title,
        "summary": feedback.overall_summary or "",
        "suggestions": (feedback.comments_json or {}).get("suggestions", []),
        "typos": (feedback.comments_json or {}).get("typos", [])
    }


def get_parent_paper_text(db, paper: Paper) -> str:
    """
    前回（親）論文の全文テキストを取得

    再提出論文の場合、親論文のメインファイルをパースしてテキストを抽出する。
    これにより、前回と今回のテキスト差分（Diff）を算出できる。

    Args:
        db: DBセッション
        paper: 現在の論文オブジェクト

    Returns:
        親論文のテキスト（親論文がない場合は空文字）
    """
    # 親論文がない場合は空文字を返す
    if not paper.parent_paper_id:
        return ""

    try:
        # 親論文を取得
        parent_paper = db.query(Paper).filter(
            Paper.paper_id == paper.parent_paper_id
        ).first()

        if not parent_paper:
            if settings.debug_mode:
                print(f"【デバッグ】親論文が見つかりません: parent_paper_id={paper.parent_paper_id}")
            return ""

        # 親論文の最新バージョンを取得
        parent_version = db.query(Version).filter(
            Version.paper_id == parent_paper.paper_id
        ).order_by(Version.version_number.desc()).first()

        if not parent_version:
            if settings.debug_mode:
                print(f"【デバッグ】親論文のバージョンが見つかりません")
            return ""

        # プライマリファイルを取得
        parent_file = db.query(File).filter(
            File.version_id == parent_version.version_id,
            File.is_primary == True
        ).first()

        if not parent_file:
            # プライマリがなければ最初のファイルを使用
            parent_file = db.query(File).filter(
                File.version_id == parent_version.version_id
            ).first()

        if not parent_file or not parent_file.cache_path:
            if settings.debug_mode:
                print(f"【デバッグ】親論文のファイルが見つかりません")
            return ""

        # Parserを呼び出してテキスト抽出
        if settings.debug_mode:
            print(f"【デバッグ】親論文をパース中: {parent_file.cache_path}")

        parse_result = call_parser(parent_file.cache_path)
        parent_text = parse_result.get("text", "")

        if settings.debug_mode:
            print(f"【デバッグ】親論文テキスト取得完了: {len(parent_text)}文字")

        return parent_text

    except Exception as e:
        # エラーが発生してもタスクは継続（Diffはあくまで参考情報）
        print(f"Warning: Failed to get parent paper text: {e}")
        return ""


def generate_diff_summary(old_text: str, new_text: str, max_length: int = 3000) -> str:
    """
    2つのテキスト間の差分サマリーを生成

    Python標準の difflib を使用して unified diff を生成し、
    変更箇所（追加・削除）のみを抽出する。

    Args:
        old_text: 前回のテキスト
        new_text: 今回のテキスト
        max_length: 出力の最大文字数（トークン制限対策）

    Returns:
        差分サマリー文字列（変更がない場合は空文字）
    """
    if not old_text or not new_text:
        return ""

    # テキストを行単位で分割
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    # unified_diff で差分を生成
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile='前回の論文',
        tofile='今回の論文',
        lineterm=''
    )

    # 変更行（+/-）のみを抽出
    # ヘッダー行（---、+++、@@）は含める
    diff_lines = []
    for line in diff:
        # ヘッダー行とコンテキスト変更行のみ抽出
        if line.startswith('---') or line.startswith('+++') or line.startswith('@@'):
            diff_lines.append(line)
        elif line.startswith('+') or line.startswith('-'):
            # 追加・削除行
            diff_lines.append(line)
        # スペースで始まる行（変更なし）は除外

    if not diff_lines:
        return ""

    diff_text = '\n'.join(diff_lines)

    # トークン制限対策: 長すぎる場合は切り捨て
    if len(diff_text) > max_length:
        diff_text = diff_text[:max_length] + "\n\n... (以下省略: 差分が長すぎるため切り捨て)"

    return diff_text


def get_rag_context(db, paper_text: str, current_file_id: Optional[int] = None) -> dict:
    """
    RAGによる関連コンテキストの検索

    Args:
        db: DBセッション
        paper_text: 現在の論文テキスト（クエリとして使用）
        current_file_id: 除外するファイルID

    Returns:
        {
            "related_chunks": [...],  # 関連する過去論文のチャンク
            "related_rules": [...]    # 関連する学会ルール
        }
    """
    # 論文の先頭部分（概要など）をクエリとして使用
    query_text = paper_text[:2000]

    # 関連チャンク検索
    related_chunks = semantic_search_chunks(
        db,
        query_text,
        exclude_file_id=current_file_id,
        top_k=settings.rag_top_k
    )

    # 関連学会ルール検索
    related_rules = semantic_search_conference_rules(
        db,
        query_text,
        top_k=3
    )

    return {
        "related_chunks": related_chunks,
        "related_rules": related_rules
    }


# ================== Prompt Builder (Phase 1-3) ==================

def build_analysis_prompt(
    paper_text: str,
    conference_context: dict,
    previous_feedback: dict,
    rag_context: dict,
    diff_text: str = ""
) -> str:
    """
    コンテキストを含む分析プロンプトを組み立て

    Args:
        paper_text: 論文テキスト
        conference_context: 学会ルールコンテキスト
        previous_feedback: 前回フィードバック
        rag_context: RAG検索結果
        diff_text: 前回論文との差分テキスト（再提出の場合）
    """
    sections = []

    # ヘッダー
    sections.append("あなたは学術論文のレビューを行う専門家です。以下の論文を分析し、改善提案を行ってください。")
    sections.append("")

    # 学会ルールセクション（あれば）
    if conference_context:
        sections.append("=" * 50)
        sections.append("## 対象学会・投稿規定")
        sections.append(f"学会名: {conference_context.get('name', '不明')}")

        format_rules = conference_context.get("format_rules", {})
        if format_rules:
            sections.append("")
            sections.append("### フォーマット規定")
            for key, value in format_rules.items():
                sections.append(f"- {key}: {value}")

        style_guide = conference_context.get("style_guide", "")
        if style_guide:
            sections.append("")
            sections.append("### スタイルガイド")
            sections.append(style_guide)
        sections.append("")

    # RAG: 関連する学会ルール（セマンティック検索結果）
    if rag_context.get("related_rules"):
        sections.append("=" * 50)
        sections.append("## 参考: 関連する学会ガイドライン（類似度検索）")
        for rule in rag_context["related_rules"][:2]:  # 上位2件
            if rule.get("similarity", 0) > 0.3:  # 類似度閾値
                sections.append(f"### {rule['name']} (類似度: {rule['similarity']:.2f})")
                if rule.get("style_guide"):
                    sections.append(rule["style_guide"][:500] + "...")
                sections.append("")

    # 前回フィードバックセクション（あれば）
    if previous_feedback:
        sections.append("=" * 50)
        sections.append("## 前回提出時のフィードバック（参考情報）")
        sections.append(f"前回タイトル: {previous_feedback.get('parent_title', '不明')}")

        if previous_feedback.get("summary"):
            sections.append("")
            sections.append("### 前回の総評")
            sections.append(previous_feedback["summary"])

        if previous_feedback.get("suggestions"):
            sections.append("")
            sections.append("### 前回の改善提案（これらが反映されているか確認してください）")
            for i, suggestion in enumerate(previous_feedback["suggestions"], 1):
                sections.append(f"{i}. {suggestion}")

        sections.append("")
        sections.append("※ 上記の前回フィードバックを踏まえ、改善されている点と残っている課題を明確にしてください。")
        sections.append("")

    # 前回論文との差分セクション（再提出の場合）
    if diff_text:
        sections.append("=" * 50)
        sections.append("## 前回論文との差分（Unified Diff）")
        sections.append("")
        sections.append("以下は前回提出論文との差分です。")
        sections.append("「-」で始まる行は削除された内容、「+」で始まる行は追加された内容を示します。")
        sections.append("この差分を参考に、どのような修正が行われたかを評価してください。")
        sections.append("")
        sections.append("```diff")
        sections.append(diff_text)
        sections.append("```")
        sections.append("")

    # RAG: 関連する過去論文のチャンク
    if rag_context.get("related_chunks"):
        relevant_chunks = [c for c in rag_context["related_chunks"] if c.get("similarity", 0) > 0.5]
        if relevant_chunks:
            sections.append("=" * 50)
            sections.append("## 参考: 関連する過去のフィードバック（類似度検索）")
            for chunk in relevant_chunks[:3]:  # 上位3件
                sections.append(f"### 論文: {chunk.get('paper_title', '不明')} (類似度: {chunk['similarity']:.2f})")
                sections.append(f"セクション: {chunk.get('section', '不明')}")
                sections.append(chunk["content"][:300] + "...")
                sections.append("")

    # 分析依頼
    sections.append("=" * 50)
    sections.append("## 分析内容")
    sections.append("1. 要約（summary）: 200文字程度で論文の概要を説明")
    sections.append("2. 誤字脱字（typos）: 検出された誤字脱字のリスト")
    sections.append("3. 改善提案（suggestions）: 論文を改善するための具体的な提案")

    if previous_feedback:
        sections.append("4. 前回からの改善点（improvements_from_previous）: 前回フィードバックに対する改善状況")

    sections.append("")
    sections.append("## 出力形式（JSON）")
    sections.append("{")
    sections.append('  "summary": "論文の要約...",')
    sections.append('  "typos": ["誤字1", "誤字2"],')
    sections.append('  "suggestions": ["提案1", "提案2", "提案3"]')
    if previous_feedback:
        sections.append('  "improvements_from_previous": ["改善点1", "改善点2"]')
    sections.append("}")
    sections.append("")

    # 論文テキスト
    sections.append("=" * 50)
    sections.append("## 論文テキスト")
    sections.append(paper_text[:10000])  # 最初の10000文字のみ
    sections.append("")
    sections.append("## 回答（JSON形式）")

    return "\n".join(sections)


# ================== Parser & LLM Calls ==================

def call_parser(file_path: str) -> dict:
    """
    Parserサービスを呼び出してテキスト抽出
    """
    response = requests.post(
        f"{settings.parser_url}/parse",
        json={"file_path": file_path},
        timeout=120
    )
    response.raise_for_status()
    result = response.json()

    if "content" in result:
        return {
            "text": result["content"],
            "meta": result.get("meta", {}),
            "pages": result.get("pages", []),
            "chunks": result.get("chunks", [])
        }
    elif "text" in result:
        return {
            "text": result["text"],
            "meta": {},
            "pages": [],
            "chunks": []
        }
    else:
        raise ValueError("Parser response missing both 'content' and 'text' fields")


def call_ollama(prompt: str, is_mock_extended: bool = False) -> dict:
    """
    Ollamaを呼び出してテキスト分析

    Mockモード時はプロンプト内容をそのまま返す（デバッグ用）
    これにより、RAGがどのようなコンテキストを検索・注入したかを確認できる
    """
    # Mockモード: プロンプト内容をそのまま返す
    # Phase 1-3改善: 固定デモデータではなく、実際のプロンプトを返すことで
    # RAGの動作確認とデバッグを容易にする
    if settings.mock_mode:
        print("Mock mode: Returning prompt content for debugging...")
        time.sleep(1)

        # プロンプトを適切な長さに分割してsuggestionsに格納
        # フロントエンドの「改善提案」欄でプロンプト内容を確認できるようにする
        prompt_lines = prompt.split('\n')
        prompt_chunks = []

        # 長いプロンプトを見やすく分割（空行で区切られたセクション単位）
        current_chunk = []
        for line in prompt_lines:
            current_chunk.append(line)
            if line.strip() == '' and len(current_chunk) > 5:
                prompt_chunks.append('\n'.join(current_chunk))
                current_chunk = []
        if current_chunk:
            prompt_chunks.append('\n'.join(current_chunk))

        return {
            "summary": f"【Mock: プロンプト確認モード】\n以下はLLMに送信される予定だったプロンプトの内容です。\nプロンプト全長: {len(prompt)}文字",
            "typos": [],
            "suggestions": prompt_chunks if prompt_chunks else [prompt],
            "improvements_from_previous": []
        }

    # 実際のOllama呼び出し
    response = requests.post(
        f"{settings.ollama_url}/api/generate",
        json={
            "model": "gemma2:2b",
            "prompt": prompt,
            "stream": False
        },
        timeout=300
    )
    response.raise_for_status()

    result = response.json()
    response_text = result.get("response", "")

    # JSONをパース
    try:
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0]
        elif "{" in response_text:
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            json_str = response_text[start:end]
        else:
            json_str = response_text

        return json.loads(json_str)
    except Exception:
        return {
            "summary": response_text[:500],
            "typos": [],
            "suggestions": ["AIの応答をJSONとしてパースできませんでした"]
        }


# ================== Task Processing ==================

def process_diagnosis_task(task_data: dict):
    """Process SYSTEM_DIAGNOSIS task (Debug mode only)"""
    print("=" * 50)
    print(" SYSTEM_DIAGNOSIS task received")
    print("=" * 50)

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "worker_check",
            "/app/tests/worker_check.py"
        )
        if spec and spec.loader:
            worker_check = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(worker_check)
            result = worker_check.run_worker_diagnosis(task_data)
            print(f"Diagnosis completed: {result}")
            return result
        else:
            print("ERROR: Could not load worker_check module")
            return None
    except FileNotFoundError:
        print("WARNING: /app/tests/worker_check.py not found")
        return None
    except Exception as e:
        print(f"ERROR in diagnosis task: {e}")
        return None


def process_task(task_id: int, task_data: Optional[dict] = None):
    """
    タスクを処理（Phase 1-3: 完全RAGパイプライン）

    フロー:
    1. InferenceTask / Version / File を取得
    2. Parser でテキスト抽出
    3. チャンクのEmbedding生成・保存
    4. セマンティック検索でコンテキスト収集
    5. プロンプト組み立て
    6. Ollama で分析
    7. Feedback に結果を保存
    8. ステータス更新
    """
    if settings.debug_mode:
        print(f"【デバッグ】タスク処理開始: Task ID={task_id}")
        if task_data:
            print(f"【デバッグ】タスクデータ: {task_data}")

    db = get_db_session()

    try:
        # 1. InferenceTask を取得
        task = db.query(InferenceTask).filter(InferenceTask.task_id == task_id).first()
        if not task:
            print(f"Task {task_id} not found")
            return

        version = task.version
        if not version:
            print(f"Version not found for task {task_id}")
            task.status = TaskStatus.ERROR
            task.error_message = "Version not found"
            db.commit()
            return

        paper = version.paper

        # プライマリファイルを取得
        primary_file = db.query(File).filter(
            File.version_id == version.version_id,
            File.is_primary == True
        ).first()

        if not primary_file:
            primary_file = db.query(File).filter(
                File.version_id == version.version_id
            ).first()

        if not primary_file or not primary_file.cache_path:
            print(f"No file found for version {version.version_id}")
            task.status = TaskStatus.ERROR
            task.error_message = "No file found"
            db.commit()
            return

        file_path = primary_file.cache_path
        print(f"Processing task {task_id} for file {file_path}")

        # ========== PARSING Phase ==========
        task.status = TaskStatus.PARSING
        task.started_at = datetime.utcnow()
        db.commit()
        publish_notification(task_id, "PARSING", "PDF解析中 (1/4)")

        if settings.debug_mode:
            print(f"【デバッグ】Parserコンテナへテキスト抽出を依頼中...")

        parse_result = call_parser(file_path)
        parsed_text = parse_result["text"]
        chunks = parse_result.get("chunks", [])

        if settings.debug_mode:
            print(f"【デバッグ】Parser完了: {len(parsed_text)}文字, {len(chunks)}チャンク")

        # ========== RAG Phase: Embedding & Search ==========
        task.status = TaskStatus.RAG
        db.commit()
        publish_notification(task_id, "RAG", "Embedding生成・検索中 (2/4)")

        # チャンクがある場合はEmbedding生成・保存
        if chunks:
            if settings.debug_mode:
                print(f"【デバッグ】Embedding生成開始: {len(chunks)}チャンク")
            saved_count = save_chunk_embeddings(db, primary_file.file_id, chunks)
            if settings.debug_mode:
                print(f"【デバッグ】Embedding保存完了: {saved_count}件")
        else:
            # チャンクがない場合は論文全体を1チャンクとして保存
            if settings.debug_mode:
                print(f"【デバッグ】チャンクなし。論文全体を1チャンクとして処理")
            chunks = [{"content": parsed_text[:5000], "chunk_index": 0}]
            save_chunk_embeddings(db, primary_file.file_id, chunks)

        # コンテキスト収集
        if settings.debug_mode:
            print(f"【デバッグ】コンテキスト収集開始...")

        # 学会ルールコンテキスト（ID指定）
        conference_context = get_conference_context(db, task.conference_rule_id)

        # 前回フィードバックコンテキスト
        previous_feedback = get_previous_feedback_context(db, paper) if paper else {}

        # RAGコンテキスト（セマンティック検索）
        rag_context = get_rag_context(db, parsed_text, current_file_id=primary_file.file_id)

        if settings.debug_mode:
            print(f"【デバッグ】RAGコンテキスト: 関連チャンク{len(rag_context.get('related_chunks', []))}件, 関連ルール{len(rag_context.get('related_rules', []))}件")

        # 前回論文との差分を生成（再提出の場合）
        diff_text = ""
        if paper and paper.parent_paper_id:
            if settings.debug_mode:
                print(f"【デバッグ】差分生成開始: 親論文ID={paper.parent_paper_id}")

            parent_text = get_parent_paper_text(db, paper)
            if parent_text:
                diff_text = generate_diff_summary(parent_text, parsed_text)
                if settings.debug_mode:
                    print(f"【デバッグ】差分生成完了: {len(diff_text)}文字")
            else:
                if settings.debug_mode:
                    print(f"【デバッグ】親論文のテキスト取得失敗、差分はスキップ")

        # ========== LLM Phase ==========
        task.status = TaskStatus.LLM
        db.commit()
        publish_notification(task_id, "LLM", "AI分析中 (3/4)")

        # プロンプト組み立て
        prompt = build_analysis_prompt(
            paper_text=parsed_text,
            conference_context=conference_context,
            previous_feedback=previous_feedback,
            rag_context=rag_context,
            diff_text=diff_text
        )

        if settings.debug_mode:
            print(f"【デバッグ】プロンプト長: {len(prompt)}文字")

        # 拡張MOCKモード判定
        is_mock_extended = (
            settings.mock_mode and
            settings.debug_mode and
            task_data and
            task_data.get("debug_prompt", False)
        )

        print("Calling Ollama for analysis...")
        result = call_ollama(prompt, is_mock_extended=is_mock_extended)
        print("Ollama analysis complete")

        # ========== Save Feedback ==========
        comments = {
            "typos": result.get("typos", []),
            "suggestions": result.get("suggestions", [])
        }

        if "improvements_from_previous" in result:
            comments["improvements_from_previous"] = result["improvements_from_previous"]

        if "_debug_prompt" in result:
            comments["_debug_prompt"] = result["_debug_prompt"]
            comments["_debug_prompt_length"] = result["_debug_prompt_length"]

        # RAG情報を保存（デバッグ用）
        comments["_rag_stats"] = {
            "related_chunks_count": len(rag_context.get("related_chunks", [])),
            "related_rules_count": len(rag_context.get("related_rules", [])),
            "embeddings_saved": len(chunks),
            "diff_length": len(diff_text) if diff_text else 0,
            "has_parent_paper": bool(paper and paper.parent_paper_id)
        }

        feedback = Feedback(
            version_id=version.version_id,
            task_id=task.task_id,
            score_json=None,
            comments_json=comments,
            overall_summary=result.get("summary", "")
        )
        db.add(feedback)

        # ========== Complete ==========
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.utcnow()

        if paper:
            paper.status = PaperStatus.COMPLETED

        db.commit()
        publish_notification(task_id, "COMPLETED", "分析完了 (4/4)")
        print(f"Task {task_id} completed successfully")

    except Exception as e:
        print(f"Error processing task {task_id}: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()

        try:
            task = db.query(InferenceTask).filter(InferenceTask.task_id == task_id).first()
            if task:
                task.status = TaskStatus.ERROR
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()

                if task.version and task.version.paper:
                    task.version.paper.status = PaperStatus.ERROR

                db.commit()
                publish_notification(task_id, "ERROR", error_message=str(e))
        except Exception as inner_e:
            print(f"Failed to update error status: {inner_e}")

    finally:
        db.close()


def parse_task_data(data: bytes) -> tuple:
    """Parse task data from Redis."""
    try:
        decoded = data.decode("utf-8")

        try:
            task_data = json.loads(decoded)
            if isinstance(task_data, dict):
                if task_data.get("type") == "SYSTEM_DIAGNOSIS":
                    return ("SYSTEM_DIAGNOSIS", task_data)
                if "task_id" in task_data:
                    job_type = task_data.get("job_type", "ANALYSIS")
                    if job_type == "REFERENCE_ONLY":
                        return ("REFERENCE_ONLY", task_data)
                    return ("REGULAR", task_data)
        except json.JSONDecodeError:
            pass

        task_id = int(decoded)
        return ("REGULAR", {"task_id": task_id, "job_type": "ANALYSIS"})

    except Exception as e:
        print(f"Error parsing task data: {e}")
        return (None, None)


def main():
    """Main worker loop."""
    print("=" * 50)
    print(" NAK-BASE AI INFERENCE WORKER")
    print(" Phase 1-3: Full RAG Pipeline")
    print("=" * 50)
    print(f"Redis: {settings.redis_url}")
    print(f"Ollama: {settings.ollama_url}")
    print(f"Parser: {settings.parser_url}")
    print(f"Embedding Model: {settings.embedding_model}")
    print(f"Embedding Dim: {settings.embedding_dim}")
    print(f"RAG Top-K: {settings.rag_top_k}")
    print(f"Debug Mode: {settings.debug_mode}")
    print(f"Mock Mode: {settings.mock_mode}")

    client = get_redis_client()

    while True:
        try:
            client.ping()
            print("Connected to Redis")
            break
        except redis.ConnectionError:
            print("Waiting for Redis...")
            time.sleep(2)

    print("Worker ready. Waiting for tasks...")

    while True:
        try:
            result = client.blpop(TASK_QUEUE, timeout=30)

            if result:
                _, data = result
                task_type, task_data = parse_task_data(data)

                if task_type == "SYSTEM_DIAGNOSIS":
                    print(f"Received SYSTEM_DIAGNOSIS task")
                    process_diagnosis_task(task_data)

                elif task_type == "REFERENCE_ONLY":
                    task_id = task_data.get("task_id")
                    print(f"Received REFERENCE_ONLY task: {task_id} (skipping analysis)")

                elif task_type == "REGULAR":
                    task_id = task_data.get("task_id")
                    job_type = task_data.get("job_type", "ANALYSIS")
                    conference_id = task_data.get("conference_id")
                    parent_paper_id = task_data.get("parent_paper_id")
                    print(f"Received regular task: {task_id} (job_type: {job_type}, conference: {conference_id}, parent: {parent_paper_id})")
                    process_task(task_id, task_data)

                else:
                    print(f"Unknown task type, skipping: {data}")

        except Exception as e:
            print(f"Worker error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
