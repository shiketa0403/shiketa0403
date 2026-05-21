# 運用ルール

## WordPress投稿
- WordPress投稿は **GitHub Actions経由** で行う（この環境から直接 civichat.jp に接続できない）
- `csv/post.csv` をpush → `wp_post.yml` が自動実行される（投稿対象はこの1ファイルのみ）
- 手動実行も可能（GitHub Actions の workflow_dispatch）
- 投稿先サイト: https://civichat.jp
- 認証情報は GitHub Secrets に保存済み（WP_USERNAME, WP_APP_PASSWORD）

## ワークフロー
- `.github/workflows/wp_post.yml` — `csv/post.csv` を WordPress に投稿（civichat.jp 向け）
- `.github/workflows/wp_admin.yml` — 管理操作（カテゴリ一覧・削除、記事一覧・削除）
- `.github/workflows/sharebatake_article.yml` — シェア畑（sharebatake.com）を区/市単位でスクレイピング → 1記事生成 → agriwarriors.jp に draft 投稿（手動実行）

## 記事作成の流れ
1. `csv/vc_raw_utf8.csv`（バリューコマース案件一覧）から案件情報を取得
2. テンプレートに案件情報を埋め込み、AI生成ルールに従って説明文を作成
3. `csv/post.csv` に出力（フォーマット: title,content,status,category,tags,slug）
4. commit & push → GitHub Actions が自動で WordPress に投稿（デフォルト: 下書き）

## 主要ファイル
- `csv/vc_raw_utf8.csv` — バリューコマース案件一覧（データソース）
- `csv/post.csv` — 投稿用CSV（このファイルのみ投稿対象、civichat.jp向け）
- `wp_post.py` — WordPress REST API操作スクリプト（`wp_config.py` を読む）
- `wp_bulk_post.py` — CSV投稿スクリプト
- `convert_vc_csv.py` — バリューコマースCSV → 記事CSV変換
- `ai_generator.py` — Claude APIによるジャンル判定・紹介文・スラッグ生成
- `sharebatake_scraper.py` — シェア畑の区/市ページを Playwright で取得 → Farm dataclass のリスト化（スクショ含む）
- `sharebatake_ai.py` — Claude API ラッパー。農園説明文 / 自治体情報（Web Search 利用）
- `sharebatake_article.py` — 区/市1件 → スクレイピング → AI生成 → テンプレ組立 → agriwarriors.jp に draft 投稿

## 注意事項
- この環境のネットワークはプロキシ制限があり、civichat.jp への直接接続は不可
- 記事の投稿・確認・削除はすべて GitHub Actions 経由で実行すること

---

## 記事生成テンプレート

記事を作成する際は、以下のHTMLテンプレートをそのまま使い、`{{変数}}` 部分だけを案件情報に置き換える。
テンプレート外のHTML構造・クラス名・スタイル属性は一切変更しないこと。

### 必要な案件情報（これだけ渡せば記事が作れる）

| 変数 | 説明 | vc_raw_utf8.csvの列 |
|---|---|---|
| `{{案件名}}` | プログラム名 | プログラム名 |
| `{{運営会社}}` | 会社名 | 会社名 |
| `{{公式サイトURL}}` | 広告主のURL | 広告主サイトURL |
| `{{公式サイト表示名}}` | リンクテキスト | 広告主名 |
| `{{ジャンル}}` | 物販 or 登録 | AI判定 or 手動指定 |
| `{{報酬単価}}` | 報酬額 | 定額報酬 / 定率報酬 |
| `{{成果条件}}` | 成果発生の条件 | 注文発生対象・条件 |
| `{{承認基準}}` | 承認の基準 | 成果の承認基準 |
| `{{説明文}}` | AI生成の案件紹介文 | （AI生成ルールで作成） |
| `{{スクリーンショットURL}}` | 案件サイトのスクリーンショット画像URL | wp_screenshot.yml でアップロード済みのURL（なければ省略） |

### タイトル
```
{{案件名}}のアフィリエイトはどこのASP？
```

### HTMLテンプレート本文

