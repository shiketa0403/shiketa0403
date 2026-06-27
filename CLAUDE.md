# 運用ルール

## WordPress投稿
- WordPress投稿は **GitHub Actions経由** で行う（この環境から直接 garage-xxx.jp に接続できない）
- `csv/post.csv` をpush → `wp_post.yml` が自動実行される（投稿対象はこの1ファイルのみ）
- 手動実行も可能（GitHub Actions の workflow_dispatch）
- 投稿先サイト: https://www.garage-xxx.jp
- 認証情報は GitHub Secrets に保存済み（WP_USERNAME, WP_APP_PASSWORD）

## ワークフロー
- `.github/workflows/wp_post.yml` — `csv/post.csv` を WordPress に投稿（スクリーンショット自動取得・挿入含む）
- `.github/workflows/wp_screenshot.yml` — スクリーンショット単体取得（手動実行用）
- `.github/workflows/wp_admin.yml` — 管理操作（カテゴリ一覧・削除、記事一覧・削除）

## 記事作成の流れ
1. `csv/vc_raw_utf8.csv`（バリューコマース案件一覧）から案件情報を取得
2. Google検索で案件のASP掲載状況（◯✕）を調査
3. `generate_article_v2.py` で新構成の記事HTMLを生成
4. **`csv/post.csv` をヘッダー行＋新規記事のみにリセットして出力**（フォーマット: title,content,status,category,tags,slug,screenshot_url）
5. commit & push → GitHub Actions が WordPress に投稿（デフォルト: 下書き）

※ スクリーンショットは今後の記事では不要。`csv/post.csv` の `screenshot_url` 列は常に空にする（`write_post_csv` が自動で空にする）。

## 主要ファイル
- `csv/vc_raw_utf8.csv` — バリューコマース案件一覧（データソース）
- `csv/post.csv` — 投稿用CSV（このファイルのみ投稿対象）
- `generate_article_v2.py` — 新構成の記事生成スクリプト（ASP個別セクション対応）
- `asp_data.py` — 5社分のASP固定データ（バナー・テーブル・ショートコード）
- `wp_post.py` — WordPress REST API操作スクリプト
- `wp_bulk_post.py` — CSV投稿スクリプト
- `screenshot.py` — Playwright によるスクリーンショット取得 & WordPress メディアアップロード
- `ai_generator.py` — Claude APIによるジャンル判定・紹介文・スラッグ生成

## 注意事項
- この環境のネットワークはプロキシ制限があり、garage-xxx.jp への直接接続は不可
- 記事の投稿・確認・削除はすべて GitHub Actions 経由で実行すること
- **csv/post.csv は毎回リセット**: 記事作成時は `csv/post.csv` を必ずヘッダー行＋今回投稿する記事のみにする。過去の記事を残すと重複投稿される
- **重複投稿防止**: `wp_bulk_post.py` は投稿前にWordPressの既存記事タイトルを確認し、同じタイトルの記事が存在する場合は自動でスキップする
- **カテゴリは空にする**: `csv/post.csv` の `category` 列は空文字にすること。WordPress側のデフォルトカテゴリ（ASP）が自動適用される。存在しないカテゴリ名を指定すると投稿がスキップされる
- **screenshot_url列は空にする**: 今後の記事ではスクリーンショットは挿入しない。`csv/post.csv` の `screenshot_url` 列は常に空にする（`write_post_csv` が自動で空にするため通常は意識不要）

---

## 記事生成テンプレート（v2）

`generate_article_v2.py` が自動生成する。手動で記事を組み立てる場合も以下の構成に従う。

### 必要な案件情報

