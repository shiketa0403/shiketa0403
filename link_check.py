#!/usr/bin/env python3
"""サイト内リンク切れチェックツール

サイトマップ（wp-sitemap.xml / sitemap_index.xml / sitemap.xml）から全ページを取得し、
各ページ内の <a href> / <img src> を抽出して HTTP ステータスを確認する。
サイトマップが無い場合はトップページから内部リンクをクロールする。

出力CSV（utf-8-sig / Excel対応）:
    掲載ページURL, リンクURL, 種別, アンカーテキスト, 判定, ステータス, 詳細

判定:
    リンク切れ … 404/410/5xx、DNS解決失敗、接続不可、SSLエラー
    要確認     … 403/405/429/999 など Bot 対策で弾かれた可能性があるもの、タイムアウト

使い方:
    python link_check.py https://civichat.jp -o broken_links.csv
    python link_check.py https://civichat.jp --internal-only   # 内部リンクのみ確認
"""
import argparse
import csv
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 LinkChecker/1.0"
)
TIMEOUT = 20
MAX_WORKERS = 10
# Bot対策・アクセス制限の可能性が高く、即「リンク切れ」と断定できないステータス
NEEDS_REVIEW_STATUS = {401, 403, 405, 406, 429, 999}
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "#")

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "ja,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
})


def fetch(url, stream=False):
    return session.get(url, timeout=TIMEOUT, allow_redirects=True, stream=stream)


def get_sitemap_urls(base_url):
    """サイトマップから全ページURLを取得（インデックス形式は再帰的に辿る）"""
    candidates = ["wp-sitemap.xml", "sitemap_index.xml", "sitemap.xml"]
    for name in candidates:
        sitemap_url = urljoin(base_url + "/", name)
        try:
            r = fetch(sitemap_url)
            if r.status_code != 200 or b"<" not in r.content[:100]:
                print(f"サイトマップ候補 {sitemap_url}: HTTP {r.status_code}")
                continue
            urls = parse_sitemap(r.content, depth=0)
            if urls:
                print(f"サイトマップ検出: {sitemap_url}（{len(urls)}ページ）")
                return urls
            print(f"サイトマップ候補 {sitemap_url}: URL抽出0件")
        except requests.RequestException as e:
            print(f"サイトマップ候補 {sitemap_url}: 取得エラー ({str(e)[:150]})")
    return []


def parse_sitemap(content, depth):
    if depth > 2:
        return []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = []
    # サイトマップインデックスの場合は子サイトマップを辿る
    for loc in root.findall(".//sm:sitemap/sm:loc", ns):
        try:
            r = fetch(loc.text.strip())
            if r.status_code == 200:
                urls.extend(parse_sitemap(r.content, depth + 1))
        except requests.RequestException:
            pass
    for loc in root.findall(".//sm:url/sm:loc", ns):
        urls.append(loc.text.strip())
    return urls


def crawl_internal_pages(base_url, max_pages):
    """サイトマップが無い場合のフォールバック: 内部リンクをBFSでクロール"""
    host = urlparse(base_url).netloc
    seen = {base_url}
    queue = [base_url]
    pages = []
    errors_shown = 0
    while queue and len(pages) < max_pages:
        url = queue.pop(0)
        try:
            r = fetch(url)
            if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
                if errors_shown < 10:
                    print(f"クロール対象外 HTTP {r.status_code} "
                          f"Content-Type={r.headers.get('Content-Type', '(なし)')}: {url}")
                    errors_shown += 1
                continue
        except requests.RequestException as e:
            if errors_shown < 10:
                print(f"クロール取得エラー: {url} ({str(e)[:150]})")
                errors_shown += 1
            continue
        pages.append(url)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            link = urldefrag(urljoin(url, a["href"]))[0]
            if urlparse(link).netloc == host and link not in seen:
                seen.add(link)
                queue.append(link)
        time.sleep(0.2)
    return pages


def extract_links(page_url, html):
    """ページ内の <a href> と <img src> を (URL, 種別, テキスト) で返す"""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.lower().startswith(SKIP_SCHEMES):
            continue
        text = a.get_text(strip=True) or "(画像リンク)"
        links.append((urldefrag(urljoin(page_url, href))[0], "リンク(a)", text[:50]))
    for img in soup.find_all("img", src=True):
        src = img["src"].strip()
        if not src or src.lower().startswith(SKIP_SCHEMES):
            continue
        alt = img.get("alt", "").strip()
        links.append((urldefrag(urljoin(page_url, src))[0], "画像(img)", alt[:50]))
    return links


