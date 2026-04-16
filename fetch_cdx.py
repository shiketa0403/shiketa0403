#!/usr/bin/env python3
"""
Step 1: Wayback CDX API で skyperfectv.co.jp の過去アーカイブURL一覧を取得する。

年ごとに分割して CDX API を叩き、HTML かつ statuscode 200 のスナップショットを
(timestamp, original) のペアで取得して ./cdx_data/cdx_{year}.json に保存する。

- 既に cdx_{year}.json がある年はスキップ(再実行可能)
- リクエスト間に 2 秒 sleep(レート制限対策)
- タイムアウト/一時エラーは指数バックオフで最大 4 回リトライ

使い方:
    python fetch_cdx.py
    python fetch_cdx.py --domain skyperfectv.co.jp --from 2005 --to 2015
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests


CDX_API = "https://web.archive.org/cdx/search/cdx"
DEFAULT_DOMAIN = "skyperfectv.co.jp"
DEFAULT_FROM_YEAR = 2005
DEFAULT_TO_YEAR = 2015
DEFAULT_RESULTS_DIR = Path("./results")  # 下に {domain}/cdx_data/ を作る

SLEEP_BETWEEN_REQUESTS = 2.0  # 秒
REQUEST_TIMEOUT = 120  # CDX は重いことがあるので長め
MAX_RETRIES = 4
USER_AGENT = "Mozilla/5.0 (wayback-dead-links-extractor; +https://example.invalid)"


def build_cdx_params(domain: str, year: int) -> list[tuple[str, str]]:
    """CDX API のクエリパラメータを構築する。

    filter は複数指定したいので、requests の params は list[tuple] 形式で渡す
    (同じキーを2回書くために必要)。
    """
    return [
        ("url", f"{domain}/*"),
        ("output", "json"),
        ("fl", "timestamp,original"),
        ("filter", "statuscode:200"),
        ("filter", "mimetype:text/html"),
        ("collapse", "urlkey"),
        ("from", f"{year}0101000000"),
        ("to", f"{year}1231235959"),
    ]


def fetch_cdx_for_year(
    domain: str,
    year: int,
    session: requests.Session,
) -> list[list[str]] | None:
    """指定年の CDX データを取得する。

    成功時は CDX の生 JSON(ヘッダ行を含む 2次元配列)を返す。
    失敗時は None。
    """
    params = build_cdx_params(domain, year)
    backoff = 2.0

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  [attempt {attempt}/{MAX_RETRIES}] GET CDX API (year={year})")
            resp = session.get(CDX_API, params=params, timeout=REQUEST_TIMEOUT)

            # レート制限っぽいステータス
            if resp.status_code in (429, 503, 504):
                print(f"    → HTTP {resp.status_code} (rate limited?) retry in {backoff:.0f}s")
                time.sleep(backoff)
                backoff *= 2
                continue

            if resp.status_code != 200:
                print(f"    → HTTP {resp.status_code}: {resp.text[:200]}")
                return None

            text = resp.text.strip()
            if not text:
                # 該当なし(空レスポンス)
                return []

            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                print(f"    → JSONデコード失敗: {e} / head={text[:200]!r}")
                time.sleep(backoff)
                backoff *= 2
                continue

            if not isinstance(data, list):
                print(f"    → 想定外のレスポンス型: {type(data).__name__}")
                return None

            return data

        except (requests.Timeout, requests.ConnectionError) as e:
            print(f"    → ネットワークエラー: {e} / retry in {backoff:.0f}s")
            time.sleep(backoff)
            backoff *= 2
        except requests.RequestException as e:
            print(f"    → リクエスト失敗: {e}")
            return None

    print(f"  !! {MAX_RETRIES} 回リトライしても取得できませんでした (year={year})")
    return None


def save_cdx_json(
    data: list[list[str]],
    output_path: Path,
    domain: str,
    year: int,
) -> int:
    """CDX の生データを整形して JSON 保存する。
    レコード数(ヘッダを除く)を返す。
    """
    # data[0] はヘッダ行 ["timestamp", "original"]
    if len(data) == 0:
        header: list[str] = []
        records: list[dict[str, str]] = []
    else:
        header = data[0]
        records = [dict(zip(header, row)) for row in data[1:]]

    payload = {
        "domain": domain,
        "year": year,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "header": header,
        "count": len(records),
        "records": records,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # アトミックに書くために tmp → rename
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, output_path)

    return len(records)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wayback CDX API で過去アーカイブURL一覧を年ごとに取得する"
    )
    parser.add_argument(
        "--domain",
        default=DEFAULT_DOMAIN,
        help=f"対象ドメイン (default: {DEFAULT_DOMAIN})",
    )
    parser.add_argument(
        "--from",
        dest="from_year",
        type=int,
        default=DEFAULT_FROM_YEAR,
        help=f"取得開始年 (default: {DEFAULT_FROM_YEAR})",
    )
    parser.add_argument(
        "--to",
        dest="to_year",
        type=int,
        default=DEFAULT_TO_YEAR,
        help=f"取得終了年 (default: {DEFAULT_TO_YEAR})",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help=f"結果ルートディレクトリ (default: {DEFAULT_RESULTS_DIR}). "
             f"下に {{domain}}/cdx_data/ を作る",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="CDX 出力先 (上書き指定。未指定なら results-dir/{domain}/cdx_data)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存ファイルがあっても上書き取得する",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.from_year > args.to_year:
        print(f"エラー: --from ({args.from_year}) > --to ({args.to_year})", file=sys.stderr)
        return 2

    domain = re.sub(r"^https?://", "", args.domain.strip()).rstrip("/")
    if args.output_dir is None:
        output_dir: Path = args.results_dir / domain / "cdx_data"
    else:
        output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    years = list(range(args.from_year, args.to_year + 1))
    print("=" * 60)
    print(f"対象ドメイン : {domain}")
    print(f"対象年       : {years[0]}〜{years[-1]} ({len(years)}年分)")
    print(f"出力先       : {output_dir.resolve()}")
    print(f"force上書き  : {args.force}")
    print("=" * 60)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    total_records = 0
    total_fetched_years = 0
    total_skipped_years = 0
    total_failed_years = 0

    for i, year in enumerate(years, start=1):
        output_path = output_dir / f"cdx_{year}.json"
        print(f"\n[{i}/{len(years)}] year={year} → {output_path}")

        if output_path.exists() and not args.force:
            # 既存ファイルの件数も表示しておくと親切
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                existing_count = existing.get("count", "?")
            except Exception:
                existing_count = "?"
            print(f"  → 既に存在するのでスキップ (count={existing_count})")
            total_skipped_years += 1
            continue

        data = fetch_cdx_for_year(domain, year, session)
        if data is None:
            print(f"  → 取得失敗")
            total_failed_years += 1
            # 失敗時もレート制限のため sleep してから次へ
            time.sleep(SLEEP_BETWEEN_REQUESTS)
            continue

        count = save_cdx_json(data, output_path, domain, year)
        total_records += count
        total_fetched_years += 1
        print(f"  → 保存完了: {count} 件")

        # 最後の年の後は sleep しない
        if i < len(years):
            time.sleep(SLEEP_BETWEEN_REQUESTS)

    print("\n" + "=" * 60)
    print("Step 1 完了")
    print(f"  取得成功年 : {total_fetched_years}")
    print(f"  スキップ年 : {total_skipped_years}")
    print(f"  失敗年     : {total_failed_years}")
    print(f"  新規レコード数合計: {total_records}")
    print("=" * 60)

    return 0 if total_failed_years == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
