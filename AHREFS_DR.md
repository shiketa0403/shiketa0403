# 中古ドメイン DR 一括チェック（Ahrefs API v3）

中古ドメイン購入の選別用。Ahrefs の `batch-analysis` エンドポイントでドメインの
DR（Domain Rating）を一括取得し、**DR2以下を除外**（DR3以上だけ残す）する。

`domain_check`（Wayback でタイトル調査）とは独立したツール。お互い干渉しない。

## ファイル構成

| ファイル | 役割 |
|---|---|
| `ahrefs_dr.py` | DR一括チェック本体 |
| `.github/workflows/ahrefs_dr.yml` | GitHub Actions ワークフロー |
| `csv/domains.txt` | 調査対象ドメイン（1行1ドメイン、`#`コメント可。domain_checkと共用可） |
| `csv/ahrefs_dr.csv` | 全結果（ドメイン, DR, 備考）※自動生成・上書き |
| `csv/ahrefs_dr_passed.csv` | DRしきい値を通過したドメイン（DR降順）※自動生成・上書き |

## 事前準備（1回だけ）

GitHub Secret に Ahrefs API キーを登録する:
**Settings → Secrets and variables → Actions → New repository secret**
- Name: `AHREFS_API_KEY`
- Value: Ahrefs管理画面で発行した API トークン

## 使い方

### 1. 本番前に必ずテスト実行（生レスポンス・消費unitsの確認）

Ahrefs API のレスポンス構造・消費 units の実値を確認する。

1. `csv/domains.txt` に対象ドメインを記入してコミット
2. **Actions → Ahrefs DR 一括チェック → Run workflow**
   - `test` を **true** にして実行
3. ログに1件分の生レスポンスと `x-api-units-*` ヘッダが出るので、
   DR が取れていること・1リクエストの消費 units を確認

### 2. 本番実行

1. **Actions → Ahrefs DR 一括チェック → Run workflow**
   - `test` は **false**（既定）
   - `exclude_max` は除外する DR の上限（既定 `2` = DR2以下を除外）
2. 完了後 `csv/ahrefs_dr_passed.csv` に DR3以上のドメインが残る

## Standard プランの制限と消費量

| 項目 | Standard |
|---|---|
| 月間 API units | 150,000（固定・追加購入不可） |
| レート | 60 リクエスト/分 |
| 1リクエスト行数 | 25行（=25ドメイン/リクエスト） |

- スクリプトは既定で **25件/リクエスト・1.1秒間隔** で投げる（制限内）。
- **DRのみ取得**なので 1行あたり約1 unit。
- 8000件の概算: `(8000/25)×50（基本）+ 8000×1 ≈ 24,000 units`（150,000の約16%）。
- 実際の消費はログの「合計消費 units」で確認。月の上限を超えると **翌月リセットまで待つ**しかない（Standardは追加購入不可）。

## CSV出力フォーマット

| 列 | 説明 |
|---|---|
| ドメイン | 調査対象ドメイン |
| DR | Domain Rating（0〜100） |
| 備考 | 空=正常 / `DR取得失敗` / `API失敗` / `未取得` |

## 注意事項

- この環境から api.ahrefs.com への直接接続はプロキシ制限で不可。**必ず GitHub Actions 経由**で実行する。
- レスポンスのキー名・target の `mode`（既定 `subdomains`）は API 仕様変更で要調整。
  まず `--test` で生レスポンスを確認し、`ahrefs_dr.py` の `extract_rows` / `parse_dr` を合わせる。
- `csv/ahrefs_dr*.csv` は実行ごとに上書き（過去結果は git 履歴で確認）。
