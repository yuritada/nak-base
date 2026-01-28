# nak-base MVP
COMPOSE = docker-compose

.PHONY: help up build down restart clean logs ps setup-ollama

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
	@echo "初回セットアップ手順:"
	@echo "  1. make build"
	@echo "  2. make up"
	@echo "  3. make setup-ollama"
	@echo "  4. http://localhost:3000 にアクセス"

# コンテナの起動
up:
	$(COMPOSE) up -d

# イメージのビルド
build:
	$(COMPOSE) build --no-cache

# コンテナの停止
down:
	$(COMPOSE) down

# 再起動
restart:
	$(COMPOSE) down
	$(COMPOSE) up -d

# 強力なクリーンアップ
clean:
	$(COMPOSE) down --volumes --rmi all --remove-orphans
	docker builder prune -f
	@echo "完全クリーンアップ完了"

# ログの表示
logs:
	$(COMPOSE) logs -f

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
