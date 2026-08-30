# ブログ記事 自動作成パイプライン

キーワードと案件情報を渡すと、リサーチ → 1万字級の本文執筆 → 機械監査 → AFFINGER装飾 →
図解・アイキャッチ生成 → エビデンススクショ → WordPress下書き投稿 までを
ローカルのClaude Codeセッションが無人で実行する仕組み。

## 初回セットアップ（1回だけ）

ローカルPC（Windows）のPowerShellで:

```powershell
cd $HOME\Documents\shiketa0403
pip install playwright requests
python -m playwright install chromium
python wp-article\scripts\fetch_fonts.py
```

最後の行は図解用の日本語フォント（丸ゴシック・極太ゴシック・明朝）のダウンロードです。

認証情報ファイルを作成:

1. `wp-article/config/sites.example.json` を同じフォルダに `sites.local.json` という名前でコピー
2. サイトのURL・WordPressユーザー名・アプリケーションパスワードを記入
   （アプリケーションパスワード: WordPress管理画面 → ユーザー → プロフィール → アプリケーションパスワード）
3. このファイルはgitignore対象。GitHubにはアップロードされない

## 使い方

ローカルのClaude Codeセッション（作業フォルダ: このリポジトリ）で指示するだけ:

```
KUMADOLLのテスト記事を作成して。
キーワード: KUMADOLL 口コミ
公式URL: https://kumadoll.jp/
投稿先: lovedoll
```

複数記事は `wp-article/config/master_example.csv` の書式でCSVを渡す。
Claudeが `wp-article/WORKFLOW.md` に従って全工程を実行し、
最後にWordPressの下書きURLを報告する。**公開は必ず人間が下書きを確認してから**。

## 構成

| パス | 役割 |
|---|---|
| `WORKFLOW.md` | 実行手順書（Claudeが従う本体） |
| `prompts/01〜10` | 記事品質ルールの原本（ペルソナ〜ピックアップボックス） |
| `prompts/11` | 図解・アイキャッチ仕様（diagrams.json の書式） |
| `prompts/12` | エビデンススクショ仕様（shots.json の書式） |
| `scripts/validate_article.py` | 機械監査（禁止語・語尾・文長・装飾密度・日付表記・数値の出典確認） |
| `scripts/render_diagram.py` | 図解PNG生成（Playwright） |
| `scripts/evidence_shots.py` | 公式サイト等の自動スクショ |
| `scripts/wp_publish.py` | 画像アップ＋アイキャッチ設定＋下書き投稿（マルチサイト） |
| `templates/diagram_template.html` | 図解デザインテンプレ（配色・レイアウトはここを編集） |
| `config/sites.example.json` | 投稿先設定のひな形 |
| `config/master_example.csv` | 案件マスタのひな形 |
| `out/<slug>/` | 記事ごとの生成物（gitignore対象） |

## 図解デザインの調整

配色・フォント・レイアウトは `templates/diagram_template.html` の `:root` のCSS変数と
各セクションのスタイルで一元管理している。テスト記事を見て
「ヘッダーの色を◯◯に」「文字をもっと大きく」等をClaudeに指示すれば反映される。

## 運用ルール

- 投稿は常に draft。公開ボタンは人間が押す
- 記事中の数値はすべて `out/<slug>/facts.json`（出典付き事実シート）由来。
  リライト時はfacts.jsonの確認日を見て古い事実から再調査する
- 日付表記（「◯月時点」等）は記事・画像に一切入れない
- アフィリエイトリンク・`st_af` は案件マスタに値がある場合のみ挿入される