| 変数 | 説明 | vc_raw_utf8.csvの列 |
|---|---|---|
| `{{案件名}}` | サービス名（プログラム名から抽出） | プログラム名 → 案件名抽出ルール適用 |
| `{{運営会社}}` | 会社名 | 会社名 |
| `{{公式サイトURL}}` | 広告主のURL | 広告主サイトURL |
| `{{公式サイト表示名}}` | リンクテキスト | 広告主名 |
| `{{ジャンル}}` | 物販 or 登録 | AI判定 or 手動指定 |
| `{{報酬単価}}` | 報酬額 | 定額報酬 / 定率報酬 |
| `{{成果条件}}` | 成果発生の条件 | 注文発生対象・条件 |
| `{{承認基準}}` | 承認の基準 | 成果の承認基準 |
| `{{ASP掲載状況}}` | 各ASPの◯✕ | Google検索で調査 |

### 案件名抽出ルール
`{{案件名}}` はCSVの「プログラム名」からサービス名（ブランド名）だけを抽出して使う。広告コピーやキャンペーン文言はすべて除去する。

**抽出手順（上から順に適用）:**
1. 【】内があればその中身を使う（例: `【フレッツ光】安心と信頼の…` → `フレッツ光`）
2. `｜`（全角）や `|`（半角）以降を切り捨て
3. 以下の広告用語を除去: キャンペーン、キャッシュバック、WEB申込、お申し込み、プロモーション、公式、プログラム
4. 前後の全角・半角スペースをトリム

### タイトル
```
{{案件名}}のアフィリエイトはどこのASP？
```

### 記事構成（v2）

```
1. リード文（掲載ASPのみをアフィリエイトリンク付きで並べる）
   {{案件名}}は<span class="st-mymarker-s">{ASP1リンク}・{ASP2リンク}…</span>・{末尾ASPリンク}でアフィリエイトできます。
   - 表示するのは広告掲載中のASPのみ（asp_status が True のもの）
   - st-mymarker-s は末尾ASP以外を囲む（末尾ASPは枠外）
   - 各ASPは ASP_LEAD_LINKS のアフィリエイトリンクを使う
2. <h2>{{案件名}}のアフィリエイト情報</h2>
   案件情報テーブル（案件名・運営会社・公式サイト・ジャンル・報酬単価・成果条件・承認基準）
   説明文（10文前後、案件固有の訴求）
3. [st_af id="..."]（末尾、◯のASPのうち末尾のショートコード）
```

※ 削除済みの旧要素: 「ASP◯✕比較テーブル（5社）」「<h2>{{案件名}}を扱えるASP一覧</h2>」（各ASPのH3セクション）、スクリーンショット。

### ASP掲載状況の調査方法
`"{案件名} アフィリエイト ASP 提携"` でGoogle検索し、検索結果のスニペットから◯✕を判定する。
スクリプト実行時は `--asp-status` オプションでJSONを渡す:
```
python generate_article_v2.py --name "LINEMO" --slug "linemo" \
  --asp-status '{"a8":false,"valuecommerce":true,"accesstrade":true,"afb":false,"moshimo":false}'
```

---

## スクリーンショットルール
- **今後の記事では使用しない**: スクリーンショットは挿入しない。`csv/post.csv` の `screenshot_url` 列は常に空にする
- 仕組み自体（GitHub Actions の自動取得・挿入）は残してあるが、`write_post_csv` が `screenshot_url` を常に空で出力するため発動しない

---

## 説明文の生成ルール

### ASP説明文（各H3内、4文）
- 案件名×ASPの組み合わせでユニークに生成
- ASP固有の特徴（振込手数料無料、W報酬など）を案件と絡めて書く
- 報酬単価情報があれば含める

### 案件説明文（H2「アフィリエイト情報」内、10文前後）
- 案件固有の訴求文。以下の要素を含む:
  - 運営会社とサービスの説明
  - 報酬単価と成果条件
  - 注目ポイント（キャンペーン、保証、送料無料など）
  - ターゲット層
  - おすすめのメディアジャンル
  - 承認基準の特徴
- 事実ベースで書く（数字の捏造禁止）

### 文体ルール
- ですます調、1文は70字以内
- 断定すべきところは断定する
- 「〜かもしれません」の連発禁止
- 数字の捏造・公式情報以外のキャンペーン記載禁止

### スラッグ生成
タイトルからサービス名を抽出し、英小文字+ハイフン（1〜3単語）
