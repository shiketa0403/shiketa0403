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
    python link_check.py https://www.meti.go.jp -o out.csv --browser
        # --browser: Playwright の実ブラウザ(Chrome)経由でアクセスする。
        #   政府系サイト等、プログラムからのアクセスを WAF が 403 で弾くサイト向け。
        #   事前に: pip install playwright && python -m playwright install chromium
        #   それでも 403 になる場合は --headed でブラウザ画面を表示して実行する。
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
BROWSER_BATCH = 8  # ブラウザ内fetchの同時実行数（同一サーバへの負荷を抑える）
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


def verdict_from_status(status):
    """HTTPステータス → (判定, 詳細)。正常なら None"""
    if status < 400:
        return None
    if status in NEEDS_REVIEW_STATUS:
        return "要確認", "アクセス制限の可能性（Bot対策等）。手動確認推奨"
    return "リンク切れ", ""


def requests_fetch_text(url):
    """requests でテキスト取得。戻り値: (status, content_type, text)。接続不可は status=-1"""
    try:
        r = fetch(url)
        return r.status_code, r.headers.get("Content-Type", ""), r.text
    except requests.RequestException as e:
        return -1, "", str(e)[:150]


class BrowserFetcher:
    """Playwright の実ブラウザ経由でページ取得・リンク確認を行う。

    トップページに一度アクセスして WAF を通過した後は、そのページ内の
    fetch() （本物のChromeのネットワークスタック・Cookie込み）で
    同一サイト内の URL を取得・確認する。
    """

    _JS_FETCH_TEXT = """async (u) => {
      try {
        const r = await fetch(u, {redirect: 'follow', signal: AbortSignal.timeout(20000)});
        const ct = r.headers.get('content-type') || '';
        let text = '';
        if (r.status < 400 && (ct.includes('html') || ct.includes('xml'))) {
          text = await r.text();
        } else {
          try { if (r.body) r.body.cancel(); } catch (e) {}
        }
        return {status: r.status, ct: ct, text: text};
      } catch (e) {
        return {status: -1, ct: '', text: '', error: String(e).slice(0, 150)};
      }
    }"""

    _JS_CHECK_BATCH = """async (urls) => {
      const out = [];
      await Promise.all(urls.map(async (u) => {
        try {
          const r = await fetch(u, {redirect: 'follow', signal: AbortSignal.timeout(20000)});
          try { if (r.body) r.body.cancel(); } catch (e) {}
          out.push([u, r.status, '']);
        } catch (e) {
          out.push([u, -1, String(e).slice(0, 150)]);
        }
      }));
      return out;
    }"""

    def __init__(self, base_url, headed=False):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("ERROR: --browser には Playwright が必要です。以下を実行してください:", file=sys.stderr)
            print("  pip install playwright", file=sys.stderr)
            print("  python -m playwright install chromium", file=sys.stderr)
            sys.exit(1)
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=not headed)
        self._context = self._browser.new_context(locale="ja-JP", bypass_csp=True)
        self.page = self._context.new_page()
        self.base_url = base_url
        status = self._goto(base_url)
        if status == 202:
            # AWS WAF の JavaScript チャレンジ。ブラウザが自動解決するのを待つ
            print("WAFのJavaScriptチャレンジを検出（HTTP 202）。自動解決を待ちます...")
            print("※ブラウザ画面にパズル等の確認が表示された場合は手動で操作してください")
            for _ in range(5):
                self.page.wait_for_timeout(6000)
                status = self._goto(base_url)
                if status != 202:
                    break
        print(f"ブラウザでトップページを取得: HTTP {status}")
        if status >= 400 or status == 202:
            print(f"ERROR: 実ブラウザでも HTTP {status} で拒否されました。", file=sys.stderr)
            print(f"  通常のブラウザで {base_url} が開けるか確認してください。", file=sys.stderr)
            if not headed:
                print("  開ける場合は --headed を付けて再実行してみてください。", file=sys.stderr)
            self.close()
            sys.exit(1)

    def _goto(self, url):
        resp = self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return resp.status if resp else 0

    def _nav_fetch(self, url, need_text=True):
        """ブラウザの画面遷移でURLを取得（WAFチャレンジは遷移中に自動解決される）。

        戻り値: (status, content_type, text)。ナビゲーション不可は status=-2、
        text にエラー内容。ダウンロード開始 = 実体あり = 200 扱い。
        """
        hinted = False
        for attempt in range(3):
            try:
                resp = self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                msg = str(e)
                if "Download is starting" in msg:
                    return 200, "application/octet-stream", ""
                return -2, "", msg[:150]
            if resp is None:
                return -2, "", "no response"
            if resp.status in (202, 405) and attempt < 2:
                # 202: JSチャレンジ（自動解決を待つ） / 405: CAPTCHA（手動解決が必要）
                if resp.status == 405 and not hinted:
                    print("※ブラウザ画面にCAPTCHA（パズル）が表示されていたら手動で解いてください")
                    hinted = True
                self.page.wait_for_timeout(8000 if resp.status == 405 else 4000)
                continue
            ct = resp.headers.get("content-type", "")
            text = ""
            if need_text and resp.status < 400 and ("html" in ct or "xml" in ct):
                try:
                    text = resp.text()
                except Exception:
                    text = self.page.content()
            return resp.status, ct, text
        return resp.status, resp.headers.get("content-type", ""), ""

    def fetch_text(self, url):
        r = self.page.evaluate(self._JS_FETCH_TEXT, url)
        if r["status"] in (202, 405):
            # ページ内fetchはWAFにチャレンジされやすい → 画面遷移で取得し直す
            return self._nav_fetch(url)
        return r["status"], r.get("ct", ""), r.get("text", "") or r.get("error", "")

    def check_urls(self, urls):
        """URLリストをブラウザ内 fetch で確認。戻り値: {url: (status, エラー文字列)}"""
        results = {}
        for i in range(0, len(urls), BROWSER_BATCH):
            chunk = urls[i:i + BROWSER_BATCH]
            for u, status, err in self.page.evaluate(self._JS_CHECK_BATCH, chunk):
                results[u] = (status, err)
            done = min(i + BROWSER_BATCH, len(urls))
            if done % 80 < BROWSER_BATCH or done == len(urls):
                print(f"内部リンク確認済み {done}/{len(urls)}")
            time.sleep(0.3)
        # WAFチャレンジ応答(202/405)は画面遷移で1件ずつ確認し直す（確実だが低速）
        pending = [u for u, (s, _) in results.items() if s in (202, 405)]
        if pending:
            print(f"WAFチャレンジ応答が{len(pending)}件 → ブラウザ遷移で1件ずつ再確認します"
                  f"（1件あたり1〜2秒かかります）")
            for n, u in enumerate(pending, 1):
                status, _, err = self._nav_fetch(u, need_text=False)
                results[u] = (status, err if status < 0 else "")
                if n % 25 == 0 or n == len(pending):
                    print(f"再確認 {n}/{len(pending)}")
        return results

    def close(self):
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass


