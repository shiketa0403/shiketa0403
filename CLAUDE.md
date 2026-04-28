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
2. テンプレートに案件情報を埋め込み、AI生成ルールに従って7見出し構成の本文を作成
3. **`csv/post.csv` をヘッダー行＋新規記事のみにリセットして出力**（フォーマット: title,content,status,category,tags,slug,screenshot_url）
4. commit & push → GitHub Actions が自動で スクリーンショット取得・挿入 → WordPress に投稿（デフォルト: 下書き）

## 主要ファイル
- `csv/vc_raw_utf8.csv` — バリューコマース案件一覧（データソース）
- `csv/post.csv` — 投稿用CSV（このファイルのみ投稿対象）
- `wp_post.py` — WordPress REST API操作スクリプト
- `wp_bulk_post.py` — CSV投稿スクリプト
- `convert_vc_csv.py` — バリューコマースCSV → 記事CSV変換
- `screenshot.py` — Playwright によるスクリーンショット取得 & WordPress メディアアップロード
- `ai_generator.py` — Claude APIによるジャンル判定・紹介文・スラッグ生成

## 注意事項
- この環境のネットワークはプロキシ制限があり、garage-xxx.jp への直接接続は不可
- 記事の投稿・確認・削除はすべて GitHub Actions 経由で実行すること
- **csv/post.csv は毎回リセット**: 記事作成時は `csv/post.csv` を必ずヘッダー行＋今回投稿する記事のみにする。過去の記事を残すと重複投稿される
- **重複投稿防止**: `wp_bulk_post.py` は投稿前にWordPressの既存記事タイトルを確認し、同じタイトルの記事が存在する場合は自動でスキップする
- **カテゴリは空にする**: `csv/post.csv` の `category` 列は空文字にすること。WordPress側のデフォルトカテゴリ（ASP）が自動適用される。存在しないカテゴリ名を指定すると投稿がスキップされる
- **screenshot_url列は必須**: `csv/post.csv` には必ず `screenshot_url` 列を含め、案件の公式サイトURL（`広告主サイトURL`）を入れる。GitHub Actionsがスクリーンショットを自動取得し記事に挿入する。スクリーンショット不要の場合は空にする

---

## 記事生成テンプレート

記事を作成する際は、以下のHTMLテンプレートをそのまま使い、`{{変数}}` 部分だけを案件情報に置き換える。
テンプレート外のHTML構造・クラス名・スタイル属性は一切変更しないこと。

### 必要な案件情報（これだけ渡せば記事が作れる）

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
| `{{スクリーンショットURL}}` | 案件サイトのスクリーンショット画像URL | wp_screenshot.yml でアップロード済みのURL（なければ省略） |

### 案件名抽出ルール
`{{案件名}}` はCSVの「プログラム名」からサービス名（ブランド名）だけを抽出して使う。広告コピーやキャンペーン文言はすべて除去する。

**抽出手順（上から順に適用）:**
1. 【】内があればその中身を使う（例: `【フレッツ光】安心と信頼の…` → `フレッツ光`）
2. `｜`（全角）や `|`（半角）以降を切り捨て
3. 以下の広告用語を除去: キャンペーン、キャッシュバック、WEB申込、お申し込み、プロモーション、公式、プログラム
4. 前後の全角・半角スペースをトリム

**変換例:**

| プログラム名（CSV） | 抽出後の案件名 |
|---|---|
| 【フレッツ光】安心と信頼の光回線｜最大79,000円キャッシュバック | フレッツ光 |
| auひかり　WEB申込キャンペーン | auひかり |
| Watepoint ポット型浄水器 | Watepoint ポット型浄水器（変換不要） |

**注意**: 抽出後の案件名が他の既存記事と重複しないか確認すること。同一サービスで複数プログラムがある場合は、代理店名等で区別するか、1つだけ採用する。

### タイトル
```
{{案件名}}のアフィリエイトはどこのASP？
```

### HTMLテンプレート本文

記事は以下の3ブロックで構成する。

**ブロック1: 冒頭 + ASP比較テーブル**（固定テンプレート）

