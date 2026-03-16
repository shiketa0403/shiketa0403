# 運用ルール

## WordPress投稿
- WordPress投稿は **GitHub Actions経由** で行う（この環境から直接 civichat.jp に接続できない）
- `csv/post_*.csv` を **mainブランチ** にpush → `wp_post.yml` が自動実行される
- 手動実行も可能（GitHub Actions の workflow_dispatch）
- 投稿先サイト: https://civichat.jp
- 認証情報は GitHub Secrets に保存済み（WP_USERNAME, WP_APP_PASSWORD, ANTHROPIC_API_KEY）

## ワークフロー
- `.github/workflows/wp_post.yml` — 記事投稿（CSV投稿 / AI変換投稿）
- `.github/workflows/wp_admin.yml` — 管理操作（カテゴリ一覧・削除、記事一覧・削除）

## 記事作成の流れ
1. `csv/post_<名前>.csv` を作成（フォーマット: title,content,status,category,tags,slug）
2. mainブランチにcommit & push
3. GitHub Actionsが自動で WordPress に投稿（デフォルト: 下書き）

## 主要ファイル
- `wp_post.py` — WordPress REST API操作スクリプト
- `wp_bulk_post.py` — CSV一括投稿スクリプト
- `wp_config.py` — ローカル用設定（GitHub Actionsでは Secrets から自動生成）
- `convert_vc_csv.py` — バリューコマースCSV → 記事CSV変換（AI生成対応）

## 注意事項
- この環境のネットワークはプロキシ制限があり、civichat.jp への直接接続は不可
- 記事の投稿・確認・削除はすべて GitHub Actions 経由で実行すること