```html
{{案件名}}は<span class="st-mymarker-s">バリューコマース</span>でアフィリエイトできます。
<table style="border-collapse: collapse; width: 100%;">
<tbody>
<tr>
<th style="width: 50%; background-color: #301ef7;"></th>
<th style="width: 50%; background-color: #301ef7;"><strong><span style="color: #ffffff;">広告掲載状況</span></strong></th>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="https://px.a8.net/svt/ejp?a8mat=3BG026+FXXVXU+0K+10A5LT" rel="nofollow noopener"><img class="alignnone size-full" src="https://www.civichat.jp/wp-content/uploads/2026/03/a8.png" alt="A8net" width="500" height="200" /></a>
<a href="https://px.a8.net/svt/ejp?a8mat=3BG026+FXXVXU+0K+10A5LT" rel="nofollow">https://www.a8.net/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span style="font-size: 7em;">✕</span></td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="//ck.jp.ap.valuecommerce.com/servlet/referral?sid=3548721&amp;amp;pid=892566121" rel="nofollow"><img class="alignnone size-full" src="https://www.civichat.jp/wp-content/uploads/2026/03/vc.png" alt="バリューコマース" width="500" height="200" /></a>
<a href="//ck.jp.ap.valuecommerce.com/servlet/referral?sid=3548721&amp;pid=892566121" rel="nofollow"><img src="//ad.jp.ap.valuecommerce.com/servlet/gifbanner?sid=3548721&amp;pid=892566121" width="1" height="1" border="0" />https://www.valuecommerce.ne.jp/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span class="hutoaka"><span style="font-size: 7em;">◯</span></span></td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="https://h.accesstrade.net/sp/cc?rk=0100nldw00kolw" rel="nofollow"><img class="alignnone size-full" src="https://www.civichat.jp/wp-content/uploads/2026/03/acces.png" alt="アクセストレード" width="500" height="200" /></a>
<a href="https://h.accesstrade.net/sp/cc?rk=0100nldw00kolw" rel="nofollow">https://www.accesstrade.ne.jp/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span style="font-size: 7em;">✕</span></td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="https://www.afi-b.com/" rel="nofollow"><img class="alignnone size-full" src="https://www.civichat.jp/wp-content/uploads/2026/03/afb.png" alt="afb" width="500" height="200" /></a>
<a href="https://www.afi-b.com/" rel="nofollow">https://www.afi-b.com/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span style="font-size: 7em;">✕</span></td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="//af.moshimo.com/af/c/click?a_id=4207547&amp;p_id=1&amp;pc_id=1&amp;pl_id=82635" rel="nofollow"><img class="alignnone size-full" src="https://www.civichat.jp/wp-content/uploads/2026/03/moshimo.png" alt="もしもアフィリエイト" width="500" height="200" /></a>
<a href="//af.moshimo.com/af/c/click?a_id=4207547&amp;p_id=1&amp;pc_id=1&amp;pl_id=82635" rel="nofollow">https://af.moshimo.com/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span style="font-size: 7em;">✕</span></td>
</tr>
</tbody>
</table>

<h2>{{案件名}}をアフィリエイトできるASP</h2>
<h3>バリューコマース</h3>
<img class="alignnone size-full" src="https://www.civichat.jp/wp-content/uploads/2026/03/スクリーンショット-2026-03-15-182118.png" alt="バリューコマース" width="951" height="535" />
<table style="border-collapse: collapse; width: 100%;">
<tbody>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">サービス開始年</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">1999年（日本初のASP）</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">運営会社</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">バリューコマース株式会社（LINEヤフーグループ）</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">サイト審査</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">あり（記事数目安：7〜10記事程度）</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">SNS・サイトなしで登録</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">✕（サイト必要）</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">初心者向けサポート</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">◯</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">案件総数</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">大規模（累計広告主6,500社以上）</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">得意ジャンル</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">Yahoo!ショッピング・大手EC・金融・旅行</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">Amazon・楽天案件</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">〇</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">独自案件の豊富さ</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">◎（大手企業の独占案件多数）</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">最低支払額</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">500円</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">振込手数料</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">無料</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">特別報酬制度</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">会員ランク制度（ゴールド・シルバー・ブロンズ・一般）</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">高単価案件</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">〇</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">管理画面の使いやすさ</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">◎</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">専任担当者</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">〇</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">薬機法チェック機能</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">×</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">おまかせ広告機能</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">◎（コンテンツに合わせ自動で最適広告を配信）</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">会員数</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">85万サイト以上登録</td>
</tr>
<tr>
<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><span style="color: #ffffff;">満足度実績</span></th>
<td style="width: 50%; text-align: center; vertical-align: middle;">日本最古のASPとしての老舗ブランド力</td>
</tr>
</tbody>
</table>
[st-minihukidashi webicon="" fontsize="" fontweight="" bgcolor="#FFB74D" color="#fff" margin="0 0 20px 0" radius="" position="" myclass="" add_boxstyle=""]おすすめな人
<div class="st-square-checkbox st-square-checkbox-nobox">
<ul>
 	<li>Yahoo!ショッピングのアフィリエイトを扱いたい人</li>
 	<li>大手企業・有名ブランドの信頼性の高い案件を紹介したい人</li>
 	<li>広告の貼り替えの手間を省いて効率よく運用したい人</li>
</ul>
</div>
[/st-minihukidashi]
日本初のASPとして1999年に誕生した、<span class="hutoaka">信頼と実績のあるサービス</span>です。

Yahoo!ショッピングのアフィリエイトを扱えるのはバリューコマースだけ。

大手企業・有名ECサイトの案件が充実しているので、「信頼できるブランドの商品を紹介したい」という方に特に向いています。

コンテンツに合わせて広告を自動表示してくれる<span class="st-mymarker-s">「おまかせ広告」機能も便利</span>です。

また、会員ランク制度があり、成果を積み上げるほど特典や報酬条件が有利になっていく仕組みも魅力のひとつです。
[st_af id="2784"]

<h2>{{案件名}}のアフィリエイト情報</h2>
{{#スクリーンショットURL}}<img class="alignnone size-full" src="{{スクリーンショットURL}}" alt="{{案件名}}" width="1280" height="800" />{{/スクリーンショットURL}}
<table style="border-collapse: collapse; width: 100%;">
<tbody>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><strong><span style="color: #ffffff;">案件名</span></strong></td>
<td style="width: 50%; text-align: center; vertical-align: middle;">{{案件名}}</td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><strong><span style="color: #ffffff;">運営会社</span></strong></td>
<td style="width: 50%; text-align: center; vertical-align: middle;">{{運営会社}}</td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><strong><span style="color: #ffffff;">公式サイト</span></strong></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="{{公式サイトURL}}" target="_blank" rel="noopener">{{公式サイト表示名}}</a></td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><strong><span style="color: #ffffff;">ジャンル</span></strong></td>
<td style="width: 50%; text-align: center; vertical-align: middle;">{{ジャンル}}</td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><strong><span style="color: #ffffff;">報酬単価</span></strong></td>
<td style="width: 50%; text-align: center; vertical-align: middle;">{{報酬単価}}</td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><strong><span style="color: #ffffff;">成果条件</span></strong></td>
<td style="width: 50%; text-align: center; vertical-align: middle;">{{成果条件}}</td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><strong><span style="color: #ffffff;">確定率</span></strong></td>
<td style="width: 50%; text-align: center; vertical-align: middle;">不明</td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><strong><span style="color: #ffffff;">CVR</span></strong></td>
<td style="width: 50%; text-align: center; vertical-align: middle;">不明</td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><strong><span style="color: #ffffff;">EPC</span></strong></td>
<td style="width: 50%; text-align: center; vertical-align: middle;">不明</td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"><strong><span style="color: #ffffff;">承認基準</span></strong></td>
<td style="width: 50%; text-align: center; vertical-align: middle;">{{承認基準}}</td>
</tr>
</tbody>
</table>
{{説明文}}
[st_af id="2784"]
```