def get_sitemap_urls(base_url, fetch_text):
    """サイトマップから全ページURLを取得（インデックス形式は再帰的に辿る）"""
    candidates = ["wp-sitemap.xml", "sitemap_index.xml", "sitemap.xml"]
    for name in candidates:
        sitemap_url = urljoin(base_url + "/", name)
        status, ct, text = fetch_text(sitemap_url)
        if status != 200 or "<" not in text[:100]:
            print(f"サイトマップ候補 {sitemap_url}: HTTP {status}")
            continue
        urls = parse_sitemap(text, 0, fetch_text)
        if urls:
            print(f"サイトマップ検出: {sitemap_url}（{len(urls)}ページ）")
            return urls
        print(f"サイトマップ候補 {sitemap_url}: URL抽出0件")
    return []


def parse_sitemap(text, depth, fetch_text):
    if depth > 2:
        return []
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except (ET.ParseError, UnicodeEncodeError):
        return []
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = []
    # サイトマップインデックスの場合は子サイトマップを辿る
    for loc in root.findall(".//sm:sitemap/sm:loc", ns):
        status, _, child = fetch_text(loc.text.strip())
        if status == 200:
            urls.extend(parse_sitemap(child, depth + 1, fetch_text))
    for loc in root.findall(".//sm:url/sm:loc", ns):
        urls.append(loc.text.strip())
    return urls


