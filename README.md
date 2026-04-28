# WordPress 自動投稿ツール (garage-xxx.jp)

WordPress REST API を使った記事の自動投稿・管理ツール。

## セットアップ

1. `wp_config.py.example` を `wp_config.py` にコピー
2. WordPress のユーザー名・アプリケーションパスワードを設定

```bash
cp wp_config.py.example wp_config.py
# wp_config.py を編集して認証情報を入力
```

## 使い方

### 単体操作 (wp_post.py)

```bash
# 記事を投稿（下書き）
python wp_post.py post --title "記事タイトル" --content "<p>本文</p>"

# 記事を投稿（公開）
python wp_post.py post --title "記事タイトル" --content "<p>本文</p>" --status publish

# カテゴリ指定で投稿（カテゴリIDを指定）
python wp_post.py post --title "記事タイトル" --content "<p>本文</p>" --status publish --categories 1 5

# 記事一覧
python wp_post.py list

# 記事更新
python wp_post.py update --id 123 --title "新タイトル"

# 記事削除
python wp_post.py delete --id 123

# カテゴリ一覧 / 作成
python wp_post.py list-categories
python wp_post.py create-category --name "新カテゴリ"

# タグ一覧 / 作成
python wp_post.py list-tags
python wp_post.py create-tag --name "新タグ"
```

### CSV一括投稿 (wp_bulk_post.py)

```bash
# CSVの内容確認（投稿しない）
python wp_bulk_post.py csv/articles.csv --dry-run

# 下書きで一括投稿
python wp_bulk_post.py csv/articles.csv

# 公開で一括投稿
python wp_bulk_post.py csv/articles.csv --status publish

# 投稿間隔を3秒に設定
python wp_bulk_post.py csv/articles.csv --status publish --delay 3
```

### CSVフォーマット

| カラム | 必須 | 説明 |
|--------|------|------|
| title | ○ | 記事タイトル |
| content | ○ | 本文（HTML可） |
| status | - | draft/publish/pending/private（デフォルト: draft） |
| category | - | カテゴリ名（自動作成） |
| tags | - | タグ名（カンマ区切り、自動作成） |

## ファイル構成

```
├── wp_config.py.example  # 設定ファイルのテンプレート
├── wp_config.py          # 認証情報（※gitignore対象）
├── wp_post.py            # 単体記事操作
├── wp_bulk_post.py       # CSV一括投稿
└── csv/                  # CSVファイル置き場
    └── sample.csv        # サンプルCSV
```
