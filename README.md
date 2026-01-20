# nak-base

**nakamura knowledge database** - 研究室の『集合知』で、最高の一本を。

論文フィードバックシステム - AIによる多層的フィードバックで論文の質を向上させます。

## 機能

- 論文（PDF/TeX）のアップロードとGoogle Driveへの自動保存
- マルチエージェントAIによる「形式・論理・内容」の多層的フィードバック
- 論文のバージョン管理と、過去の指摘を踏まえた継続的な指導
- ゼミ全体でのナレッジ共有（過去論文のRAG検索）

## システム構成

| コンテナ | 技術スタック | 役割 |
|---------|-------------|------|
| frontend | Next.js 14 | ユーザーインターフェース |
| backend | FastAPI | API、認証、DB操作、Drive連携 |
| worker | Python | AI推論、RAG処理 |
| redis | Redis | メッセージキュー |
| db | PostgreSQL + pgvector | メタデータ・ベクトルDB |

## 起動方法

### 1. 事前準備

#### Google Cloud設定

1. Google Cloud Consoleでプロジェクトを作成
2. Google Drive APIを有効化
3. サービスアカウントを作成し、JSONキーをダウンロード
4. ダウンロードしたJSONを `secrets/service-account.json` として保存
5. Google Driveでゼミ共有フォルダを作成
6. 共有フォルダをサービスアカウントのメールアドレスと共有（編集権限）

#### Gemini API設定

1. [Google AI Studio](https://makersuite.google.com/app/apikey) でAPIキーを取得

### 2. 環境変数設定

```bash
cp .env.example .env
```

`.env` ファイルを編集して以下を設定：

```env
POSTGRES_USER=nakbase
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=nakbase
SECRET_KEY=your-secret-key
GOOGLE_DRIVE_FOLDER_ID=your-google-drive-folder-id
GEMINI_API_KEY=your-gemini-api-key
```

### 3. シークレットファイル配置

```bash
# secretsディレクトリにサービスアカウントのJSONを配置
cp /path/to/your-service-account.json secrets/service-account.json
```

### 4. 起動

```bash
docker-compose up --build
```

### 5. アクセス

- フロントエンド: http://localhost:3000
- バックエンドAPI: http://localhost:8000
- API ドキュメント: http://localhost:8000/docs

## 使い方

### 1. ユーザー登録

1. http://localhost:3000/users にアクセス
2. 「新規ユーザー」から学生または教授を登録

### 2. 論文アップロード

1. http://localhost:3000/upload にアクセス
2. ユーザーを選択
3. 論文タイトルを入力
4. 対象学会フォーマットを選択（DEIM, IPSJ, 一般）
5. PDF/TeXファイルをドラッグ＆ドロップ
6. 「アップロードして分析開始」をクリック

### 3. フィードバック確認

1. http://localhost:3000/papers にアクセス
2. 論文をクリックして詳細表示
3. 各バージョンのスコアとフィードバックを確認

### 4. ダッシュボード（教授向け）

1. http://localhost:3000/dashboard にアクセス
2. 全学生の論文状況とスコアを一覧確認

## ディレクトリ構成

```
nak_base/
├── docker-compose.yml
├── .env.example
├── README.md
├── MasterPRD.md
├── secrets/                    # シークレットファイル
│   └── service-account.json    # Google サービスアカウントキー
├── db/
│   └── init.sql               # PostgreSQLスキーマ
├── backend/                   # FastAPI バックエンド
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── models.py
│       ├── schemas.py
│       ├── routers/
│       └── services/
├── worker/                    # AI推論ワーカー
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── worker.py
│       ├── config.py
│       ├── database.py
│       └── agents/
│           ├── parser.py      # PDF/TeXパーサー
│           ├── linter.py      # 形式チェックエージェント
│           ├── logic.py       # 論理チェックエージェント
│           ├── rag.py         # RAG検索エージェント
│           └── diff_checker.py # 差分確認エージェント
└── frontend/                  # Next.js フロントエンド
    ├── Dockerfile
    ├── package.json
    └── app/
        ├── layout.tsx
        ├── page.tsx
        ├── upload/
        ├── papers/
        ├── dashboard/
        └── users/
```

## API エンドポイント

### Users
- `POST /users/` - ユーザー作成
- `GET /users/` - ユーザー一覧
- `GET /users/{user_id}` - ユーザー詳細

### Papers
- `POST /papers/` - 論文作成
- `GET /papers/` - 論文一覧
- `GET /papers/{paper_id}` - 論文詳細（バージョン含む）
- `POST /papers/{paper_id}/upload` - 新バージョンアップロード

### Feedbacks
- `GET /feedbacks/version/{version_id}` - バージョンのフィードバック取得
- `GET /feedbacks/task/{task_id}` - タスクステータス確認

### Dashboard
- `GET /dashboard/professor` - 教授用ダッシュボード
- `GET /dashboard/student/{user_id}` - 学生用ダッシュボード
- `GET /dashboard/conference-rules` - 学会フォーマット一覧

## AI分析の内容

### 1. 形式チェック（Linter Agent）
- 誤字脱字検出
- 文法エラー検出
- 学会フォーマット適合性チェック

### 2. 論理チェック（Logic Agent）
- AbstractとConclusionの整合性
- 章立ての論理的な流れ
- 主張と根拠の対応

### 3. RAG検索（RAG Agent）
- 過去の類似論文検索
- 新規性評価
- 参考文献の提案

### 4. 差分チェック（Diff Checker）
- 前回の指摘の改善確認
- 新たな問題点の検出

## 開発

### ローカル開発

```bash
# バックエンドのみ起動
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# フロントエンドのみ起動
cd frontend
npm install
npm run dev
```

### データベースリセット

```bash
docker-compose down -v
docker-compose up --build
```

## トラブルシューティング

### Google Drive連携エラー

1. サービスアカウントのJSONが正しく配置されているか確認
2. Drive APIが有効になっているか確認
3. 共有フォルダがサービスアカウントと共有されているか確認

### AI分析が完了しない

1. Gemini APIキーが正しく設定されているか確認
2. `docker logs nak_base_worker` でワーカーのログを確認
3. Redisが正常に動作しているか確認

## ライセンス

MIT License