def crawl_internal_pages(base_url, max_pages, fetch_text, html_cache=None):
    """サイトマップが無い場合のフォールバック: 内部リンクをBFSでクロール"""
    host = urlparse(base_url).netloc
    seen = {base_url}
    queue = [base_url]
    pages = []
    errors_shown = 0
    while queue and len(pages) < max_pages:
        url = queue.pop(0)
        status, ct, text = fetch_text(url)
        if status != 200 or "text/html" not in ct:
            if errors_shown < 10:
                print(f"クロール対象外 HTTP {status} Content-Type={ct or '(なし)'}: {url}")
                errors_shown += 1
            continue
        pages.append(url)
        if html_cache is not None:
            html_cache[url] = text
        if len(pages) % 25 == 0:
            print(f"クロール中... {len(pages)}/{max_pages}ページ目")
        soup = BeautifulSoup(text, "html.parser")
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
    """requests でURLの生存確認。戻り値: (判定, ステータス, 詳細)  判定 None は正常"""
    last_error = None
    for attempt in range(2):  # 接続系エラーは1回リトライ
        try:
            r = fetch(url, stream=True)
            status = r.status_code
            reason = r.reason or ""
            r.close()
            verdict = verdict_from_status(status)
            if verdict is None:
                return None, status, ""
            return verdict[0], status, verdict[1] or reason
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
    parser.add_argument("--browser", action="store_true",
                        help="Playwrightの実ブラウザ経由でアクセス（Bot対策で403になるサイト向け）")
    parser.add_argument("--headed", action="store_true",
                        help="--browser 使用時にブラウザ画面を表示する")
    args = parser.parse_args()

    base_url = args.site_url.rstrip("/")
    host = urlparse(base_url).netloc

    br = None
    if args.browser:
        br = BrowserFetcher(base_url, headed=args.headed)
        fetch_text = br.fetch_text
    else:
        fetch_text = requests_fetch_text

    try:
        html_cache = {}
        pages = get_sitemap_urls(base_url, fetch_text)
        if not pages:
            print("サイトマップが見つからないため内部リンクをクロールします")
            pages = crawl_internal_pages(base_url, args.max_pages, fetch_text, html_cache)
        pages = pages[: args.max_pages]
        if not pages:
            print("ERROR: ページを1件も取得できませんでした", file=sys.stderr)
            sys.exit(1)
        print(f"確認対象: {len(pages)}ページ")

        # 各ページからリンクを収集（リンクURL -> [(掲載ページ, 種別, テキスト), ...]）
        link_sources = {}
        for i, page_url in enumerate(pages, 1):
            if page_url in html_cache:
                status, text = 200, html_cache[page_url]
            else:
                status, ct, text = fetch_text(page_url)
            if status != 200:
                print(f"[{i}/{len(pages)}] ページ取得失敗 {status}: {page_url}")
                link_sources.setdefault(page_url, []).append((page_url, "ページ本体", ""))
                continue
            for url, kind, anchor in extract_links(page_url, text):
                if args.internal_only and urlparse(url).netloc != host:
                    continue
                link_sources.setdefault(url, []).append((page_url, kind, anchor))
            if i % 50 == 0:
                print(f"[{i}/{len(pages)}] リンク収集中...")
            time.sleep(0.1)

        print(f"ユニークリンク数: {len(link_sources)}件 → ステータス確認開始")

        # 判定結果: url -> (判定 or None, ステータス, 詳細)
        judged = {}

        internal = [u for u in link_sources if urlparse(u).netloc == host]
        external = [u for u in link_sources if urlparse(u).netloc != host]

        if br is not None:
            # 内部リンクはブラウザ経由で確認（WAFを通過できるのはブラウザだけのため）
            print(f"内部リンク {len(internal)}件をブラウザ経由で確認")
            browser_results = br.check_urls(internal)
            fallback = []
            for u, (status, err) in browser_results.items():
                if status == -1:
                    fallback.append(u)  # ブラウザ内fetch不可（http混在等）→ requestsで再確認
                    continue
                if status == -2:
                    if "Timeout" in err:
                        judged[u] = ("要確認", "", f"タイムアウト: {err}")
                    else:
                        judged[u] = ("リンク切れ", "", f"接続不可: {err}")
                    continue
                if status in (202, 405):
                    judged[u] = ("要確認", status, "WAFチャレンジ応答。ブラウザで手動確認推奨")
                    continue
                verdict = verdict_from_status(status)
                judged[u] = (None, status, "") if verdict is None else (verdict[0], status, verdict[1])
            to_check_with_requests = external + fallback
        else:
            to_check_with_requests = internal + external

        if to_check_with_requests:
            print(f"{len(to_check_with_requests)}件を通常アクセスで確認")
            checked = 0
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                futures = {pool.submit(check_url, u): u for u in to_check_with_requests}
                for future in as_completed(futures):
                    u = futures[future]
                    verdict, status, detail = future.result()
                    judged[u] = (verdict, status, detail)
                    checked += 1
                    if checked % 100 == 0:
                        print(f"確認済み {checked}/{len(to_check_with_requests)}")

        results = []  # (掲載ページ, リンクURL, 種別, テキスト, 判定, ステータス, 詳細)
        for url, (verdict, status, detail) in judged.items():
            if verdict is None:
                continue
            for page_url, kind, anchor in link_sources[url]:
                results.append((page_url, url, kind, anchor, verdict, status, detail))

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
    finally:
        if br is not None:
            br.close()


if __name__ == "__main__":
    main()
