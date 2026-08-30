# ブログ記事 全自動作成ワークフロー（ローカルClaude Code用）

ユーザーが「◯◯の記事を作成して」と指示したら、この手順書に従って
**リサーチ → 執筆 → 機械監査 → 装飾 → 画像生成 → WordPress下書き投稿** までを
**人間の承認ゲートなしで一気に実行**する。

途中で「続けて」「OK」等の確認を求めない。判断に迷う点は最も妥当な選択をして
最終レポートに記載する。ユーザーの確認はWordPressの下書きで行われる。

## 前提ファイル

| ファイル | 内容 |
|---|---|
| `wp-article/config/sites.local.json` | 投稿先サイトの認証情報（ユーザーが作成。無ければ投稿フェーズをスキップし、その旨を報告） |
| 案件マスタ（CSV or ユーザーのメッセージ） | キーワード・サービス名・公式URL等。`wp-article/config/master_example.csv` が書式 |
| `wp-article/prompts/01〜12` | 各工程の品質ルール原本。**本書の差分ルールが優先** |

## 全工程共通の差分ルール（原本プロンプトより優先）

1. **承認ゲート全廃** — 原本にある「フェーズ1で提示→OK待ち」「1回の出力につきH2一つ→続けて待ち」は全て無視し、最後まで実行する
2. **出力はチャットではなくファイル** — アーティファクト（textarea+コピーボタン）仕様は廃止。生HTMLを `out/<slug>/` 配下に保存する
3. **日付表記の全面禁止** — 「◯年◯月時点」「◯月確認」「2026年現在」等を本文・alt・図解・スクショのどこにも出さない。確認日は facts.json 内部にのみ記録
4. **数値は事実シートからのみ** — 本文・図解に書く数字（料金・期間・件数・%等）は必ず facts.json に出典付きで存在するものを使う。検索の記憶やスニペットから直接書かない
5. **1セクション=1生成** — 本文はH2ごとに独立して生成する（長文一括生成による品質劣化を防ぐ）。
6. アフィリエイト関連（`st_af`・バナー・アフィリンク）は案件マスタに値がある場合のみ出力。無ければ該当ブロックごと省略（質問しない）
7. **タグは自動生成しない** — 案件マスタの tags 列に明示された場合のみ設定。空なら記事にタグを付けない（カテゴリは従来通り）

## 実行手順

作業ディレクトリ: `wp-article/out/<slug>/`（以下 `out/` と表記）。
初回のみ環境確認: `python -m playwright --version` が失敗したら
`pip install playwright requests` と `python -m playwright install chromium` を実行する。

### Phase 0: 入力の確定
案件マスタから site_key / keyword / article_type(商標・一般) / service_name / official_url /
media_info / slug / category / tags / アフィリエイト各項目 を読み取る。
slugが未指定ならキーワードから英小文字ハイフンで生成（例: kuma-doll）。
`out/meta.json` に保存する。

### Phase 1: リサーチ＋事実シート（prompts/01 + 12のSearch Protocol）
WebSearch / WebFetch を使い次を実施:
1. ターゲットKWでSERPs上位10件の傾向把握（prompts/01 Step0）
2. 口コミ実調査 — 知恵袋・5ch・ブログ等で実在の投稿を確認。見つからなければ「確認できなかった」と記録。**創作禁止**（prompts/01 Step0.5、prompts/04 実調査ルール）
3. 公式サイトの一次情報収集 — 料金・会社概要・特商法表記・条件等の**該当ページを直接開いて**数値を抽出
4. すべての事実を `out/facts.json` に記録:
```json
{"facts": [{"id": "F1", "claim": "料金帯は10〜70万円", "value": "10〜70万円",
  "source_url": "https://...", "source_kind": "公式/公的/口コミ/他メディア",
  "checked_date": "YYYY-MM-DD", "usable_as_link": true}]}
```
   - usable_as_link は prompts/08 のホワイトリスト（公的機関・公式のみtrue）
5. prompts/01 のOutput Format（検索者像〜独自性の切り口）を `out/persona.md` に保存

### Phase 2: 構成（prompts/02 + 03を連続適用）
prompts/02 で構成案を作り、**同一生成内で** prompts/03 の監査ルール（KW配置・階層・数値一致・
粒度・1見出し1概念）を自己適用して修正後の完成構成のみを `out/outline.md` に保存。
タイトル（32文字前後・KW左寄せ）とCTA位置 [CTA] も確定する。meta.json にタイトルを反映。

**ボリューム基準（必須）**: 本文は合計 **9,000〜12,000文字**（タグ・ショートコード除く）、
H2は**7本以上**を基本とする。リサーチで得た事実が足りない場合のみ縮めてよいが、
その理由を最終レポートに書く。

**商標（口コミ・評判）記事の標準カバレッジ**: 以下の観点は、事実が確認できる限り
それぞれ独立したH2として立てる。5本構成で済ませない。
1. 結論・総合評価（口コミ全体傾向）
2. 信頼性・詐欺でない根拠の検証（法人確認・拠点・届出・正規許可）
3. 良い口コミ・強み（4項目前後）
4. 悪い口コミ・デメリット（3〜4項目、正直に）
5. プライバシー・配送・受け取りの工夫（該当ジャンルの場合）
6. 競合・代替サービスとの比較（3〜4社、表付き）
7. 向いている人・向いていない人
8. よくある質問（3問前後）
9. まとめ

