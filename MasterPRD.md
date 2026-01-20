# 設計指示書

## 論文フィードバックシステム開発 統合指示書 (Master PRD)

### 1. プロジェクト概要

**プロジェクト名:** # nak-base (nakamura knowledge database) ~研究室の『集合知』で、最高の一本を。~

開発の目的:

大学ゼミにおける論文指導の非効率性（教員の負荷、学生の待ち時間、フィードバックの質のばらつき）を解消する。教員と学生の間に「AIによる即時フィードバック層」を設けることで、形式的なミスや論理的な矛盾を事前に解決し、人間同士の本質的な議論の時間を最大化する。

**主要機能:**

- 論文（PDF/TeX）のアップロードとGoogle Driveへの自動保存。
- マルチエージェントAIによる「形式・論理・内容」の多層的フィードバック。
- 論文のバージョン管理と、過去の指摘（差分）を踏まえた継続的な指導。
- ゼミ全体でのナレッジ共有（過去論文のRAG検索）。

### 2. システムアーキテクチャ

本システムは、**Docker Compose** を用いたマイクロサービス構成（多コンテナ構成）で開発する。各コンテナは疎結合を保ち、スケーラビリティを確保する。

### コンテナ構成

1. **Frontend (Next.js):** ユーザーインターフェース。
2. **Operating API (FastAPI):** システムの中核。認証、DB操作、Drive連携、タスク管理。
3. **Message Queue (Redis):** 非同期タスクのブローカー。
4. **AI Inference Worker (Python):** Gemini APIを用いた推論実行、RAG処理。
5. **Database (PostgreSQL):** メタデータ管理、ベクトルデータ保存（pgvector）。

### 3. データフローとワークフロー

**処理の流れ (Asynchronous Pipeline):**

1. **Upload:** FrontendからOperating APIへファイルを送信。
2. **Storage:** Operating APIがGoogle Driveへファイルをアップロードし、`file_id`を取得。
3. **Registration:** DBに論文バージョン(`Processing`)を登録。Frontendには「受付完了」を即時レスポンス。
4. **Queueing:** Operating APIがRedisに「推論タスク（`paper_id`, `file_id`, `学会ルールID`）」をPush。
5. **Inference:**
    - AI WorkerがRedisからタスクを取得。
    - Google Driveからファイルをダウンロード。
    - Vector DBから「過去の類似論文」と「前回のFBデータ」を取得。
    - Gemini APIへコンテキスト付きでリクエスト。
6. **Completion:** AI Workerが結果（全体レポートPDF + 詳細JSON）をDriveとDBに保存。ステータスを`Completed`に更新。

### 4. データベース設計 (PostgreSQL Schema)

以下のER設計を実装すること。

- **Users:** `user_id`, `email`, `role` (Student/Professor)
- **Papers:** `paper_id`, `user_id`, `title`, `target_conference`, `status`
- **Versions:** `version_id`, `paper_id`, `drive_file_id`, `version_number` (自動採番), `created_at`
- **Feedbacks:** `feedback_id`, `version_id`, `report_drive_id`, `score_json` (各項目の点数), `comments_json` (座標/行数付き詳細指摘)
- **Seminars (RAG Source):** `doc_id`, `content_vector`, `meta_data` (過去論文や議事録)

### 5. 各コンテナの実装要件

### A. Frontend (Next.js)

- **UI:** モダンでリッチなダッシュボード。
- **機能:**
    - ドラッグ＆ドロップによるファイルアップロード。
    - 進捗ステータスバー（受付済 -> 解析中 -> 完了）。
    - FBレポート表示画面（PDFビューアの横にAIコメントを表示、またはオーバーレイ）。
    - 教授用ビュー：全学生の最新バージョンとスコア一覧（ヒートマップ等）。

### B. Operating API (FastAPI)

- **Google Drive連携:** サービスアカウントを使用。指定された「ゼミ共有ルートフォルダ」の下に `/{StudentName}/{PaperTitle}/` の構造を自動生成して保存。
- **非同期処理:** `Celery` または `rq` を使用してRedisへジョブを投入。

### C. AI Inference Worker (Python)

- **LLM:** Google Gemini 1.5 Pro/Flash (API) を使用。
- **エージェントロジック:**
    1. **Parser:** PyMuPDF等でPDF/TeXからテキスト構造を抽出。
    2. **Linter Agent:** 誤字脱字、学会フォーマット（DEIM/IPSJ等）違反の検出。
    3. **Logic Agent:** AbstractとConclusionの整合性、章立ての論理チェック。
    4. **RAG Agent:** Vector DBから類似研究を検索し「過去の優秀論文ではこう記述されている」と提示。
- **差分考慮:** DBから「前回のFB」を取得し、「前回の指摘（X）が今回修正されているか？」を検証するステップを含めること。

### 6. 開発ガイドライン

- **環境:** Docker Composeですべてが立ち上がる (`docker-compose up --build`) 状態にすること。
- **環境変数:** `.env` ファイルですべての機密情報（API Key, DB URL, Drive Folder ID）を管理すること。
- **エラーハンドリング:** 推論失敗時もシステムを停止させず、ステータスを `Error` にしてDBにログを残すこと。

### 7. デリバリー成果物

AIエージェントは以下のファイル群を作成してください。

1. `docker-compose.yml`
2. `/frontend`: Next.js プロジェクトソース
3. `/backend`: FastAPI プロジェクトソース
4. `/worker`: AI Worker プロジェクトソース
5. `/db`: 初期化用SQL (Schema定義)
6. `README.md`: 起動手順と環境変数の設定方法

---
サービスアカウントのjsonキーやgemini api キーを置くためのディレクトリを作り、そこを参照するようにしてください。
**指示は以上です。この要件に基づき、MVP（Minimum Viable Product）の実装コードを作成してください。**
