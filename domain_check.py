#!/usr/bin/env python3
"""
中古ドメイン履歴調査ツール
Wayback Machine CDX API を使い、ドメインの最新タイトルを一括取得する。
"""

import csv
import json
import re
import sys
import argparse
import asyncio

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

CDX_API = "https://web.archive.org/cdx/search/cdx"
WAYBACK_URL = "https://web.archive.org/web"
CONCURRENCY = 5
TIMEOUT_SEC = 20

PARKING_PATTERNS = [
    "parking", "parked", "for sale", "buy this domain",
    "domain expired", "this domain", "coming soon",
    "under construction", "is available", "domain name",
    "sedoparking", "hugedomains", "godaddy", "afternic",
    "dan.com", "sav.com",
]

REDIRECT_PATTERNS = [
    "window.location", "location.href", "location.replace",
    "location.assign", "document.location",
]


def detect_note(title, html=""):
    """タイトルと HTML から備考を判定"""
    if not title:
        return ""
    lower = title.lower()
    for pattern in PARKING_PATTERNS:
        if pattern in lower:
            return "パーキング"

    # meta refresh チェック
    html_lower = html.lower()
    if 'http-equiv="refresh"' in html_lower or "http-equiv='refresh'" in html_lower:
        if "url=" in html_lower:
            return "リダイレクト"

    # JS リダイレクトチェック
    for pattern in REDIRECT_PATTERNS:
        if pattern in html_lower:
            return "リダイレクト"

    return ""


def decode_html(data):
    """HTMLバイトデータをエンコーディング自動検出でデコード"""
    if not data:
        return ""

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

    for enc in ["shift_jis", "euc-jp", "cp932"]:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            pass

    return data.decode("utf-8", errors="replace")


def extract_title(html):
    """HTMLからtitleタグを正規表現で抽出"""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    return None


# ========== async版（aiohttp使用）==========

async def async_get_latest_snapshot(session, domain):
    """CDX APIで最新スナップショットのタイムスタンプを取得"""
    urls_to_try = [domain, f"http://{domain}", f"https://{domain}"]
    for try_url in urls_to_try:
        params = [
            ("url", try_url),
            ("output", "json"),
            ("fl", "timestamp,statuscode"),
            ("filter", "statuscode:200"),
            ("filter", "mimetype:text/html"),
            ("limit", "3"),
            ("sort", "reverse"),
        ]
        try:
            async with session.get(CDX_API, params=params,
                                   timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC)) as resp:
                data = await resp.json(content_type=None)
                if len(data) > 1:
                    return data[1][0]
        except Exception:
            continue
    return None


async def async_get_title(session, domain, timestamp):
    """スナップショットHTMLからタイトルを取得"""
    url = f"{WAYBACK_URL}/{timestamp}id_/http://{domain}"
    try:
        async with session.get(url,
                               timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC)) as resp:
            if resp.status != 200:
                return None, ""
            chunk = await resp.content.read(50000)
            html = decode_html(chunk)
            title = extract_title(html)
            return title, html
    except Exception:
        pass
    return None, ""


async def async_check_domain(session, sem, domain, idx, total):
    """1ドメインの処理"""
    async with sem:
        print(f"[{idx}/{total}] {domain}")
        timestamp = await async_get_latest_snapshot(session, domain)
        if not timestamp:
            print(f"  → アーカイブなし")
            return {
                "domain": domain, "last_seen": "",
                "title": "", "note": "アーカイブなし",
            }

        last_seen = f"{timestamp[:4]}-{timestamp[4:6]}"
        title, html = await async_get_title(session, domain, timestamp)

        if not title:
            print(f"  → {last_seen} | タイトル取得失敗")
            return {
                "domain": domain, "last_seen": last_seen,
                "title": "", "note": "タイトル取得失敗",
            }

        note = detect_note(title, html)
        print(f"  → {last_seen} | {title[:50]} | {note or 'OK'}")
        return {
            "domain": domain, "last_seen": last_seen,
            "title": title, "note": note,
        }