### Phase 3: 本文執筆（prompts/04 + 05を統合、H2ごと）
各H2セクションを**1つずつ独立に**生成し `out/sections/h2-1.html` … に保存する。
prompts/04（PRE構造・語尾ルール・冗長/断定回避表現の禁止・文量目安・トランジション）と
prompts/05（1文50字以内・1段落句点3つまで・句点後空行・体言止め配置・語尾連続禁止・
HTMLはh2/h3/ul/ol/aのみ・pタグ/brタグ禁止）を**最初からまとめて適用**する。
数値は facts.json のみ。デメリット最低1箇所。

### Phase 4: 機械監査＋自動修正（prompts/06の自動化）
```
python wp-article/scripts/validate_article.py out/<slug> --stage text
```
エラー（P0/P1）が出たセクションのみ修正 → 再実行。最大3周。
残った警告は最終レポートに記載する。

### Phase 5: 装飾（prompts/07）
セクションごとに装飾を適用し `out/sections_deco/h2-N.html` に保存。
色装飾3種のみ・H3単位の配置ルール・ふきだしルール・AFFINGERショートコード・
装飾なし3段落連続の禁止・CTA前後の装飾禁止・同種装飾3連禁止を厳守。
本文の文言・数字・順序は一切変更しない。

### Phase 6: 外部発リンク（prompts/08）
facts.json で usable_as_link=true のURLのみ使用。トップページではなく具体ページ。
同一サイト1記事1回まで。アフィリエイトのみ rel="nofollow"、その他はrel属性なし
（prompts/07 のrelルール）。アンカーに「こちら」禁止。

### Phase 7: リード文＋ピックアップボックス（prompts/09 + 10）
リード文（250〜400字・黄マーカー1箇所・句点ごと空行）とまとめボックスを生成。
アフィリエイト明示ブロック（prompts/07 の 7-1）をリード直後に配置。
バナー・st_af はマスタに値がある場合のみ。`out/lead.html` に保存。

### Phase 8: 図解＋アイキャッチ（prompts/11）
0. フォント確認: `wp-article/templates/fonts/` が空なら
   `python wp-article/scripts/fetch_fonts.py` を実行
1. **見本を最低1つReadする**（`wp-article/templates/examples/`）。
   記事全体のビジュアルテーマを決める（prompts/11「自由デザイン方式」＋「デザイン品質基準」参照）
2. 図解ごとに `out/diagrams/dNN.html` を自由デザインで作成し、
   `out/diagrams.json` を作成（type: "custom" 基本。アイキャッチ+図解4枚以上、
   CTA直前に後押し図解、YMYLルール適用、数値はfacts.jsonと一致、日付なし）。
   diagram_fonts.css の読み込みと品質基準6項目（装飾で埋める・絵文字はチップに乗せる・
   文字の立体感・影・小物・アイキャッチの密度）を必ず満たす
3. ```
   python wp-article/scripts/render_diagram.py out/<slug>
   ```
4. **目視セルフチェック（必須）**: 生成された `out/images/*.png` を1枚ずつReadで開き、
   **見本PNGと並べて見劣りしないか**を判定する。チェック観点: 余白が寂しくないか・
   絵文字が裸で浮いていないか・文字のはみ出し・不自然な改行・コントラスト・
   フォントが適用されているか（游ゴシック素のままはNG）。
   見劣りする画像はHTMLを修正して再レンダリング（最大2周）

### Phase 9: エビデンススクショ（prompts/12）
facts.json から `out/shots.json` を作成（自動撮影3〜8枚+manual_shots）。
```
python wp-article/scripts/evidence_shots.py out/<slug>
```
ブロック等で取得失敗したものは自動的にスキップされ `shots_result.json` に記録される。
連番はエビデンス01〜、図解はその続き（アイキャッチは00）だが、
撮影スキップが出ても図解のファイル名は変更しなくてよい（欠番許容）。

### Phase 10: 組立
`out/final.html` を次の順で組み立てる:
1. リード文 → ピックアップボックス → アフィリエイト明示 →（バナー/st_af: あれば）
2. 各H2セクション（装飾済み）。図解は該当H2見出しの直下、エビデンスは指定位置に
   `{{IMG:ファイル名}}` プレースホルダで挿入
3. 画像マニフェスト `out/images.json` を作成:
```json
{"eyecatch": "kuma-doll-00-eyecatch.png",
 "images": [{"file": "...", "alt": "...", "width": 1200, "height": 900}]}
```
4. 仕上げ監査: `python wp-article/scripts/validate_article.py out/<slug> --stage final`
   → エラーがあれば修正して再実行（最大2周）

画像配置ルール: 1つのH2にエビデンス+図解合計3枚以上を集中させない。
アイキャッチは本文に挿入しない（featured image専用）。

### Phase 11: WordPress下書き投稿
```
python wp-article/scripts/wp_publish.py out/<slug> --site <site_key> --status draft
```
- 画像を全てメディアにアップ → `{{IMG:...}}` を `<img class="alignnone size-full wp-image-{id}" src="{url}" alt="{alt}" width="{w}" height="{h}" />` に置換
- アイキャッチを featured image に設定
- タイトル・スラッグ・カテゴリ・タグ付きで下書き投稿
- sites.local.json が無い/認証失敗の場合は final.html までで停止し、その旨を報告

### 最終レポート（チャットに出力）
- 下書きURL（投稿できた場合）
- 記事文字数 / 図解枚数 / エビデンス枚数（スキップ含む）
- manual_shots（手動撮影が必要なもの）
- 機械監査で残った警告
- facts.json で「要確認」扱いにした事実

## 複数記事の連続実行
マスタCSVに複数行ある場合は1行ずつ上記を完走させる。
1記事の失敗で全体を止めず、失敗行はレポートにまとめる。