---

## スクリーンショットルール
- `wp_screenshot.yml` で案件サイトのスクリーンショットを取得し、WordPressメディアにアップロード
- **挿入箇所**: `<h2>{{案件名}}のアフィリエイト情報</h2>` の直後、テーブルの前
- **代替テキスト（alt）**: 案件名で統一する（例: `alt="マネーフォワードME"`）
- **スクリーンショット取得に失敗した場合**（サイトのボット対策でブロック等）: スクリーンショットなしで記事を作成する（imgタグごと省略）
- ファイルサイズ 20KB 未満は自動でスキップされる（ブロック判定）
- テンプレートで `{{#スクリーンショットURL}}...{{/スクリーンショットURL}}` はスクリーンショットがある場合のみ出力し、ない場合は丸ごと省略する

## 装飾ルール
記事内で使用するCSS装飾クラス：

| 装飾 | HTML | 用途 | 使用数 |
|---|---|---|---|
| 太字＋黄色下線 | `<span class="st-mymarker-s">テキスト</span>` | 最重要ポイント | 全体で1箇所 |
| 太赤字 | `<span class="hutoaka">テキスト</span>` | 補足的な強調 | 全体で1〜2箇所 |

- 上記以外のHTMLタグ（装飾目的）は使わない
- テーブル内のスタイルは既存テンプレートのものをそのまま使う（変更禁止）

