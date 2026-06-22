#!/usr/bin/env python3
"""
中古ドメイン DR 一括チェックツール（Ahrefs API v3 / batch-analysis）

ドメインリストを Ahrefs の batch-analysis エンドポイントに投げて DR（Domain Rating）を
一括取得し、しきい値以下のドメインを除外する。

- Standard プランは「1リクエスト25行」「60リクエスト/分」「150,000 units/月・追加購入不可」。
  → 既定で 25 件ずつ・1.1 秒間隔で投げる。
- DR のみ取得すれば 1 行あたり 1 unit 程度。8000 件で概算 24,000 units（150,000 の約16%）。
- 実際の消費はレスポンスヘッダ（x-api-units-cost-* 等）で確認できる。
  本番前に --test で 1 件だけ投げ、生レスポンスと消費 units を確認すること。

使い方:
  # 1件だけ投げて生レスポンス・消費unitsを確認（本番前に必ず）
  AHREFS_API_KEY=xxxx python ahrefs_dr.py csv/domains.txt --test

  # 本番（DR2以下を除外、DR3以上だけ csv/ahrefs_dr_passed.csv に残す）
  AHREFS_API_KEY=xxxx python ahrefs_dr.py csv/domains.txt
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API_URL = "https://api.ahrefs.com/v3/batch-analysis/batch-analysis"

# Standard プランの制限に合わせた既定値
DEFAULT_CHUNK = 25          # 1リクエストあたりのドメイン数（Standard は25行上限）
DEFAULT_INTERVAL = 1.1      # リクエスト間隔（秒）。60req/min を超えないように
DEFAULT_EXCLUDE_MAX = 2     # この DR 以下を除外（既定: DR2以下を除外 = DR3以上だけ残す）

# batch-analysis の target 設定
TARGET_MODE = "subdomains"  # ドメイン全体の DR を見る（exact/prefix/domain/subdomains）
TARGET_PROTOCOL = "both"

MAX_RETRY = 4
RETRY_BACKOFF = [2, 4, 8, 16]


# 裸ドメインらしさの判定（ヘッダ行や空セルを自動で弾く）
DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def normalize_domain(raw):
    """URL/前後空白/引用符を落として裸ドメインに正規化（不正なら空文字）。

    日本語ドメイン（IDN, 例: 求人.jp）は punycode（xn--...）に変換する。
    """
    if raw is None:
        return ""
    d = raw.strip().strip('"').strip("'").strip()
    if not d or d.startswith("#"):
        return ""
    d = re.sub(r"^https?://", "", d, flags=re.IGNORECASE).strip()
    d = d.split("/")[0].split("?")[0].strip().rstrip(".").lower()
    if not d or " " in d:
        return ""
    if DOMAIN_RE.match(d):
        return d
    # 非ASCII（日本語ドメイン等）は punycode に変換して再判定
    if any(ord(c) > 127 for c in d) and "." in d:
        try:
            puny = d.encode("idna").decode("ascii")
            if DOMAIN_RE.match(puny):
                return puny
        except (UnicodeError, ValueError):
            return ""
    return ""


def load_domains(input_arg):
    """ファイルまたはカンマ区切り文字列からドメインを読む。

    ファイルは CSV / TXT どちらもOK:
    - CSV（ヘッダ付き・複数列）でも各行の「1列目」を採用
    - 1行1ドメインの TXT もそのまま読める
    - ドメインとして不正な値（ヘッダ名・空欄など）は自動でスキップ
    """
    raw_values = []
    if os.path.isfile(input_arg):
        # 文字コード自動判定: UTF-8(BOM可) → Shift-JIS(cp932) の順で試す
        text = None
        for enc in ("utf-8-sig", "cp932", "euc-jp"):
            try:
                with open(input_arg, "r", encoding=enc, newline="") as f:
                    text = f.read()
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            with open(input_arg, "r", encoding="utf-8", errors="replace", newline="") as f:
                text = f.read()
        for row in csv.reader(text.splitlines()):
            if row:
                raw_values.append(row[0])  # 常に1列目を採用
    else:
        # ファイルでなければカンマ区切り文字列とみなす
        raw_values = input_arg.split(",")

    cleaned = []
    seen = set()
    for raw in raw_values:
        d = normalize_domain(raw)
        if d and d not in seen:
            seen.add(d)
            cleaned.append(d)
    return cleaned


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def call_api(api_key, domains_chunk):
    """1チャンクを batch-analysis に投げ、(rows, headers) を返す。失敗時は例外。"""
    body = {
        "select": ["url", "domain_rating"],
        "targets": [
            {"url": d, "mode": TARGET_MODE, "protocol": TARGET_PROTOCOL}
            for d in domains_chunk
        ],
        "output": "json",
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    last_err = None
    for attempt in range(MAX_RETRY):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                headers = {k.lower(): v for k, v in resp.headers.items()}
                payload = json.loads(raw) if raw.strip() else {}
                return extract_rows(payload), headers, payload
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            last_err = f"HTTP {e.code}: {err_body[:500]}"
            # 429（レート超過）/ 5xx はバックオフして再試行。それ以外は即中断。
            if e.code == 429 or 500 <= e.code < 600:
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                print(f"    リトライ {attempt + 1}/{MAX_RETRY}（{wait}s 待機）: {last_err}")
                time.sleep(wait)
                continue
            raise RuntimeError(last_err)
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = str(e)
            wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
            print(f"    リトライ {attempt + 1}/{MAX_RETRY}（{wait}s 待機）: {last_err}")
            time.sleep(wait)
    raise RuntimeError(f"リトライ上限。最後のエラー: {last_err}")


def extract_rows(payload):
    """レスポンスの形が未確定なので、行リストを防御的に取り出す。"""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        # よくあるキー名を優先的に探す
        for key in ("batch_analysis", "batchAnalysis", "pages", "rows", "data", "results"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
        # それ以外: 最初に見つかった「dictのリスト」を採用
        for v in payload.values():
            if isinstance(v, list) and (not v or isinstance(v[0], dict)):
                return v
    return []


def parse_dr(row):
    """行から domain_rating を取り出す（キー名のゆらぎに対応）"""
    if not isinstance(row, dict):
        return None
    for key in ("domain_rating", "domainRating", "dr"):
        if key in row and row[key] is not None:
            try:
                return float(row[key])
            except (TypeError, ValueError):
                return None
    return None


def parse_url(row):
    if not isinstance(row, dict):
        return ""
    for key in ("url", "target", "domain"):
        if key in row and row[key]:
            return re.sub(r"^https?://", "", str(row[key])).rstrip("/").split("/")[0].lower()
    return ""


def units_from_headers(headers):
    """レスポンスヘッダから今回の消費 units を拾う（ヘッダ名が未確定なので cost を含むものを探す）"""
    for k, v in headers.items():
        if "units" in k and "cost" in k and "total" in k:
            try:
                return int(float(v))
            except ValueError:
                pass
    # フォールバック: units と cost を含む数値ヘッダ
    for k, v in headers.items():
        if "units" in k and "cost" in k:
            try:
                return int(float(v))
            except ValueError:
                pass
    return None


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ドメイン", "DR", "備考"])
        for r in rows:
            w.writerow([r["domain"], r["dr"] if r["dr"] is not None else "", r["note"]])


def run_test(api_key, domains):
    """1件だけ投げて、生レスポンスと消費unitsヘッダを表示（本番前の確認用）"""
    target = domains[0]
    print(f"=== テストモード: {target} を1件だけ投げます ===\n")
    rows, headers, payload = call_api(api_key, [target])
    print("--- レスポンスヘッダ（units 関連のみ）---")
    for k, v in sorted(headers.items()):
        if "units" in k or "rate" in k or "limit" in k:
            print(f"  {k}: {v}")
    print("\n--- 生レスポンス（JSON）---")
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:3000])
    print("\n--- パース結果 ---")
    for row in rows:
        print(f"  url={parse_url(row)!r}  DR={parse_dr(row)}")
    cost = units_from_headers(headers)
    print(f"\n今回の消費 units: {cost if cost is not None else '不明（ヘッダ未検出）'}")
    if cost:
        print(f"概算: {len(domains)}件を25件/リクエストで処理 → "
              f"約 { (len(domains)+24)//25 * cost } units（1チャンク={cost}u 想定）")
    print("\nヘッダ/レスポンス構造を確認したら --test を外して本番実行してください。")


def main():
    ap = argparse.ArgumentParser(description="中古ドメイン DR 一括チェック（Ahrefs API v3）")
    ap.add_argument("input", help="ドメインリストファイル（1行1ドメイン）またはカンマ区切り")
    ap.add_argument("-o", "--output", default="ahrefs_dr.csv", help="全結果CSV")
    ap.add_argument("--passed-output", default="ahrefs_dr_passed.csv",
                    help="しきい値を通過したドメインのCSV")
    ap.add_argument("--exclude-max", type=int, default=DEFAULT_EXCLUDE_MAX,
                    help="この DR 以下を除外（既定2 = DR2以下を除外しDR3以上を残す）")
    ap.add_argument("--chunk", type=int, default=DEFAULT_CHUNK, help="1リクエストのドメイン数")
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="リクエスト間隔(秒)")
    ap.add_argument("--test", action="store_true", help="1件だけ投げて生レスポンス・消費unitsを確認")
    args = ap.parse_args()

    api_key = os.environ.get("AHREFS_API_KEY") or os.environ.get("AHREFS_API_TOKEN")
    if not api_key:
        print("ERROR: 環境変数 AHREFS_API_KEY（または AHREFS_API_TOKEN）が未設定です。")
        sys.exit(1)

    domains = load_domains(args.input)
    if not domains:
        print("ERROR: ドメインが1件もありません。")
        sys.exit(1)

    print(f"調査対象: {len(domains)} ドメイン")

    if args.test:
        run_test(api_key, domains)
        return

    num_chunks = (len(domains) + args.chunk - 1) // args.chunk
    print(f"チャンク数: {num_chunks}（{args.chunk}件/リクエスト, {args.interval}s間隔）")
    print(f"除外条件: DR {args.exclude_max} 以下を除外（DR {args.exclude_max + 1} 以上を通過）\n")

    results = []          # {domain, dr, note}
    total_units = 0
    by_domain = {d: {"domain": d, "dr": None, "note": "未取得"} for d in domains}

    for ci, chunk in enumerate(chunked(domains, args.chunk), 1):
        print(f"[チャンク {ci}/{num_chunks}] {len(chunk)}件")
        try:
            rows, headers, _ = call_api(api_key, chunk)
        except Exception as e:
            print(f"  失敗: {e}")
            for d in chunk:
                by_domain[d]["note"] = "API失敗"
            # 途中結果を保存して次へ
            write_csv(args.output, list(by_domain.values()))
            time.sleep(args.interval)
            continue

        cost = units_from_headers(headers)
        if cost:
            total_units += cost

        # url で突き合わせ。取れない場合は順序で対応づけ。
        matched_by_url = {parse_url(r): r for r in rows if parse_url(r)}
        for idx, d in enumerate(chunk):
            row = matched_by_url.get(d)
            if row is None and idx < len(rows):
                row = rows[idx]
            dr = parse_dr(row) if row is not None else None
            by_domain[d]["dr"] = dr
            by_domain[d]["note"] = "" if dr is not None else "DR取得失敗"

        write_csv(args.output, list(by_domain.values()))
        print(f"  累計消費 units: {total_units if total_units else '不明'}")

        if ci < num_chunks:
            time.sleep(args.interval)

    results = list(by_domain.values())
    write_csv(args.output, results)

    # しきい値で絞り込み（DR が exclude_max より大きいものだけ通過）
    passed = [r for r in results if r["dr"] is not None and r["dr"] > args.exclude_max]
    passed.sort(key=lambda r: r["dr"], reverse=True)
    write_csv(args.passed_output, passed)

    # サマリ
    got = [r for r in results if r["dr"] is not None]
    failed = [r for r in results if r["dr"] is None]
    print(f"\n{'='*60}")
    print(f"完了: {len(results)}件中 DR取得 {len(got)}件 / 失敗 {len(failed)}件")
    print(f"通過（DR>{args.exclude_max}）: {len(passed)}件 → {args.passed_output}")
    print(f"全結果: {args.output}")
    print(f"合計消費 units: {total_units if total_units else '不明（ヘッダ未検出）'}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
