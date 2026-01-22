# 変数定義
COMPOSE = docker-compose

.PHONY: help up build down restart clean logs ps

# デフォルトのターゲット（helpを表示）
help:
	@echo "使用可能なコマンド:"
	@echo "  make up      - コンテナをバックグラウンドで起動します"
	@echo "  make build   - キャッシュを使用せずにイメージをビルドします"
	@echo "  make down    - コンテナとネットワークを停止・削除します"
	@echo "  make restart - コンテナを再起動します"
	@echo "  make clean   - コンテナ、ボリューム、プロジェクト関連イメージ、ビルドキャッシュを完全に削除します"
	@echo "  make logs    - コンテナのログをリアルタイムで表示します"
	@echo "  make ps      - コンテナの稼働状態を表示します"

# コンテナの起動
up:
	$(COMPOSE) up -d

# イメージのビルド（確実を期すため --no-cache を付与）
build:
	$(COMPOSE) build --no-cache

# コンテナの停止と削除
down:
	$(COMPOSE) down

# 再起動
restart:
	$(COMPOSE) down
	$(COMPOSE) up -d

# 強力なクリーンアップ
# --volumes: 名前付きボリュームも削除
# --rmi all: プロジェクトで使用されているすべてのイメージを削除
# --remove-orphans: 定義外のコンテナも削除
# docker builder prune: ビルドキャッシュを削除
clean:
	$(COMPOSE) down --volumes --rmi all --remove-orphans
	docker builder prune -f
	@echo "プロジェクトのキャッシュ、イメージ、ボリュームを完全に削除しました。"

# ログの表示
logs:
	$(COMPOSE) logs -f

# ステータス確認
ps:
	$(COMPOSE) ps