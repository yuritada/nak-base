# tests/mock_ollama.py
#
# Multi-Agent Pipeline 対応モックサーバー
# - 既存の Ollama 互換 (/api/generate, /api/chat, /api/embeddings, /api/tags) を維持
# - X-Agent-Type ヘッダ (linter / logic / rag / diff) を見て、エージェント別の JSON を返す
# - コントロールパネル (/) からエージェント別レスポンスをそれぞれ更新できる
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
import json
import asyncio

app = FastAPI(title="Mock Ollama / Multi-Agent API")

# ----- エージェント別のデフォルト・モックレスポンス（JSON文字列） -----
DEFAULT_AGENT_RESPONSES = {
    "linter": json.dumps({
        "typos": [
            {"text": "誤字サンプル", "suggestion": "修正サンプル", "location": "p.3 第2段落"}
        ],
        "format_violations": [
            {"rule": "ページ数上限", "detail": "本文が規定の8ページを超過しています",
             "suggestion": "結論部の冗長表現を削減"}
        ],
        "summary": "[Mock/Linter] フォーマット観点でのダミー所見。"
    }, ensure_ascii=False, indent=2),

    "logic": json.dumps({
        "section_summaries": [
            {"section": "1. はじめに", "summary": "[Mock] 研究背景と課題のダミー要約。"},
            {"section": "3. 提案手法", "summary": "[Mock] 手法のダミー要約。"}
        ],
        "logical_gaps": [
            {"location": "3.2 の主張", "issue": "根拠データなしに性能向上を主張",
             "suggestion": "実験条件と比較対象を明示する"}
        ],
        "abstract_conclusion_alignment": {
            "aligned": True,
            "comment": "[Mock] AbstractとConclusionは概ね整合している（ダミー判定）。"
        },
        "structural_issues": ["[Mock] 関連研究セクションが薄い"],
        "summary": "[Mock/Logic] 論理観点でのダミー所見。"
    }, ensure_ascii=False, indent=2),

    "rag": json.dumps({
        "related_works": [
            {"source": "[Mock] 過去論文 A / 第2章 (p.5)", "similarity": 0.82,
             "insight": "同様のテーマで先行研究が存在し、評価指標XXを採用している"}
        ],
        "improvement_hints": [
            "[Mock] 過去の優秀論文では実験設定の表（パラメータ一覧）が章末に提示されていた"
        ],
        "summary": "[Mock/RAG] 関連知見のダミー所見。"
    }, ensure_ascii=False, indent=2),

    "diff": json.dumps({
        "improvements": [
            {"previous_issue": "[Mock] 前回指摘されていた誤字",
             "addressed": True,
             "evidence": "差分のp.4で当該語が修正されている",
             "comment": ""}
        ],
        "remaining_issues": ["[Mock] 前回指摘の図1のキャプション不足が未対応"],
        "new_concerns": ["[Mock] 改稿で導入された新章の論理が浅い"],
        "summary": "[Mock/Diff] 改稿差分観点のダミー所見。"
    }, ensure_ascii=False, indent=2),

    # 旧シングルエージェント互換（agentヘッダなし）
    "_default": "[Mock] これはテスト用の固定レスポンスです。\n受け取ったプロンプトの先頭: {prompt}...",
}

state = {
    "received_prompt": "まだプロンプトは受信されていません",
    "last_agent": "(未受信)",
    "responses": dict(DEFAULT_AGENT_RESPONSES),
}


def _get_response_for(agent: str | None, prompt: str) -> str:
    """エージェント名から該当のモックレスポンス文字列を返す。{prompt} は置換する。"""
    key = (agent or "").lower() if agent else "_default"
    if key not in state["responses"]:
        key = "_default"
    template = state["responses"].get(key, DEFAULT_AGENT_RESPONSES["_default"])
    return template.replace("{prompt}", prompt[:30])