```html
{{案件名}}は<span class="st-mymarker-s">バリューコマース</span>でアフィリエイトできます。
<table style="border-collapse: collapse; width: 100%;">
<tbody>
<tr>
<th style="width: 50%; background-color: #301ef7;"></th>
<th style="width: 50%; background-color: #301ef7;"><strong><span style="color: #ffffff;">広告掲載状況</span></strong></th>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="https://px.a8.net/svt/ejp?a8mat=3BG026+FXXVXU+0K+10A5LT" rel="nofollow noopener"><img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/a8.png" alt="A8net" width="500" height="200" /></a>
<a href="https://px.a8.net/svt/ejp?a8mat=3BG026+FXXVXU+0K+10A5LT" rel="nofollow">https://www.a8.net/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span style="font-size: 7em;">✕</span></td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="//ck.jp.ap.valuecommerce.com/servlet/referral?sid=3548721&amp;amp;pid=892566121" rel="nofollow"><img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/vc.png" alt="バリューコマース" width="500" height="200" /></a>
<a href="//ck.jp.ap.valuecommerce.com/servlet/referral?sid=3548721&amp;pid=892566121" rel="nofollow"><img src="//ad.jp.ap.valuecommerce.com/servlet/gifbanner?sid=3548721&amp;pid=892566121" width="1" height="1" border="0" />https://www.valuecommerce.ne.jp/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span class="hutoaka"><span style="font-size: 7em;">◯</span></span></td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="https://h.accesstrade.net/sp/cc?rk=0100nldw00kolw" rel="nofollow"><img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/acces.png" alt="アクセストレード" width="500" height="200" /></a>
<a href="https://h.accesstrade.net/sp/cc?rk=0100nldw00kolw" rel="nofollow">https://www.accesstrade.ne.jp/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span style="font-size: 7em;">✕</span></td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="https://www.afi-b.com/" rel="nofollow"><img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/afb.png" alt="afb" width="500" height="200" /></a>
<a href="https://www.afi-b.com/" rel="nofollow">https://www.afi-b.com/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span style="font-size: 7em;">✕</span></td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="//af.moshimo.com/af/c/click?a_id=4207547&amp;p_id=1&amp;pc_id=1&amp;pl_id=82635" rel="nofollow"><img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/moshimo.png" alt="もしもアフィリエイト" width="500" height="200" /></a>
<a href="//af.moshimo.com/af/c/click?a_id=4207547&amp;p_id=1&amp;pc_id=1&amp;pl_id=82635" rel="nofollow">https://af.moshimo.com/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span style="font-size: 7em;">✕</span></td>
</tr>
</tbody>
</table>
```

**ブロック2: 案件情報テーブル**（固定テンプレート + 変数埋め込み）

```html
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
```

**ブロック3: AI生成コンテンツ（7見出し）+ ショートコード**