async def async_main(domains, output_path):
    """async版メイン処理（失敗分は自動リトライ）"""
    sem = asyncio.Semaphore(CONCURRENCY)
    headers = {"User-Agent": "Mozilla/5.0 (domain-history-checker)"}

    async with aiohttp.ClientSession(headers=headers) as session:
        # 1周目
        print(f"\n=== 1周目: {len(domains)}件 ===")
        tasks = [
            async_check_domain(session, sem, d, i + 1, len(domains))
            for i, d in enumerate(domains)
        ]

        results = []
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)

            if len(results) % 20 == 0:
                write_csv(sorted(results, key=lambda r: r["domain"]), output_path)
                print(f"  >>> 途中結果を保存 ({len(results)}/{len(domains)}件完了)")

        # 1周目の結果を保存
        write_csv(sorted(results, key=lambda r: r["domain"]), output_path)

        # 2周目: 失敗分だけリトライ
        failed = [r for r in results if r["note"] in ("アーカイブなし", "タイトル取得失敗")]
        if failed:
            print(f"\n=== 2周目（リトライ）: {len(failed)}件 ===")
            ok_results = [r for r in results if r not in failed]

            retry_tasks = [
                async_check_domain(session, sem, r["domain"], i + 1, len(failed))
                for i, r in enumerate(failed)
            ]

            retry_results = []
            for coro in asyncio.as_completed(retry_tasks):
                result = await coro
                retry_results.append(result)

            # リトライで成功したものだけ上書き
            retry_map = {r["domain"]: r for r in retry_results}
            final_results = []
            for r in results:
                if r["domain"] in retry_map and retry_map[r["domain"]]["note"] == "":
                    final_results.append(retry_map[r["domain"]])
                elif r["domain"] in retry_map and r["note"] == "アーカイブなし" and retry_map[r["domain"]]["title"]:
                    final_results.append(retry_map[r["domain"]])
                else:
                    final_results.append(r)

            results = final_results

    return results


# ========== sync版（フォールバック）==========

def sync_check_domain(domain):
    """同期版: 1ドメインの処理"""
    import urllib.request
    import urllib.error
    import urllib.parse

    timestamp = None
    for try_url in [domain, f"http://{domain}", f"https://{domain}"]:
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
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (domain-history-checker)"
            })
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
                data = json.loads(resp.read(100000).decode("utf-8", errors="replace"))
                if len(data) > 1:
                    timestamp = data[1][0]
                    break
        except Exception:
            continue

    if not timestamp:
        return {"domain": domain, "last_seen": "", "title": "", "note": "アーカイブなし"}

    last_seen = f"{timestamp[:4]}-{timestamp[4:6]}"
    wb_url = f"{WAYBACK_URL}/{timestamp}id_/http://{domain}"

    title, html = None, ""
    try:
        req = urllib.request.Request(wb_url, headers={
            "User-Agent": "Mozilla/5.0 (domain-history-checker)"
        })
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            chunk = resp.read(50000)
            html = decode_html(chunk)
            title = extract_title(html)
    except Exception:
        pass

    if not title:
        return {"domain": domain, "last_seen": last_seen, "title": "", "note": "タイトル取得失敗"}

    note = detect_note(title, html)
    return {"domain": domain, "last_seen": last_seen, "title": title, "note": note}


# ========== 共通 ==========

def write_csv(results, output_path):
    """結果をCSVに書き出す"""
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ドメイン", "最終アーカイブ", "タイトル", "備考"])
        for r in results:
            writer.writerow([r["domain"], r["last_seen"], r["title"], r["note"]])


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

    domains = [re.sub(r'^https?://', '', d).rstrip('/') for d in domains]

    print(f"調査対象: {len(domains)} ドメイン")
    print(f"出力先: {args.output}")

    if HAS_AIOHTTP:
        print("モード: async (aiohttp)")
        results = asyncio.run(async_main(domains, args.output))
    else:
        print("モード: sync (aiohttp未インストール)")
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = []
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
            futures = {executor.submit(sync_check_domain, d): d for d in domains}
            for i, future in enumerate(as_completed(futures)):
                result = future.result()
                results.append(result)
                d = result["domain"]
                status = result["note"] or "OK"
                print(f"[{i+1}/{len(domains)}] {d} → {status}")
                if len(results) % 20 == 0:
                    write_csv(sorted(results, key=lambda r: r["domain"]), args.output)

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
    print(f"  OK: {len(ok)} | パーキング: {len(parking)} | リダイレクト: {len(redirect)} | アーカイブなし: {len(no_archive)} | 取得失敗: {len(failed)}")
    print(f"\n結果CSV: {args.output}")


if __name__ == "__main__":
    main()