@app.get("/", response_class=HTMLResponse)
async def index():
    # 各エージェントのテキストエリアを動的生成
    agent_blocks = []
    for key in ["linter", "logic", "rag", "diff", "_default"]:
        label = "Default (旧シングルエージェント)" if key == "_default" else key.upper()
        value = state["responses"].get(key, "")
        # HTMLエスケープ最低限
        safe = (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        agent_blocks.append(f"""
            <div class="section">
              <h3>{label} レスポンス</h3>
              <textarea data-key="{key}">{safe}</textarea>
              <button onclick="updateResponse('{key}')">「{label}」を更新</button>
            </div>
        """)
    agent_blocks_html = "\n".join(agent_blocks)

    html_content = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>Mock Ollama / Multi-Agent Control Panel</title>
        <style>
            body {{ font-family: 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 0; background-color: #f9f9f9; color: #333; }}
            .header {{ background-color: #007bff; color: white; padding: 20px; text-align: center; }}
            .container {{ max-width: 960px; margin: 30px auto; padding: 20px; background: white; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            h2, h3 {{ color: #007bff; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
            textarea {{ width: 100%; height: 180px; padding: 10px; font-size: 13px; font-family: ui-monospace, Menlo, Consolas, monospace; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; resize: vertical; }}
            pre {{ background: #f4f4f4; padding: 15px; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-family: monospace; border: 1px solid #ddd; max-height: 300px; overflow-y: auto; }}
            .section {{ margin-bottom: 30px; }}
            button {{ padding: 10px 20px; font-size: 14px; cursor: pointer; background-color: #28a745; color: white; border: none; border-radius: 5px; transition: background 0.3s; }}
            button:hover {{ background-color: #218838; }}
            .btn-secondary {{ background-color: #6c757d; }}
            .btn-secondary:hover {{ background-color: #5a6268; }}
            .agent-tag {{ display: inline-block; background:#eef; color:#226; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Mock Ollama / Multi-Agent Control Panel</h1>
            <small>各エージェント（Linter / Logic / RAG / Diff）が返す JSON を個別に編集できます</small>
        </div>
        <div class="container">
            <div class="section">
                <h2>最後に受信したプロンプト <span class="agent-tag">agent: {state['last_agent']}</span></h2>
                <pre>{state['received_prompt']}</pre>
                <button class="btn-secondary" onclick="location.reload()">最新情報を取得</button>
            </div>
            <h2>返信レスポンスの設定（エージェント別）</h2>
            <p>※ 「&#123;prompt&#125;」と書くと受信プロンプトの先頭30文字に置換されます。各テキストエリアは JSON 文字列を入れてください。</p>
            {agent_blocks_html}
        </div>
        <script>
            async function updateResponse(key) {{
                const ta = document.querySelector(`textarea[data-key="${{key}}"]`);
                const newResponse = ta.value;
                const res = await fetch('/update_response', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ key: key, new_response: newResponse }})
                }});
                if (res.ok) {{
                    alert('更新しました');
                    location.reload();
                }} else {{
                    alert('更新に失敗しました');
                }}
            }}
        </script>
    </body>
    </html>
    """
    return html_content


@app.post("/update_response")
async def update_response(request: Request):
    data = await request.json()
    key = (data.get("key") or "_default").lower()
    new_response = data.get("new_response")
    if new_response is None:
        return JSONResponse({"status": "error", "detail": "new_response missing"}, status_code=400)
    state["responses"][key] = new_response
    return {"status": "ok", "key": key}


@app.post("/api/generate")
async def generate(request: Request):
    data = await request.json()
    prompt = data.get("prompt", "")
    stream = data.get("stream", False)
    model = data.get("model", "gemma2:2b")
    agent = request.headers.get("X-Agent-Type")

    state["received_prompt"] = prompt
    state["last_agent"] = agent or "(なし)"

    response_text = _get_response_for(agent, prompt)

    if stream:
        async def generate_stream():
            chunks = [response_text[i:i + 8] for i in range(0, len(response_text), 8)]
            for chunk_text in chunks:
                yield json.dumps({"model": model, "response": chunk_text, "done": False}) + "\n"
                await asyncio.sleep(0.02)
            yield json.dumps({"model": model, "response": "", "done": True}) + "\n"

        return StreamingResponse(generate_stream(), media_type="application/x-ndjson")
    else:
        return JSONResponse({
            "model": model,
            "response": response_text,
            "done": True
        })


@app.post("/api/chat")
async def chat(request: Request):
    data = await request.json()
    model = data.get("model", "gemma2:2b")
    messages = data.get("messages", [])
    agent = request.headers.get("X-Agent-Type")

    if messages:
        state["received_prompt"] = json.dumps(messages, ensure_ascii=False, indent=2)
        last_message_content = messages[-1].get("content", "")
    else:
        state["received_prompt"] = "No messages"
        last_message_content = ""
    state["last_agent"] = agent or "(なし)"

    response_text = _get_response_for(agent, last_message_content)

    return JSONResponse({
        "model": model,
        "message": {"role": "assistant", "content": response_text},
        "done": True
    })


@app.post("/api/embeddings")
async def embeddings(request: Request):
    """Embedding生成のモック（768次元の固定ダミーベクトル）"""
    data = await request.json()
    prompt = data.get("prompt", "")
    state["received_prompt"] = f"[embedding] {prompt[:200]}"
    state["last_agent"] = "embedding"
    return JSONResponse({"embedding": [0.1] * 768})


@app.get("/api/tags")
async def tags():
    return {"models": [
        {"name": "gemma2:2b"},
        {"name": "nomic-embed-text"},
        {"name": "gemini-1.5-flash"},
        {"name": "gemini-1.5-pro"},
    ]}
