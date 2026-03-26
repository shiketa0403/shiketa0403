#!/usr/bin/env python3
"""
中古ドメイン履歴調査ツール
Wayback Machine CDX API を使い、ドメインの過去のタイトル変化を調査する。
"""

import csv
import io
import re
import sys
import time
import argparse
import urllib.request
import urllib.error
import urllib.parse
from html.parser import HTMLParser


CDX_API = "https://web.archive.org/cdx/search/cdx"
WAYBACK_URL = "https://web.archive.org/web"
REQUEST_INTERVAL = 0.3  # 秒（rate limit対策）
MAX_RETRIES = 2


class TitleParser(HTMLParser):
    """HTMLから<title>タグの中身を抽出する"""
    def __init__(self):
        super().__init__()
        self._in_title = False
        self._title = ""
        self._has_meta_refresh = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            attrs_dict = dict(attrs)
            if attrs_dict.get("http-equiv", "").lower() == "refresh":
                content = attrs_dict.get("content", "")
                if "url=" in content.lower():
                    self._has_meta_refresh = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self._title += data

    @property
    def title(self):
        return self._title.strip()

    @property
    def is_meta_refresh(self):
        return self._has_meta_refresh


def fetch_url(url, timeout=15, max_bytes=50000):
    """URLからコンテンツを取得（リトライ付き、先頭部分のみ）"""
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (domain-history-checker)"
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                # <title>はhead内にあるので先頭部分だけ読む
                data = resp.read(max_bytes)
                return data.decode("utf-8", errors="replace"), resp.status
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2)
            else:
                print(f"  [WARN] 取得失敗: {url} ({e})")
                return None, None


def get_snapshots(domain):
    """CDX APIで月別スナップショット一覧を取得"""
    params = urllib.parse.urlencode({
        "url": domain,
        "output": "json",
        "fl": "timestamp,statuscode,mimetype",
        "collapse": "timestamp:6",  # 月単位で重複除去
        "filter": "mimetype:text/html",
        "limit": "5000",
    })
    url = f"{CDX_API}?{params}"
    body, status = fetch_url(url)
    if not body:
        return []

    rows = []
    try:
        import json
        data = json.loads(body)
        if len(data) <= 1:
            return []
        # data[0]はヘッダー行
        for row in data[1:]:
            ts, sc, _ = row
            rows.append({"timestamp": ts, "statuscode": sc})
    except (json.JSONDecodeError, ValueError):
        return []

    return rows


def get_title_from_snapshot(domain, timestamp):
    """Wayback Machineのスナップショットからタイトルを取得"""
    url = f"{WAYBACK_URL}/{timestamp}/{domain}"
    html, status = fetch_url(url)
    if not html:
        return None, False

    parser = TitleParser()
    try:
        parser.feed(html)
    except Exception:
        return None, False

    return parser.title if parser.title else None, parser.is_meta_refresh


def is_redirect_status(code):
    """HTTPステータスがリダイレクトかどうか"""
    try:
        return int(code) in (301, 302, 303, 307, 308)
    except (ValueError, TypeError):
        return False


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

    # リダイレクトチェック: 直近のスナップショットの大半がリダイレクトか
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
        print(f"  有効なスナップショットなし（全てリダイレクト等）")
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

    # サンプリング: 最大10件にする（均等間隔）
    max_samples = 10
    if len(valid_snapshots) > max_samples:
        step = len(valid_snapshots) / max_samples
        sampled = [valid_snapshots[int(i * step)] for i in range(max_samples)]
        # 最初と最後は必ず含める
        if sampled[0] != valid_snapshots[0]:
            sampled[0] = valid_snapshots[0]
        if sampled[-1] != valid_snapshots[-1]:
            sampled[-1] = valid_snapshots[-1]
    else:
        sampled = valid_snapshots

    print(f"  スナップショット数: {len(valid_snapshots)} → サンプル: {len(sampled)}")

    # タイトルを取得
    titles_history = []
    prev_title = None
    has_meta_refresh = False

    for i, snap in enumerate(sampled):
        ts = snap["timestamp"]
        time.sleep(REQUEST_INTERVAL)
        title, is_meta = get_title_from_snapshot(domain, ts)

        if is_meta:
            has_meta_refresh = True

        if title and title != prev_title:
            ym = f"{ts[:4]}-{ts[4:6]}"
            titles_history.append({"date": ym, "title": title})
            print(f"  {ym}: {title}")
            prev_title = title
        elif title:
            pass  # 同じタイトル、スキップ
        else:
            print(f"  {ts[:4]}-{ts[4:6]}: (タイトル取得失敗)")

    # meta refreshリダイレクトの場合も除外
    if has_meta_refresh and len(titles_history) <= 1:
        print(f"  meta refreshリダイレクト検出")

    title_changes = len(titles_history)
    titles_str = " → ".join([t["title"] for t in titles_history])

    return {
        "domain": domain,
        "status": "ok",
        "first_seen": valid_snapshots[0]["timestamp"][:6],
        "last_seen": valid_snapshots[-1]["timestamp"][:6],
        "title_changes": title_changes,
        "is_redirect": has_meta_refresh and title_changes <= 1,
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
        # カンマ区切りとして解釈
        domains = [d.strip() for d in args.input.split(",") if d.strip()]

    if not domains:
        print("ドメインが指定されていません")
        sys.exit(1)

    print(f"調査対象: {len(domains)} ドメイン")
    print(f"出力先: {args.output}")

    # 調査実行
    results = []
    for domain in domains:
        # http/httpsを除去
        domain = re.sub(r'^https?://', '', domain).rstrip('/')
        result = check_domain(domain)
        results.append(result)

    # CSV出力
    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ドメイン", "ステータス", "初回アーカイブ", "最終アーカイブ",
            "タイトル変化回数", "リダイレクト", "タイトル履歴"
        ])
        for r in results:
            writer.writerow([
                r["domain"],
                r["status"],
                format_date(r["first_seen"]),
                format_date(r["last_seen"]),
                r["title_changes"],
                "YES" if r["is_redirect"] else "NO",
                r["titles"],
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
