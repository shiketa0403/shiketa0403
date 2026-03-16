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

## 記事テンプレート構成
記事HTMLは `convert_vc_csv.py` の `build_article_html()` でテンプレートから生成する。手動でCSVを作る場合も同じ構成に従うこと。

### 構成（上から順）
1. **冒頭文** — `{案件名}は<span class="st-mymarker-s">バリューコマース</span>でアフィリエイトできます。`
2. **ASP5社比較テーブル** — A8net / バリューコマース / アクセストレード / afb / もしもアフィリエイト（バリューコマースのみ◯、他は✕）
3. **H2: {案件名}をアフィリエイトできるASP**
   - H3: バリューコマース詳細情報テーブル（サービス開始年、運営会社、審査、案件数など18項目）
   - おすすめな人リスト（`[st-minihukidashi]`ショートコード使用）
   - バリューコマース紹介文（静的テキスト）
   - CTAボタン `[st_af id="2784"]`
4. **H2: {案件名}のアフィリエイト情報**
   - 案件情報テーブル（案件名、運営会社、公式サイト、ジャンル、報酬単価、成果条件、確定率、CVR、EPC、承認基準）
   - 案件説明文（AI生成 or プログラム内容から引用）
   - CTAボタン `[st_af id="2784"]`

### タイトル形式
- `{プログラム名}のアフィリエイトはどこのASP？`

## 装飾ルール
記事内で使用するCSS装飾クラス：

| 装飾 | HTML | 用途 | 使用数 |
|---|---|---|---|
| 太字＋黄色下線 | `<span class="st-mymarker-s">テキスト</span>` | 最重要ポイント | 全体で1箇所 |
| 太赤字 | `<span class="hutoaka">テキスト</span>` | 補足的な強調 | 全体で1〜2箇所 |

- 上記以外のHTMLタグ（装飾目的）は使わない
- テーブル内のスタイルは既存テンプレートに従う

## AI生成ルール（ai_generator.py）
- **モデル**: Claude Haiku (`claude-haiku-4-5-20251001`)
- **ジャンル判定**: 案件情報から「物販」or「登録」を自動判定
- **紹介文生成**: 3パート構成（サービスの魅力 → アフィリエイトの魅力 → 訴求のコツ）
  - 「です・ます」調
  - 500文字程度
  - 箇条書きは使わず自然な文章
  - 誇大表現・断定は避け事実ベース
  - `st-mymarker-s`（1箇所）と `hutoaka`（1〜2箇所）の装飾を含める
  - 必ず文章を最後まで書ききり、途中で切れないようにする（。で終わること）
  - 最後は「バリューコマースで提携できます」で締める
- **スラッグ生成**: タイトルからサービス名を抽出し、英小文字+ハイフン（1〜3単語）

## バリューコマースCSV変換ルール（convert_vc_csv.py）
- 同一広告主の複数プログラムは **1記事にまとめる**（例外: `SEPARATE_ADVERTISERS` に定義された広告主は個別記事）
- 個別記事にする広告主: ABLENET, IIJmio, ふるさと納税「ふるなび」, タウンライフ土地活用
- `--ai` フラグでClaude APIによるジャンル判定・紹介文・スラッグの自動生成が有効になる

## 注意事項
- この環境のネットワークはプロキシ制限があり、civichat.jp への直接接続は不可
- 記事の投稿・確認・削除はすべて GitHub Actions 経由で実行すること
