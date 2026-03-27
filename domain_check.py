#!/usr/bin/env python3
"""
中古ドメイン履歴調査ツール
Wayback Machine CDX API を使い、ドメインの最新タイトルを一括取得する。
"""

import csv
import json
import re
import sys
import time
import argparse
import urllib.request
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser


CDX_API = "https://web.archive.org/cdx/search/cdx"
WAYBACK_URL = "https://web.archive.org/web"
MAX_RETRIES = 2
MAX_WORKERS = 5


class TitleParser(HTMLParser):
    """HTMLから<title>タグの中身を抽出する"""
    def __init__(self):
        super().__init__()
        self._in_title = False
        self._in_script = False
        self._title = ""
        self._has_meta_refresh = False
        self._has_js_redirect = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag == "script":
            self._in_script = True
        if tag == "meta":
            attrs_dict = dict(attrs)
            if attrs_dict.get("http-equiv", "").lower() == "refresh":
                content = attrs_dict.get("content", "")
                if "url=" in content.lower():
                    self._has_meta_refresh = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_title:
            self._title += data
        if self._in_script:
            lower = data.lower()
            if any(p in lower for p in [
                "window.location", "location.href", "location.replace",
                "location.assign", "document.location",
            ]):
                self._has_js_redirect = True

    @property
    def title(self):
        return self._title.strip()

    @property
    def is_redirect(self):
        return self._has_meta_refresh or self._has_js_redirect


PARKING_PATTERNS = [
    "parking", "parked", "for sale", "buy this domain",
    "domain expired", "this domain", "coming soon",
    "under construction", "is available", "domain name",
    "sedoparking", "hugedomains", "godaddy", "afternic",
    "dan.com", "sav.com",
]


def detect_note(title, is_redirect=False):
    """タイトルから備考を判定"""
    if not title:
        return ""
    lower = title.lower()
    for pattern in PARKING_PATTERNS:
        if pattern in lower:
            return "パーキング"
    if is_redirect:
        return "リダイレクト"
    return ""


def fetch_url_bytes(url, timeout=20, max_bytes=30000):
    """URLからバイトデータを取得"""
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (domain-history-checker)"
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read(max_bytes)
                return data, resp.status
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
            else:
                return None, None


def fetch_url(url, timeout=20, max_bytes=30000):
    """URLからテキストを取得"""
    data, status = fetch_url_bytes(url, timeout, max_bytes)
    if data is None:
        return None, None
    return data.decode("utf-8", errors="replace"), status


def decode_html(data):
    """HTMLバイトデータをエンコーディング自動検出でデコード"""
    if data is None:
        return None

    head = data[:2000].decode("ascii", errors="replace").lower()
    charset = None

    m = re.search(r'<meta[^>]+charset=["\']?([a-zA-Z0-9_-]+)', head)
    if m:
        charset = m.group(1)
    if not charset:
        m = re.search(r'content=["\'][^"\']*charset=([a-zA-Z0-9_-]+)', head)
        if m:
            charset = m.group(1)

    if charset:
        try:
            return data.decode(charset)
        except (UnicodeDecodeError, LookupError):
            pass

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    for enc in ["shift_jis", "euc-jp", "iso-2022-jp", "cp932"]:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            pass

    return data.decode("utf-8", errors="replace")


def get_latest_snapshot(domain):
    """CDX APIで最新のスナップショットのタイムスタンプを取得"""
    urls_to_try = [domain, f"http://{domain}", f"https://{domain}"]
    if domain.startswith("http"):
        urls_to_try = [domain]

    for attempt in range(3):
        if attempt > 0:
            wait = attempt * 3
            time.sleep(wait)

        for try_url in urls_to_try:
            # 重複キーはリストで渡す
            params = urllib.parse.urlencode([
                ("url", try_url),
                ("output", "json"),
                ("fl", "timestamp,statuscode"),
                ("filter", "statuscode:200"),
                ("filter", "mimetype:text/html"),
                ("limit", "3"),
                ("sort", "reverse"),
            ])
            url = f"{CDX_API}?{params}"
            body, status = fetch_url(url, timeout=30, max_bytes=100000)

            if not body:
                continue

            try:
                data = json.loads(body)
                if len(data) > 1:
                    return data[1][0]  # 最新のタイムスタンプ
            except (json.JSONDecodeError, ValueError, IndexError):
                continue

    return None


