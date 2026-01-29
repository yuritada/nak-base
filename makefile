# nak-base MVP
COMPOSE = docker-compose

.PHONY: help up build down restart clean logs ps setup-ollama debug-up debug-down test test-parser

# デフォルトのターゲット
help:
	@echo "nak-base MVP - 使用可能なコマンド:"
	@echo ""
	@echo "  make up           - コンテナをバックグラウンドで起動"
	@echo "  make build        - キャッシュなしでイメージをビルド"
	@echo "  make down         - コンテナを停止"
	@echo "  make restart      - コンテナを再起動"
	@echo "  make clean        - コンテナ、ボリューム、イメージを完全削除"
	@echo "  make logs         - ログをリアルタイム表示"
	@echo "  make ps           - コンテナ状態を表示"
	@echo "  make setup-ollama - Ollamaモデルをダウンロード（初回のみ）"
	@echo ""
	@echo "デバッグ用コマンド:"
	@echo "  make debug-up     - デバッグモードで起動（テストコード含む）"
	@echo "  make debug-down   - デバッグモードを停止"
	@echo "  make test         - システム診断を実行"
	@echo "  make test-parser  - Parser高度機能テスト（Phase 1-2）"
	@echo ""
	@echo "初回セットアップ手順:"
	@echo "  1. make build"
	@echo "  2. make up"
	@echo "  3. make setup-ollama"
	@echo "  4. http://localhost:3000 にアクセス"

# コンテナの起動（本番モード）
up:
	$(COMPOSE) up -d
	$(COMPOSE) logs -f --tail="all" > logs.txt 2>&1 &

# イメージのビルド
build:
	$(COMPOSE) build --no-cache

# コンテナの停止
down:
	$(COMPOSE) down
	-pkill -f "$(COMPOSE) logs"

# 再起動
restart:
	$(COMPOSE) down
	$(COMPOSE) up -d

# 強力なクリーンアップ（DB、ボリューム、イメージ、キャッシュ、ログを全て吹き飛ばす）
# デバッグ用を含めた全構成ファイルを定義
COMPOSE_FILES = -f docker-compose.yml -f docker-compose.debug.yml

# 強力なクリーンアップ
clean:
	@echo "システム全体の完全リセットを開始します..."
	# 1. 両方の設定ファイルを明示的に指定して、ボリュームごと削除
	docker-compose $(COMPOSE_FILES) down --volumes --rmi all --remove-orphans
	# 2. 名前のないボリュームや、迷子になったボリュームを強制削除
	docker volume prune -f
	# 3. キャッシュとログの削除
	docker builder prune -f
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf logs/
	rm -f logs.txt
	@echo "完全クリーンアップ完了"
	

# ログの表示
logs:
	$(COMPOSE) logs -f --tail="all"

# 特定サービスのログ
logs-backend:
	$(COMPOSE) logs -f backend

logs-worker:
	$(COMPOSE) logs -f worker

logs-ollama:
	$(COMPOSE) logs -f ollama

# ステータス確認
ps:
	$(COMPOSE) ps

# Ollamaモデルのセットアップ（初回のみ必要）
setup-ollama:
	@echo "Ollamaにgemma2:2bモデルをダウンロード中..."
	@echo "これには数分かかる場合があります..."
	docker exec nak_base_ollama ollama pull gemma2:2b
	@echo "モデルのダウンロード完了！"

# ===========================================
# Debug Mode Commands
# ===========================================

# デバッグモードで起動（テストコードをマウント）
debug-up:
	@echo "デバッグモードで起動中..."
	@mkdir -p logs
	$(COMPOSE) -f docker-compose.yml -f docker-compose.debug.yml up -d
	$(COMPOSE) logs -f --tail="all" > logs.txt 2>&1 &
	@echo ""
	@echo "デバッグモードで起動しました。"
	@echo "テストを実行するには: make test"

# デバッグモードを停止
debug-down:
	$(COMPOSE) -f docker-compose.yml -f docker-compose.debug.yml down
	-pkill -f "$(COMPOSE) logs"

# システム診断を実行（デバッグモード専用）
# test:
# 	@echo "=============================================="
# 	@echo " Running System Diagnosis..."
# 	@echo "=============================================="
# 	@docker compose exec backend python /app/tests/run_diagnosis.py || \
# 		(echo ""; echo "ERROR: テスト実行に失敗しました。"; \
# 		 echo "デバッグモードで起動していますか？ (make debug-up)"; \
# 		 exit 1)
# 	@echo ""
# 	@echo "診断結果は logs/system_diagnosis.log に保存されました。"
# 	# システム診断を実行（デバッグモード専用）
test:
	@echo "=============================================="
	@echo " Installing Debug Dependencies..."
	@echo "=============================================="
	# backendコンテナ内に、その場だけ必要なライブラリをインストール
	@docker compose exec backend pip install requests redis
	@echo ""
	@echo "=============================================="
	@echo " Running System Diagnosis..."
	@echo "=============================================="
	@docker compose exec backend python /app/tests/run_diagnosis.py || \
		(echo ""; echo "ERROR: テスト実行に失敗しました。"; \
		 echo "デバッグモードで起動していますか？ (make debug-up)"; \
		 exit 1)

# 診断ログを表示
show-diagnosis:
	@cat logs/system_diagnosis.log 2>/dev/null || echo "診断ログが見つかりません。make test を実行してください。"

# Parser Service テスト（Phase 1-2）
test-parser:
	@echo "=============================================="
	@echo " Running Parser Advanced Tests..."
	@echo "=============================================="
	@docker compose exec backend pip install requests > /dev/null 2>&1
	@docker compose exec backend python /app/tests/test_parser_advanced.py || \
		(echo ""; echo "ERROR: Parser tests failed."; exit 1)