def check_url(url):
    """URLの生存確認。戻り値: (判定, ステータス, 詳細)  判定 None は正常"""
    last_error = None
    for attempt in range(2):  # 接続系エラーは1回リトライ
        try:
            r = fetch(url, stream=True)
            status = r.status_code
            r.close()
            if status < 400:
                return None, status, ""
            if status in NEEDS_REVIEW_STATUS:
                return "要確認", status, "アクセス制限の可能性（Bot対策等）。手動確認推奨"
            return "リンク切れ", status, r.reason or ""
        except requests.exceptions.SSLError as e:
            return "リンク切れ", "", f"SSLエラー: {e}"
        except requests.exceptions.ConnectionError as e:
            last_error = ("リンク切れ", "", f"接続不可（DNS解決失敗等）: {str(e)[:100]}")
        except requests.exceptions.Timeout:
            last_error = ("要確認", "", f"タイムアウト（{TIMEOUT}秒）")
        except requests.RequestException as e:
            last_error = ("リンク切れ", "", f"エラー: {str(e)[:100]}")
        time.sleep(1)
    return last_error


def main():
    parser = argparse.ArgumentParser(description="サイト内リンク切れチェック")
    parser.add_argument("site_url", help="対象サイトURL（例: https://civichat.jp）")
    parser.add_argument("-o", "--output", default="broken_links.csv", help="出力CSVパス")
    parser.add_argument("--internal-only", action="store_true", help="内部リンクのみ確認")
    parser.add_argument("--max-pages", type=int, default=1000, help="確認する最大ページ数")
    args = parser.parse_args()

    base_url = args.site_url.rstrip("/")
    host = urlparse(base_url).netloc

    pages = get_sitemap_urls(base_url)
    if not pages:
        print("サイトマップが見つからないため内部リンクをクロールします")
        pages = crawl_internal_pages(base_url, args.max_pages)
    pages = pages[: args.max_pages]
    if not pages:
        print("ERROR: ページを1件も取得できませんでした", file=sys.stderr)
        sys.exit(1)
    print(f"確認対象: {len(pages)}ページ")

    # 各ページからリンクを収集（リンクURL -> [(掲載ページ, 種別, テキスト), ...]）
    link_sources = {}
    for i, page in enumerate(pages, 1):
        try:
            r = fetch(page)
            if r.status_code != 200:
                print(f"[{i}/{len(pages)}] ページ取得失敗 {r.status_code}: {page}")
                link_sources.setdefault(page, []).append((page, "ページ本体", ""))
                continue
        except requests.RequestException as e:
            print(f"[{i}/{len(pages)}] ページ取得エラー: {page} ({e})")
            link_sources.setdefault(page, []).append((page, "ページ本体", ""))
            continue
        for url, kind, text in extract_links(page, r.text):
            if args.internal_only and urlparse(url).netloc != host:
                continue
            link_sources.setdefault(url, []).append((page, kind, text))
        if i % 50 == 0:
            print(f"[{i}/{len(pages)}] リンク収集中...")
        time.sleep(0.1)

    print(f"ユニークリンク数: {len(link_sources)}件 → ステータス確認開始")

    results = []  # (掲載ページ, リンクURL, 種別, テキスト, 判定, ステータス, 詳細)
    checked = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(check_url, url): url for url in link_sources}
        for future in as_completed(futures):
            url = futures[future]
            verdict, status, detail = future.result()
            checked += 1
            if checked % 100 == 0:
                print(f"確認済み {checked}/{len(link_sources)}")
            if verdict is None:
                continue
            for page, kind, text in link_sources[url]:
                results.append((page, url, kind, text, verdict, status, detail))

    results.sort(key=lambda r: (r[4], r[0], r[1]))
    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["掲載ページURL", "リンクURL", "種別", "アンカーテキスト", "判定", "ステータス", "詳細"])
        writer.writerows(results)

    broken = sum(1 for r in results if r[4] == "リンク切れ")
    review = sum(1 for r in results if r[4] == "要確認")
    print("=" * 60)
    print(f"確認ページ数   : {len(pages)}")
    print(f"確認リンク数   : {len(link_sources)}（ユニーク）")
    print(f"リンク切れ     : {broken}件")
    print(f"要確認         : {review}件")
    print(f"出力: {args.output}")


if __name__ == "__main__":
    main()