def get_title_from_snapshot(domain, timestamp):
    """Wayback Machineのスナップショットからタイトルを取得"""
    target = domain if domain.startswith("http") else f"http://{domain}"

    for url in [
        f"{WAYBACK_URL}/{timestamp}id_/{target}",
        f"{WAYBACK_URL}/{timestamp}/{target}",
    ]:
        raw, status = fetch_url_bytes(url)
        if not raw:
            continue

        html = decode_html(raw)
        if not html:
            continue

        parser = TitleParser()
        try:
            parser.feed(html)
        except Exception:
            continue

        if parser.title:
            return parser.title, parser.is_redirect

    return None, False


def check_domain(domain):
    """1ドメインの最新タイトルを取得"""
    timestamp = get_latest_snapshot(domain)
    if not timestamp:
        return {
            "domain": domain,
            "last_seen": "",
            "title": "",
            "note": "アーカイブなし",
        }

    last_seen = f"{timestamp[:4]}-{timestamp[4:6]}"
    title, is_redirect = get_title_from_snapshot(domain, timestamp)

    if not title:
        return {
            "domain": domain,
            "last_seen": last_seen,
            "title": "",
            "note": "タイトル取得失敗",
        }

    note = detect_note(title, is_redirect)

    return {
        "domain": domain,
        "last_seen": last_seen,
        "title": title,
        "note": note,
    }


def check_domain_wrapper(args):
    """並列実行用ラッパー"""
    idx, total, domain = args
    print(f"[{idx}/{total}] {domain}")
    result = check_domain(domain)
    status = result["note"] if result["note"] else "OK"
    print(f"  → {result['last_seen']} | {result['title'][:50] if result['title'] else '(なし)'} | {status}")
    return result


def write_csv(results, output_path):
    """結果をCSVに書き出す"""
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ドメイン", "最終アーカイブ", "タイトル", "備考"])
        for r in results:
            writer.writerow([
                r["domain"],
                r["last_seen"],
                r["title"],
                r["note"],
            ])


def main():
    parser = argparse.ArgumentParser(description="中古ドメイン履歴調査ツール")
    parser.add_argument("input", help="ドメインリストファイル（1行1ドメイン）またはカンマ区切りドメイン")
    parser.add_argument("-o", "--output", default="domain_history.csv", help="出力CSVファイル名")
    args = parser.parse_args()

    domains = []
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            for line in f:
                d = line.strip().strip(",").strip()
                if d and not d.startswith("#"):
                    domains.append(d)
    except FileNotFoundError:
        domains = [d.strip() for d in args.input.split(",") if d.strip()]

    if not domains:
        print("ドメインが指定されていません")
        sys.exit(1)

    # http/httpsを除去
    domains = [re.sub(r'^https?://', '', d).rstrip('/') for d in domains]

    print(f"調査対象: {len(domains)} ドメイン")
    print(f"出力先: {args.output}")

    results = []
    tasks = [(i + 1, len(domains), d) for i, d in enumerate(domains)]

    # 5ドメイン並列で処理
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(check_domain_wrapper, t): t for t in tasks}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            # 20件ごとに途中保存
            if len(results) % 20 == 0:
                write_csv(sorted(results, key=lambda r: r["domain"]), args.output)
                print(f"  >>> 途中結果を保存 ({len(results)}/{len(domains)}件完了)")

    # ドメイン名順にソートして最終出力
    results.sort(key=lambda r: r["domain"])
    write_csv(results, args.output)

    # サマリ
    print(f"\n{'='*60}")
    print(f"調査完了: {len(results)} ドメイン")
    print(f"{'='*60}")

    ok = [r for r in results if not r["note"]]
    parking = [r for r in results if r["note"] == "パーキング"]
    redirect = [r for r in results if r["note"] == "リダイレクト"]
    no_archive = [r for r in results if r["note"] == "アーカイブなし"]
    failed = [r for r in results if r["note"] == "タイトル取得失敗"]

    print(f"\n  OK: {len(ok)}件 | パーキング: {len(parking)}件 | リダイレクト: {len(redirect)}件 | アーカイブなし: {len(no_archive)}件 | 取得失敗: {len(failed)}件")
    print(f"\n結果CSV: {args.output}")


if __name__ == "__main__":
    main()