AI生成ルールに従って7つのH2見出し＋本文を生成し、最後に `[st_af id="2784"]` を1箇所のみ配置する。
詳細は「AI生成ルール」セクションを参照。
```

---

## スクリーンショットルール
- **自動取得**: `csv/post.csv` の `screenshot_url` 列に対象サイトURLを指定 → `wp_post.yml` が投稿前に自動でスクリーンショット取得・WPメディアアップロード・記事HTMLに挿入
- **手動取得**: `wp_screenshot.yml` で個別に取得することも可能（workflow_dispatch）
- **挿入箇所**: `<h2>{{案件名}}のアフィリエイト情報</h2>` の直後、テーブルの前
- **代替テキスト（alt）**: 案件名で統一する（例: `alt="マネーフォワードME"`）
- **スクリーンショット不要の場合**: `screenshot_url` 列を空にすればスキップされる
- **取得失敗時**（サイトのボット対策でブロック等）: スクリーンショットなしで記事を投稿する（imgタグなし）
- ファイルサイズ 20KB 未満は自動でスキップされる（ブロック判定）
- テンプレートで `{{#スクリーンショットURL}}...{{/スクリーンショットURL}}` はスクリーンショットがある場合のみ出力し、ない場合は丸ごと省略する

## 装飾ルール

### インライン装飾

| 装飾 | HTML | 用途 | 使用数 |
|---|---|---|---|
| 太字＋黄色下線 | `<span class="st-mymarker-s">テキスト</span>` | 重要ポイント | 各H2見出しに1〜2箇所 |
| 太赤字 | `<span class="hutoaka">テキスト</span>` | 補足的な強調 | 各H2見出しに1〜2箇所 |

- 冒頭の1文 `{{案件名}}は<span class="st-mymarker-s">バリューコマース</span>でアフィリエイトできます。` は固定（装飾カウントに含めない）
- テーブル内のスタイルは既存テンプレートのものをそのまま使う（変更禁止）

### ボックス装飾
各H2見出しに必ず1つ、以下のどちらかを配置する。

**チェックボックス（黄色系）** — ポジティブな強調・おすすめポイント
```html
[st-cmemo myclass="st-text-guide st-text-guide-point" webicon="st-svg-check" iconcolor="#FF8F00" bgcolor="#FFF8E1" color="#000000" bordercolor="#FFE082" borderwidth="" iconsize="150"]ここに文章

[/st-cmemo]
```

**メモボックス（グレー系）** — 補足情報・まとめ
```html
[st-cmemo myclass="st-text-guide st-text-guide-memo" webicon="st-svg-pencil" iconcolor="#919191" bgcolor="#fafafa" color="#000000" bordercolor="" borderwidth="" iconsize=""]ここに文章

[/st-cmemo]
```

**ボックスのルール:**
- ボックス内の文章は **1段落のみ**（句読点「。」が来たらそこで終了、以降は書かない）
- インライン装飾（st-mymarker-s, hutoaka）とボックスは **併用しない**（同じ文にボックスと装飾を重ねない）
- チェックボックスとメモボックスは見出しの内容に応じて使い分ける

### ショートコード
- `[st_af id="2784"]` は **記事末尾に1箇所のみ** 配置する（まとめ見出しの最後）

---

## AI生成ルール（7見出し構成の本文作成）

ブロック2（案件情報テーブル）の後に、以下の7つのH2見出し＋本文をAI生成する。
全体で2000〜3000字、各見出し300〜400字を厳守。

### 役割
アフィリエイト初心者を集客する案件紹介の専門ライター。
読者は「アフィリエイトを始めたばかりの人」。
記事のゴールは、読者に「この案件は扱うべきだ」と感じさせ、バリューコマース登録に進ませること。
中立的な分析ではなく、案件の魅力を伝えて行動を促す訴求記事を書く。

### 7見出し構成

**見出し1: `<h2>{{案件名}}とは｜信頼できる運営会社が手がけるサービス</h2>`**
- 運営会社の規模・知名度・信頼性を強調
- サービスの基本情報
- 「読者に安心して紹介できる案件である」という方向性で書く

**見出し2: `<h2>{{案件名}}のアフィリエイト報酬は稼ぎやすい理由がある</h2>`**
- 報酬単価の魅力（3,000円以上=高単価、1,000〜3,000=中単価、1,000以下=低単価）
- 成果条件の妥当性（稼ぎやすさの観点で語る）
- 確定率・CVR・EPCのうち「不明」でないものがあればポジティブに使う。「不明」の項目には一切触れない
- 単価が低めでも「成果条件が緩いので数を稼げる」などポジティブ材料を必ず探す

**見出し3: `<h2>{{案件名}}を選ぶべき3つの理由</h2>`**
- 強み3つを **H3見出し＋解説** で記述（番号は付けない）
- サービスの特徴を「読者にとってのメリット」として翻訳
- 競合との差別化・紹介しやすさ・成約しやすさ

**見出し4: `<h2>{{案件名}}が刺さる読者層｜こんな人に紹介すれば成約する</h2>`**
- ターゲット読者像を具体的に描写
- **H3見出し** でペルソナを1〜2個提示（番号は付けない）
- 年齢層・生活スタイル・悩み・乗り換え動機

**見出し5: `<h2>{{案件名}}で稼ぐためのおすすめ訴求パターン3選</h2>`**
- すぐ真似できる勝ちパターンを3つ提示
- 各パターンは **H3見出し** + **`<ul><li>`リスト** で記述
- リストのフォーマット:
```html
<h3>パターン名</h3>
<ul>
 	<li>ターゲット
：具体的なターゲット</li>
 	<li>キーワード
：「キーワード1」
：「キーワード2」</li>
 	<li>切り口
：訴求の切り口</li>
 	<li>記事タイトル例
：「タイトル例」</li>
 	<li>キモ
：訴求の核心</li>
</ul>
```

**見出し6: `<h2>{{案件名}}を扱うなら今がチャンス</h2>`**
- 案件を扱う緊急性・優位性を訴える
- 競合の少なさ、市場の成長性、参入しやすさなど
- 推測で書かない、公式情報ベース

**見出し7: `<h2>まとめ｜{{案件名}}はバリューコマースで提携しよう</h2>`**
- 案件の魅力を1〜2行で再確認
- バリューコマースで提携できる事実を強調
- 行動のハードルを下げる文言（「登録は無料」など）
- **最後の一文は必ず**: `{{案件名}}はバリューコマースで提携できます。`
- この見出しの最後に `[st_af id="2784"]` を配置

### 訴求の温度感

**やること:**
- 案件のメリットを言い切る
- 数字があれば「これだけ稼げる可能性がある」と解釈する
- 読者の行動を後押しする言葉を使う
- 「初心者でも書ける」「成約しやすい」をポジティブに繰り返す

**やらないこと:**
- 中立的なメリット・デメリット比較
- 案件の弱点・リスクの強調
- 「〜かもしれません」「〜と思われます」の連発
- 数字の捏造・公式情報以外のキャンペーン記載
- 「不明」データへの言及

### 文体ルール
- ですます調
- 1文は70字以内
- 断定すべきところは断定する
- 見出し冒頭で「{{案件名}}は〜」を繰り返し使わない
- 同じ表現・接続詞・文末の繰り返しを避ける
- **句読点（。）の後は必ず空行を挿入する**
- 箇条書きは見出しごとに1〜2回まで（見出し5のリストは除く）

### スラッグ生成
タイトルからサービス名を抽出し、英小文字+ハイフン（1〜3単語）
