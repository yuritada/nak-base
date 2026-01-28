# nak-base MVP

**論文フィードバックシステム MVP版** - PDFを投げたらAIが感想を返す

## 概要

このMVP版は、以下の「鉄の掟」に従い、**確実に動作する最小構成**を実現しています：

- 外部サービス依存なし（Google Drive/OAuth 廃止）
- RAG/ベクトル検索なし（pgvector 廃止）
- PDF座標解析なし（テキスト抽出のみ）
- TeX対応なし（PDF単体ファイルのみ）
- 認証簡略化（デモユーザーのみ）

## システム構成

| コンテナ | 技術スタック | 役割 |
|---------|-------------|------|
| frontend | Next.js 14 | ユーザーインターフェース |
| backend | FastAPI | API、認証 |
| parser | FastAPI + pypdf | PDFからテキスト抽出 |
| worker | Python | タスク処理、Ollama連携 |
| ollama | Ollama | LLM (gemma2:2b) |
| redis | Redis | シンプルなFIFOキュー |
| db | PostgreSQL | メタデータ保存（3テーブルのみ） |

## 起動方法

### 1. ビルド

```bash
make build
```

### 2. コンテナ起動

```bash
make up
```

### 3. Ollamaモデルのダウンロード（初回のみ）

**重要**: 初回起動時は、Ollamaのモデルダウンロードが必要です。
これには数分〜数十分かかる場合があります。

```bash
make setup-ollama
```

### 4. アクセス

- フロントエンド: http://localhost:3000
- バックエンドAPI: http://localhost:8000
- API ドキュメント: http://localhost:8000/docs

## 使い方

### 1. デモログイン

1. http://localhost:3000 にアクセス
2. 「デモを開始する」ボタンをクリック

### 2. 論文アップロード

1. 「アップロード」をクリック
2. 論文タイトルを入力
3. PDFファイルを選択
4. 「アップロードして分析開始」をクリック

### 3. 結果確認

1. 「論文一覧」で論文を確認
2. ステータスが「完了」になったらクリック
3. AIの分析結果（要約、誤字脱字、改善提案）を確認

## データベース構成（MVP版）

3テーブルのシンプルな構成：

### users
- `id`: 1（固定デモユーザー）
- `name`: "Demo User"

### papers
- `id`, `user_id`, `title`, `created_at`

### tasks
- `id`, `paper_id`, `file_path`, `parsed_text`, `status`, `result_json`

## API エンドポイント

### 認証
- `POST /auth/demo-login` - デモユーザーとしてログイン

### Papers
- `GET /papers/` - 論文一覧
- `GET /papers/{paper_id}` - 論文詳細（タスク含む）
- `POST /papers/upload` - 論文アップロード
- `GET /papers/tasks/{task_id}` - タスク詳細

## コマンド一覧

```bash
make help          # ヘルプ表示
make build         # イメージビルド
make up            # コンテナ起動
make down          # コンテナ停止
make restart       # 再起動
make logs          # ログ表示
make logs-worker   # Workerログ表示
make logs-ollama   # Ollamaログ表示
make ps            # ステータス確認
make setup-ollama  # Ollamaモデルダウンロード
make clean         # 完全クリーンアップ
```

## ディレクトリ構成

```
nak_base/
├── docker-compose.yml
├── makefile
├── README.md
├── .env.example
├── db/
│   └── init.sql              # PostgreSQLスキーマ（3テーブル）
├── backend/                  # FastAPI バックエンド
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── models.py
│       ├── schemas.py
│       ├── routers/
│       │   ├── auth.py       # デモログイン
│       │   └── papers.py     # 論文管理
│       └── services/
│           └── queue_service.py
├── parser/                   # PDFパーサーサービス
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       └── main.py
├── worker/                   # タスク処理ワーカー
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── worker.py
│       ├── config.py
│       ├── database.py
│       └── models.py
└── frontend/                 # Next.js フロントエンド
    ├── Dockerfile
    ├── package.json
    └── app/
        ├── layout.tsx
        ├── page.tsx          # ログインページ
        ├── dashboard/        # 論文一覧
        ├── upload/           # アップロード
        └── papers/[id]/      # 結果表示
```

## トラブルシューティング

### Ollamaが応答しない

```bash
# Ollamaのステータス確認
docker logs nak_base_ollama

# モデルが正しくダウンロードされているか確認
docker exec nak_base_ollama ollama list
```

### Workerが処理しない

```bash
# Workerログを確認
make logs-worker
```

### データベースをリセットしたい

```bash
make clean
make build
make up
make setup-ollama
```

## 注意事項

- **初回起動時**: Ollamaのモデルダウンロードに時間がかかります（数分〜数十分）
- **再起動時**: `restart: always` が設定されているため、エラー時は自動復旧します
- **ファイル保存**: PDFはUUIDで一意なファイル名で保存されます

## ライセンス

MIT License