## AI生成ルール（説明文の作成）
`{{説明文}}` はAIで生成する。`ai_generator.py` の `generate_description()` で実行、またはこのルールに従って直接生成する。

- **3パート構成**:
  1. サービスの魅力（ユーザー目線）— どんな人の、どんな悩みを解決するか
  2. アフィリエイトの魅力（アフィリエイター目線）— 報酬単価、成果条件、CVRが期待できる理由
  3. 訴求のコツ — ターゲット層と訴求方法、最後は「バリューコマースで提携できます」で締める
- **文体・品質ルール**:
  - 「です・ます」調で統一
  - 500文字程度
  - 1文は40〜60文字程度、読みやすいリズム
  - 箇条書きは使わず自然な文章
  - 誇大表現・「絶対」「必ず」などの断定は避け、事実ベース
  - 必ず文章を最後まで書ききり、途中で切れないようにする（。で終わること）
  - **句読点（。）の後は必ず空行（空の1行）を挿入する**（1文ごとに段落を分ける。文が詰まって読みにくくなるのを防ぐ）
- **装飾の使用**:
  - `<span class="st-mymarker-s">テキスト</span>` — 最重要ポイントに1箇所のみ
  - `<span class="hutoaka">テキスト</span>` — 補足的な強調に1〜2箇所
  - 上記以外のHTMLタグは使わない
- **スラッグ生成**: タイトルからサービス名を抽出し、英小文字+ハイフン（1〜3単語）

---

## シェア畑（sharebatake.com）→ agriwarriors.jp データベース記事

バリューコマースASP記事（civichat.jp）とは完全に別系統。シェア畑のサイトを
**区/市単位**でスクレイピング → 1回の実行で1区/市の記事を1本生成 →
**agriwarriors.jp** に下書き投稿する仕組み。現状は東京都・神奈川県・千葉県・埼玉県・大阪府・兵庫県・京都府に対応。

### 投稿先
- WordPress: https://agriwarriors.jp
- 認証: GitHub Secrets `AGRIWARRIORS_WP_USERNAME` / `AGRIWARRIORS_WP_APP_PASSWORD`
- Claude API: GitHub Secrets `ANTHROPIC_API_KEY`
- ハブ記事: https://agriwarriors.jp/shared-farm/ （事前に作成済み、文末に内部リンク）

### A8 アフィリエイトリンク（CTA）
- href: `https://px.a8.net/svt/ejp?a8mat=3ZFJ8K+ABII9E+3U16+60H7M`
- 計測画像は無し、URLのみ
- アンカーテキスト: `{{農園名}}の見学予約・詳細を見る`

### フロー
1. `.github/workflows/sharebatake_article.yml` を手動実行（`workflow_dispatch`）
   - 入力: `city`（区/市名、例: 大田区）、`status`（既定 draft）、`max_farms`、`dry_run`
