# 運用ルール

## WordPress投稿
- WordPress投稿は **GitHub Actions経由** で行う（この環境から直接 civichat.jp に接続できない）
- `csv/post.csv` をpush → `wp_post.yml` が自動実行される（投稿対象はこの1ファイルのみ）
- 手動実行も可能（GitHub Actions の workflow_dispatch）
- 投稿先サイト: https://civichat.jp
- 認証情報は GitHub Secrets に保存済み（WP_USERNAME, WP_APP_PASSWORD）

## ワークフロー
- `.github/workflows/wp_post.yml` — `csv/post.csv` を WordPress に投稿
- `.github/workflows/wp_admin.yml` — 管理操作（カテゴリ一覧・削除、記事一覧・削除）

## 記事作成の流れ
1. `csv/vc_raw_utf8.csv`（バリューコマース案件一覧）から案件情報を取得
2. テンプレートに案件情報を埋め込み、AI生成ルールに従って説明文を作成
3. `csv/post.csv` に出力（フォーマット: title,content,status,category,tags,slug）
4. commit & push → GitHub Actions が自動で WordPress に投稿（デフォルト: 下書き）

## 主要ファイル
- `csv/vc_raw_utf8.csv` — バリューコマース案件一覧（データソース）
- `csv/post.csv` — 投稿用CSV（このファイルのみ投稿対象）
- `wp_post.py` — WordPress REST API操作スクリプト
- `wp_bulk_post.py` — CSV投稿スクリプト
- `convert_vc_csv.py` — バリューコマースCSV → 記事CSV変換
- `ai_generator.py` — Claude APIによるジャンル判定・紹介文・スラッグ生成

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
  - 句読点（。）の後に空行を挿入して段落を分ける
- **装飾の使用**:
  - `<span class="st-mymarker-s">テキスト</span>` — 最重要ポイントに1箇所のみ
  - `<span class="hutoaka">テキスト</span>` — 補足的な強調に1〜2箇所
  - 上記以外のHTMLタグは使わない
- **スラッグ生成**: タイトルからサービス名を抽出し、英小文字+ハイフン（1〜3単語）
