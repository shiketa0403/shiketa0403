#!/usr/bin/env python3
"""
中古ドメイン履歴調査ツール
Wayback Machine CDX API を使い、ドメインの過去のタイトル変化を調査する。
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
MAX_WORKERS = 5  # 並列リクエスト数


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


def fetch_url_bytes(url, timeout=10, max_bytes=30000):
    """URLからバイトデータを取得（リトライ付き、先頭部分のみ）"""
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (domain-history-checker)"
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read(max_bytes)
                return data, resp.status
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
            else:
                return None, None


def fetch_url(url, timeout=10, max_bytes=30000):
    """URLからテキストを取得（UTF-8）"""
    data, status = fetch_url_bytes(url, timeout, max_bytes)
    if data is None:
        return None, None
    return data.decode("utf-8", errors="replace"), status


def decode_html(data):
    """HTMLバイトデータをエンコーディング自動検出でデコード"""
    if data is None:
        return None

    # まずHTMLからcharsetを探す
    head = data[:2000].decode("ascii", errors="replace").lower()
    charset = None

    # <meta charset="xxx">
    m = re.search(r'<meta[^>]+charset=["\']?([a-zA-Z0-9_-]+)', head)
    if m:
        charset = m.group(1)

    # <meta http-equiv="Content-Type" content="text/html; charset=xxx">
    if not charset:
        m = re.search(r'content=["\'][^"\']*charset=([a-zA-Z0-9_-]+)', head)
        if m:
            charset = m.group(1)

    # 検出されたcharsetで試す
    if charset:
        try:
            return data.decode(charset)
        except (UnicodeDecodeError, LookupError):
            pass

    # UTF-8を試す
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # 日本語エンコーディングを試す
    for enc in ["shift_jis", "euc-jp", "iso-2022-jp", "cp932"]:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            pass

    return data.decode("utf-8", errors="replace")


def get_snapshots(domain):
    """CDX APIで月別スナップショット一覧を取得（リトライ付き）"""
    urls_to_try = [f"*.{domain}", domain, f"http://{domain}", f"https://{domain}"]
    if domain.startswith("http://") or domain.startswith("https://"):
        urls_to_try = [domain]

    for attempt in range(2):
        if attempt > 0:
            print(f"  CDX APIリトライ ({attempt+1}/2)... 2秒待機")
            time.sleep(2)

        for try_url in urls_to_try:
            params = urllib.parse.urlencode({
                "url": try_url,
                "output": "json",
                "fl": "timestamp,statuscode,mimetype",
                "collapse": "timestamp:6",
                "filter": "mimetype:text/html",
                "limit": "5000",
            })
            url = f"{CDX_API}?{params}"
            print(f"  CDX API問い合わせ: {try_url}")
            body, status = fetch_url(url, timeout=30, max_bytes=500000)

            if not body:
                print(f"  CDX APIレスポンスなし（URL: {try_url}）")
                continue

            try:
                data = json.loads(body)
                if len(data) <= 1:
                    print(f"  スナップショットなし（URL: {try_url}）")
                    continue
                print(f"  {len(data)-1}件のスナップショットを取得")
                return [{"timestamp": row[0], "statuscode": row[1]} for row in data[1:]]
            except (json.JSONDecodeError, ValueError) as e:
                print(f"  JSONパースエラー: {e}")
                print(f"  レスポンス先頭200文字: {body[:200]}")
                continue

        # 全URLで失敗した場合、次のattemptへ
            continue

    return []


def get_title_from_snapshot(domain, timestamp):
    """Wayback Machineのスナップショットからタイトルを取得"""
    target = domain if domain.startswith("http") else f"http://{domain}"

    # id_付き（軽量）を試し、失敗したらid_なしも試す
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
            return timestamp, parser.title, parser.is_redirect

    return timestamp, None, False


def is_redirect_status(code):
    """HTTPステータスがリダイレクトかどうか"""
    try:
        return int(code) in (301, 302, 303, 307, 308)
    except (ValueError, TypeError):
        return False


# パーキング・無効ドメインのタイトルパターン
PARKING_PATTERNS = [
    "parking", "parked", "for sale", "buy this domain",
    "domain expired", "this domain", "coming soon",
    "under construction", "is available", "domain name",
    "sedoparking", "hugedomains", "godaddy", "afternic",
    "dan.com", "sav.com",
]


def detect_note(title):
    """タイトルから備考（パーキング等）を判定"""
    if not title:
        return ""
    lower = title.lower()
    for pattern in PARKING_PATTERNS:
        if pattern in lower:
            return "パーキング"
    return ""


def check_domain(domain):
    """1ドメインの履歴を調査"""
    print(f"\n{'='*60}")
    print(f"調査中: {domain}")
    print(f"{'='*60}")

    snapshots = get_snapshots(domain)
    if not snapshots:
        print(f"  アーカイブなし")
        return {
            "domain": domain,
            "status": "no_archive",
            "first_seen": "",
            "last_seen": "",
            "title_changes": 0,
            "is_redirect": False,
            "titles": "",
            "title_history": [],
        }

    # リダイレクトチェック
    recent = snapshots[-5:] if len(snapshots) >= 5 else snapshots
    redirect_count = sum(1 for s in recent if is_redirect_status(s["statuscode"]))
    if redirect_count >= len(recent) * 0.8:
        print(f"  リダイレクトドメイン（スキップ）")
        return {
            "domain": domain,
            "status": "redirect",
            "first_seen": snapshots[0]["timestamp"][:6],
            "last_seen": snapshots[-1]["timestamp"][:6],
            "title_changes": 0,
            "is_redirect": True,
            "titles": "(redirect)",
            "title_history": [],
        }

    # HTMLステータス200のスナップショットだけ使う
    valid_snapshots = [s for s in snapshots if s["statuscode"] == "200"]
    if not valid_snapshots:
        print(f"  有効なスナップショットなし")
        return {
            "domain": domain,
            "status": "no_valid_snapshot",
            "first_seen": snapshots[0]["timestamp"][:6],
            "last_seen": snapshots[-1]["timestamp"][:6],
            "title_changes": 0,
            "is_redirect": True,
            "titles": "",
            "title_history": [],
        }

    # サンプリング: 年1回（各年から1件ずつ取得）
    year_map = {}
    for snap in valid_snapshots:
        year = snap["timestamp"][:4]
        if year not in year_map:
            year_map[year] = snap  # 各年の最初のスナップショット
    sampled = list(year_map.values())
    # 最後のスナップショットも必ず含める
    if sampled[-1] != valid_snapshots[-1]:
        sampled.append(valid_snapshots[-1])

    print(f"  スナップショット数: {len(valid_snapshots)} → サンプル: {len(sampled)}")

    # タイトルを並列取得
    title_results = {}
    has_redirect = False

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(get_title_from_snapshot, domain, snap["timestamp"]): snap
            for snap in sampled
        }
        for future in as_completed(futures):
            ts, title, is_redir = future.result()
            title_results[ts] = (title, is_redir)
            if is_redir:
                has_redirect = True

    # タイムスタンプ順に並べてタイトル変化を検出
    titles_history = []
    prev_title = None
    for snap in sampled:
        ts = snap["timestamp"]
        title, is_redir = title_results.get(ts, (None, False))
        if title and title != prev_title:
            ym = f"{ts[:4]}-{ts[4:6]}"
            note = detect_note(title)
            if not note and is_redir:
                note = "リダイレクト"
            titles_history.append({"date": ym, "title": title, "note": note})
            print(f"  {ym}: {title}" + (f" [{note}]" if note else ""))
            prev_title = title
        elif not title:
            print(f"  {ts[:4]}-{ts[4:6]}: (タイトル取得失敗)")

    if has_redirect and len(titles_history) <= 1:
        print(f"  リダイレクト検出（meta refresh / JavaScript）")

    title_changes = len(titles_history)
    titles_str = " → ".join([t["title"] for t in titles_history])

    return {
        "domain": domain,
        "status": "ok",
        "first_seen": valid_snapshots[0]["timestamp"][:6],
        "last_seen": valid_snapshots[-1]["timestamp"][:6],
        "title_changes": title_changes,
        "is_redirect": has_redirect and title_changes <= 1,
        "titles": titles_str,
        "title_history": titles_history,
    }


def format_date(yyyymm):
    """202603 → 2026-03"""
    if len(yyyymm) >= 6:
        return f"{yyyymm[:4]}-{yyyymm[4:6]}"
    return yyyymm


def main():
    parser = argparse.ArgumentParser(description="中古ドメイン履歴調査ツール")
    parser.add_argument("input", help="ドメインリストファイル（1行1ドメイン）またはカンマ区切りドメイン")
    parser.add_argument("-o", "--output", default="domain_history.csv", help="出力CSVファイル名")
    args = parser.parse_args()

    # ドメインリスト取得
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

    print(f"調査対象: {len(domains)} ドメイン")
    print(f"出力先: {args.output}")

    results = []
    for domain in domains:
        domain = re.sub(r'^https?://', '', domain).rstrip('/')
        result = check_domain(domain)
        results.append(result)

    # CSV出力（1タイトル1行）
    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ドメイン", "ステータス", "初回アーカイブ", "最終アーカイブ",
            "タイトル変化回数", "時期", "タイトル", "備考"
        ])
        for r in results:
            if r["title_history"]:
                for i, t in enumerate(r["title_history"]):
                    writer.writerow([
                        r["domain"] if i == 0 else "",
                        r["status"] if i == 0 else "",
                        format_date(r["first_seen"]) if i == 0 else "",
                        format_date(r["last_seen"]) if i == 0 else "",
                        r["title_changes"] if i == 0 else "",
                        t["date"],
                        t["title"],
                        t.get("note", ""),
                    ])
            else:
                note = "リダイレクト" if r["is_redirect"] else "タイトル取得失敗"
                writer.writerow([
                    r["domain"],
                    r["status"],
                    format_date(r["first_seen"]),
                    format_date(r["last_seen"]),
                    r["title_changes"],
                    "",
                    "",
                    note,
                ])

    # サマリ出力
    print(f"\n{'='*60}")
    print(f"調査完了: {len(results)} ドメイン")
    print(f"{'='*60}")

    ok_results = [r for r in results if r["status"] == "ok" and not r["is_redirect"]]
    single_owner = [r for r in ok_results if r["title_changes"] == 1]
    multi_owner = [r for r in ok_results if r["title_changes"] > 1]

    print(f"\n★ 1運営者候補 ({len(single_owner)}件):")
    for r in single_owner:
        print(f"  {r['domain']} [{format_date(r['first_seen'])}〜{format_date(r['last_seen'])}] {r['titles']}")

    print(f"\n▲ 複数運営者 ({len(multi_owner)}件):")
    for r in multi_owner:
        print(f"  {r['domain']} (変化{r['title_changes']}回) {r['titles']}")

    redirect_results = [r for r in results if r["is_redirect"]]
    no_archive = [r for r in results if r["status"] == "no_archive"]
    if redirect_results:
        print(f"\n✕ リダイレクト除外 ({len(redirect_results)}件):")
        for r in redirect_results:
            print(f"  {r['domain']}")
    if no_archive:
        print(f"\n- アーカイブなし ({len(no_archive)}件):")
        for r in no_archive:
            print(f"  {r['domain']}")

    print(f"\n結果CSV: {args.output}")


if __name__ == "__main__":
    main()