2. `sharebatake_scraper.py` が区/市名 → シェア畑のエリアURLを参照、Playwright で一覧→各農園詳細ページを巡回
   - 調布市・狛江市は同じシェア畑ページから住所で分離
   - その他市部は `tokyo_else` ページから住所で分離
3. 各農園のフルスクショを取得（`out_sharebatake/farm_NN_*.png`）
4. WPメディアにアップロードして src URLを取得
5. `sharebatake_ai.py` が各農園200文字説明文（生データ材料）と自治体情報（Web Search）を Claude API で生成
6. テンプレに埋め込んで agriwarriors.jp に draft 投稿（カテゴリは都道府県名（slug は `PREFECTURE_CATEGORY` 参照、東京→「東京」、神奈川→「神奈川」）、タグ「シェア畑,貸し農園,{{区/市名}}」）

### スクレイピング注意
- `sharebatake.com` は Cloudflare 系の Bot 対策あり。`requests`/`curl` だけでは 403。**Playwright 必須**。
- ローカルや一般クラウドからは 403 になりやすい。GitHub Actions 上で実行が安定。
- HTML 構造変更時は `sharebatake_scraper.py` の `.tdL/.tdR` 抽出と `_parse_list_page` の class 名要調整。
- 詳細ページの `lat="..." lng="..."` で緯度経度抽出 → Google Maps 埋め込み（APIキー不要）

### 対象エリア
区/市名 → (都道府県slug, sharebatake slug, WP slug, 住所フィルタ) は `sharebatake_scraper.AREA_MAP` に定義。
- 東京: 11区＋調布市・狛江市＋その他市部（`tokyo_else` を住所で分離）
- 神奈川: 横浜市・川崎市・藤沢市（各市専用ページがある前提）
- 千葉: 千葉市（市専用ページがある前提）
- 埼玉: さいたま市＋その他市部（`saitama_else` を住所で分離。川口市・朝霞市）
- 大阪: `/farms/osaka` 単一ページ（`sb_slug` は空文字）から住所フィルタで分離。吹田市・住吉区・箕面市
- 兵庫: `/farms/hyogo` 単一ページ（`sb_slug` は空文字）から住所フィルタで分離。尼崎市・西宮市
- 京都: `/farms/kyoto` 単一ページ（`sb_slug` は空文字）から住所フィルタで分離。京都市
**注意**: 大田区だけ sharebatake 側が `oota`、WP 側が `ota` で違う。
新たな都道府県を追加するときは `PREFECTURE_CATEGORY` にも WPカテゴリ名を追加し、WordPress 側にカテゴリを事前作成する。

### 記事テンプレート（区/市1件＝1記事）
- タイトル: `【{{区/市名}}】レンタルできる貸し農園まとめ`
- スラッグ: `AREA_MAP` の WP slug（大田区→`ota`、横浜市→`yokohama` 等）
- カテゴリ: 都道府県名（東京→`東京`(slug:`tokyo`)、神奈川→`神奈川`(slug:`kanagawa`)。WP側に事前作成必須・無いと投稿スキップ）
- タグ: `シェア畑, 貸し農園, {{区/市名}}`
- ステータス: draft（既定）
- 構成:
  1. `<h2>{{区/市名}}でレンタルできる貸し農園一覧</h2>`
  2. 農園ごとに `<h3>農園名</h3>` + `<img>`（フルスクショ）+ 2カラムテーブル + Google Map iframe + AI生成200文字説明 + CTAリンク
  3. `<h2>自治体などのレンタル畑情報</h2>` または `<h2>自治体などのレンタル情報なし</h2>`
  4. 文末にハブ記事リンク（アンカー: `シェア畑の口コミ・評判は本当?契約NGの人を200人調査で暴露`）
- 装飾: `<span class="hutoaka">` (太赤字 / 最重要1箇所)、`<span class="st-mymarker-s">` (太字+黄色下線 / 重要1〜2箇所)

### 動作確認
- まず大田区を `dry_run=true` で実行 → ログに HTML 出力されるので確認
- 大田区を `dry_run=false` で実行 → draft 記事が agriwarriors.jp に作成される
- 内容確認後に他エリアへ展開
