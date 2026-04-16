#!/usr/bin/env python3
"""
Step 2: Step 1 で集めた CDX データから、アーカイブ済み HTML を取得して
外部発リンク (source_domain 以外へのリンク) を抽出する。

- 入力 : ./cdx_data/cdx_{year}.json
- 出力 : ./links_data/links_{year}.jsonl
         各行 = {source_url, timestamp, external_domain, anchor_text, href}
- 処理済み URL は ./links_data/processed_{year}.txt に追記し、再実行時スキップ

- URL パスで優先フィルタ (/program/, /channel/, /special/, トップページ等)
- --max-urls で処理件数上限を設定 (デフォルト 300)
- リクエスト間 sleep 1.5 秒
- タイムアウト/レート制限は指数バックオフでリトライ
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


WAYBACK_BASE = "https://web.archive.org/web"
USER_AGENT = "Mozilla/5.0 (wayback-dead-links-extractor; +https://example.invalid)"
SLEEP_BETWEEN_REQUESTS = 1.5
REQUEST_TIMEOUT = 45
MAX_RETRIES = 3
MAX_HTML_BYTES = 500_000  # 取り込み上限 (巨大ページ対策)

# 外部リンクが多そうなパス (優先度高いものが先)。ドメイン非依存の一般パターン
PRIORITY_PATH_PATTERNS = [
    re.compile(r"^https?://[^/]+/?(index\.html?)?$", re.IGNORECASE),  # トップ
    re.compile(r"/article/", re.IGNORECASE),
    re.compile(r"/column/", re.IGNORECASE),
    re.compile(r"/program/", re.IGNORECASE),
    re.compile(r"/channel/", re.IGNORECASE),
    re.compile(r"/special/", re.IGNORECASE),
    re.compile(r"/category/", re.IGNORECASE),
    re.compile(r"/feature/", re.IGNORECASE),
    re.compile(r"/link", re.IGNORECASE),
    re.compile(r"/info/", re.IGNORECASE),
]

# 明らかに不要なパス
SKIP_PATH_PATTERNS = [
    re.compile(r"\.(jpg|jpeg|png|gif|svg|ico|css|js|pdf|zip|swf|mp3|mp4|woff2?|ttf)(\?|$)", re.IGNORECASE),
    re.compile(r"/(images?|img|css|js|assets?|static)/", re.IGNORECASE),
]


def normalize_host(netloc: str) -> str:
    """host を正規化 (小文字化、www. 除去、ポート除去)"""
    host = netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def is_external(href: str, source_domain: str) -> tuple[bool, str]:
    """href が外部リンクかどうか判定し、外部ドメインを返す"""
    try:
        parsed = urlparse(href)
    except ValueError:
        return False, ""

    if parsed.scheme not in ("http", "https"):
        return False, ""

    host = normalize_host(parsed.netloc)
    if not host:
        return False, ""

    src = normalize_host(source_domain)
    if host == src or host.endswith("." + src):
        return False, ""

    # web.archive.org 自身へのリンク (Wayback 内ナビ) は除外
    if host in ("web.archive.org", "archive.org"):
        return False, ""

    return True, host


def priority_score(url: str) -> int:
    """低いほど優先度高い (ソート用)"""
    for i, pat in enumerate(PRIORITY_PATH_PATTERNS):
        if pat.search(url):
            return i
    return len(PRIORITY_PATH_PATTERNS)


def should_skip(url: str) -> bool:
    return any(p.search(url) for p in SKIP_PATH_PATTERNS)


def load_cdx_records(cdx_path: Path) -> list[dict[str, str]]:
    with open(cdx_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("records", [])


def select_urls(
    records: list[dict[str, str]],
    max_urls: int,
) -> list[dict[str, str]]:
    """優先度の高い URL 上位 max_urls 件を返す (URLごと最新 timestamp のみ)"""
    filtered = [r for r in records if not should_skip(r.get("original", ""))]

    # URL(original) ごとに最新 timestamp を1つだけ残す
    latest: dict[str, dict[str, str]] = {}
    for r in filtered:
        orig = r.get("original", "")
        ts = r.get("timestamp", "")
        if orig not in latest or ts > latest[orig].get("timestamp", ""):
            latest[orig] = r
    uniq = list(latest.values())

    uniq.sort(key=lambda r: (priority_score(r.get("original", "")), r.get("original", "")))
    return uniq[:max_urls]


def fetch_wayback_html(
    session: requests.Session,
    timestamp: str,
    original: str,
) -> tuple[str | None, str]:
    """Wayback から raw HTML を取得。(text, note) を返す。取得失敗時 text=None。"""
    wb_url = f"{WAYBACK_BASE}/{timestamp}id_/{original}"
    backoff = 2.0

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(wb_url, timeout=REQUEST_TIMEOUT, stream=True)
            if resp.status_code in (429, 503, 504):
                time.sleep(backoff)
                backoff *= 2
                continue
            if resp.status_code != 200:
                return None, f"HTTP {resp.status_code}"

            # 先頭 MAX_HTML_BYTES だけ読む
            chunk = resp.raw.read(MAX_HTML_BYTES, decode_content=True) or b""
            encoding = resp.encoding or "utf-8"
            try:
                text = chunk.decode(encoding, errors="replace")
            except (LookupError, TypeError):
                text = chunk.decode("utf-8", errors="replace")
            return text, ""
        except (requests.Timeout, requests.ConnectionError):
            time.sleep(backoff)
            backoff *= 2
        except requests.RequestException as e:
            return None, f"error: {e}"
        except Exception as e:
            # urllib3.ProtocolError 等、requests でラップされないエラー対策
            return None, f"error: {e}"

    return None, "retry exhausted"


def extract_external_links(
    html: str,
    source_url: str,
    source_domain: str,
) -> list[dict[str, str]]:
    """HTML から外部リンクを抽出"""
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, str]] = []
    for a in soup.find_all("a", href=True):
        href_raw = a["href"].strip()
        if not href_raw or href_raw.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        # Wayback は id_ 付きで取得してるので書き換えは基本ないが、
        # 相対URLは source_url を基準に絶対化する
        href = urljoin(source_url, href_raw)

        ok, host = is_external(href, source_domain)
        if not ok:
            continue

        anchor = a.get_text(" ", strip=True)[:200]
        out.append({"external_domain": host, "anchor_text": anchor, "href": href})
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 2: アーカイブHTMLから外部リンク抽出")
    parser.add_argument("--year", type=int, required=True, help="対象年 (cdx_{year}.json を読む)")
    parser.add_argument("--source-domain", default="skyperfectv.co.jp", help="ソースドメイン")
    parser.add_argument("--results-dir", type=Path, default=Path("./results"),
                        help="結果ルートディレクトリ。下に {source-domain}/ を掘る")
    parser.add_argument("--cdx-dir", type=Path, default=None,
                        help="CDX 読込先 (未指定なら results-dir/{domain}/cdx_data)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="links 出力先 (未指定なら results-dir/{domain}/links_data)")
    parser.add_argument("--max-urls", type=int, default=300, help="処理URL件数上限 (デフォルト 300)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    domain = re.sub(r"^https?://", "", args.source_domain.strip()).rstrip("/")
    cdx_dir = args.cdx_dir or (args.results_dir / domain / "cdx_data")
    output_dir = args.output_dir or (args.results_dir / domain / "links_data")

    cdx_path = cdx_dir / f"cdx_{args.year}.json"
    if not cdx_path.exists():
        print(f"エラー: {cdx_path} が見つかりません。先に fetch_cdx.py を実行してください", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    links_path = output_dir / f"links_{args.year}.jsonl"
    processed_path = output_dir / f"processed_{args.year}.txt"

    # 既処理 URL 読み込み
    processed: set[str] = set()
    if processed_path.exists():
        processed = set(processed_path.read_text(encoding="utf-8").splitlines())

    print("=" * 60)
    print(f"対象年        : {args.year}")
    print(f"ソースドメイン: {domain}")
    print(f"CDX入力       : {cdx_path}")
    print(f"リンク出力    : {links_path}")
    print(f"最大処理URL数 : {args.max_urls}")
    print(f"既処理済み    : {len(processed)} 件")
    print("=" * 60)

    records = load_cdx_records(cdx_path)
    print(f"CDX レコード数: {len(records)}")
    targets = select_urls(records, args.max_urls)
    print(f"処理対象 (優先フィルタ後): {len(targets)} 件\n")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    total_links = 0
    ok_count = 0
    fail_count = 0
    skipped_count = 0

    # 追記モードで開く (既存 jsonl は残す)
    with open(links_path, "a", encoding="utf-8") as lf, \
         open(processed_path, "a", encoding="utf-8") as pf:

        for i, rec in enumerate(targets, start=1):
            original = rec.get("original", "")
            timestamp = rec.get("timestamp", "")
            key = f"{timestamp} {original}"

            if key in processed:
                skipped_count += 1
                continue

            print(f"[{i}/{len(targets)}] {timestamp} {original}")
            html, note = fetch_wayback_html(session, timestamp, original)

            if html is None:
                print(f"  → 取得失敗: {note}")
                fail_count += 1
                # 失敗時も processed に記録 (無限リトライ回避)
                pf.write(key + "\n")
                pf.flush()
                time.sleep(SLEEP_BETWEEN_REQUESTS)
                continue

            links = extract_external_links(html, original, domain)
            print(f"  → 外部リンク: {len(links)} 件")

            for l in links:
                rec_out = {
                    "source_url": original,
                    "timestamp": timestamp,
                    "external_domain": l["external_domain"],
                    "anchor_text": l["anchor_text"],
                    "href": l["href"],
                }
                lf.write(json.dumps(rec_out, ensure_ascii=False) + "\n")
            lf.flush()

            pf.write(key + "\n")
            pf.flush()

            total_links += len(links)
            ok_count += 1

            if i < len(targets):
                time.sleep(SLEEP_BETWEEN_REQUESTS)

    print("\n" + "=" * 60)
    print("Step 2 完了")
    print(f"  処理成功  : {ok_count}")
    print(f"  取得失敗  : {fail_count}")
    print(f"  スキップ  : {skipped_count} (既処理)")
    print(f"  抽出リンク: {total_links}")
    print(f"  出力      : {links_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
