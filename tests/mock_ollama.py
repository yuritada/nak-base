# tests/mock_ollama.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse, RedirectResponse
import json
import asyncio

app = FastAPI(title="Mock Ollama API")

# モックのステータスを保持する辞書
state = {
    "received_prompt": "まだプロンプトは受信されていません",
    "mock_response": "[Mock] これはテスト用の固定レスポンスです。\n受け取ったプロンプトの先頭: {prompt}..."
}

@app.get("/", response_class=HTMLResponse)
async def index():
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>Mock Ollama Control Panel</title>
        <style>
            body {{ font-family: 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 0; background-color: #f9f9f9; color: #333; }}
            .header {{ background-color: #007bff; color: white; padding: 20px; text-align: center; }}
            .container {{ max-width: 800px; margin: 30px auto; padding: 20px; background: white; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            h2 {{ color: #007bff; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
            textarea {{ width: 100%; height: 150px; padding: 10px; font-size: 14px; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; resize: vertical; }}
            pre {{ background: #f4f4f4; padding: 15px; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-family: monospace; border: 1px solid #ddd; max-height: 300px; overflow-y: auto; }}
            .section {{ margin-bottom: 30px; }}
            button {{ padding: 10px 20px; font-size: 16px; cursor: pointer; background-color: #28a745; color: white; border: none; border-radius: 5px; transition: background 0.3s; }}
            button:hover {{ background-color: #218838; }}
            .btn-secondary {{ background-color: #6c757d; }}
            .btn-secondary:hover {{ background-color: #5a6268; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Mock Ollama Control Panel</h1>
        </div>
        <div class="container">
            <div class="section">
                <h2>最後に受信したプロンプト</h2>
                <pre>{state['received_prompt']}</pre>
                <button class="btn-secondary" onclick="location.reload()">最新情報を取得</button>
            </div>
            <div class="section">
                <h2>返信するレスポンスの設定</h2>
                <p>※ 「&#123;prompt&#125;」と記述すると、受信したプロンプトの先頭30文字に置換されます。</p>
                <div id="response-form">
                    <textarea id="new_response" name="new_response">{state['mock_response']}</textarea><br><br>
                    <button onclick="updateResponse()">レスポンスを更新</button>
                </div>
            </div>
        </div>
        <script>
            async function updateResponse() {{
                const newResponse = document.getElementById('new_response').value;
                const res = await fetch('/update_response', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ new_response: newResponse }})
                }});
                if (res.ok) {{
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
    new_response = data.get("new_response")
    if new_response is not None:
        state["mock_response"] = new_response
    return {"status": "ok"}

@app.post("/api/generate")
async def generate(request: Request):
    data = await request.json()
    prompt = data.get("prompt", "")
    stream = data.get("stream", False)
    model = data.get("model", "gemma2:2b")
    
    # 状態の更新
    state["received_prompt"] = prompt
    
    # レスポンスの生成
    mock_response_text = state["mock_response"].replace("{prompt}", prompt[:30])
    
    if stream:
        # ストリーミングレスポンスのモック（NDJSON形式）
        async def generate_stream():
            words = mock_response_text.split(" ")
            # 空白で分割し、後で空白を付与して返す。元の改行などは考慮されない簡易版
            # より自然にするため1文字ずつ返すか、ある程度の塊で返す。
            # 今回は簡易的に文字単位または適当なチャンクで返します。
            chunks = [mock_response_text[i:i+3] for i in range(0, len(mock_response_text), 3)]
            
            for chunk_text in chunks:
                chunk = {
                    "model": model,
                    "response": chunk_text,
                    "done": False
                }
                yield json.dumps(chunk) + "\n"
                await asyncio.sleep(0.05) # 少し遅延を入れてストリーミングっぽくする
            
            final_chunk = {
                "model": model,
                "response": "",
                "done": True
            }
            yield json.dumps(final_chunk) + "\n"
            
        return StreamingResponse(generate_stream(), media_type="application/x-ndjson")
    else:
        # 一括レスポンスのモック
        return JSONResponse({
            "model": model,
            "response": mock_response_text,
            "done": True
        })

@app.post("/api/chat")
async def chat(request: Request):
    data = await request.json()
    model = data.get("model", "gemma2:2b")
    messages = data.get("messages", [])
    
    if messages:
        # 見やすくするためにフォーマット
        state["received_prompt"] = json.dumps(messages, ensure_ascii=False, indent=2)
        last_message_content = messages[-1].get("content", "")
    else:
        state["received_prompt"] = "No messages"
        last_message_content = ""
    
    mock_response_text = state["mock_response"].replace("{prompt}", last_message_content[:30])
    
    return JSONResponse({
        "model": model,
        "message": {"role": "assistant", "content": mock_response_text},
        "done": True
    })

@app.get("/api/tags")
async def tags():
    # 接続テスト用にモデル一覧を返す
    return {"models": [{"name": "gemma2:2b"}]}