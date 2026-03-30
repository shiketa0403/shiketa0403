#!/usr/bin/env python3
"""
Wayback Machine 全ページメタデータ取得ツール
CDX API で過去のアーカイブ済み全URLを取得し、各ページの
タイトル・メタディスクリプション・見出し(H1-H3)・本文テキストを抽出してCSV出力する。
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
TIMEOUT_SEC = 30

# 除外するファイル拡張子
SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".webp", ".bmp",
    ".css", ".js", ".json", ".xml", ".txt", ".pdf", ".zip", ".gz",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv",
    ".swf", ".exe", ".dll", ".dmg",
}


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
    """HTMLからtitleタグを抽出"""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        text = re.sub(r"<[^>]+>", "", match.group(1))
        return re.sub(r"\s+", " ", text).strip()
    return ""


def extract_headings(html, tag):
    """HTMLから指定タグ(h1,h2,h3)を全て抽出し、 | 区切りで返す"""
    matches = re.findall(rf"<{tag}[^>]*>(.*?)</{tag}>", html, re.IGNORECASE | re.DOTALL)
    results = []
    for m in matches:
        text = re.sub(r"<[^>]+>", "", m)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            results.append(text)
    return " | ".join(results)


def extract_meta_description(html):
    """HTMLからmeta descriptionを抽出"""
    # name="description" パターン
    patterns = [
        r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)["\']',
        r'<meta\s+content=["\']([^"\']*)["\'\s]+name=["\']description["\']',
        r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if match:
            text = re.sub(r"\s+", " ", match.group(1)).strip()
            return text
    return ""


def extract_body_text(html):
    """HTMLからbody内の本文テキストを抽出（タグ除去）"""
    text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<head[^>]*>.*?</head>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def should_skip_url(url):
    """静的ファイル等のスキップ判定"""
    lower = url.lower().split("?")[0]
    for ext in SKIP_EXTENSIONS:
        if lower.endswith(ext):
            return True
    return False


# ========== CDX API: 全URL取得 ==========

async def async_get_all_urls(session, domain):
    """CDX APIでドメインのアーカイブ済み全URLを取得（URLごとに最新1件）"""
    params = [
        ("url", f"{domain}/*"),
        ("output", "json"),
        ("fl", "original,timestamp,statuscode,mimetype"),
        ("filter", "statuscode:200"),
        ("filter", "mimetype:text/html"),
        ("collapse", "urlkey"),  # URLごとに最新1件だけ
        ("limit", "5000"),
    ]
    try:
        async with session.get(CDX_API, params=params,
                               timeout=aiohttp.ClientTimeout(total=60)) as resp:
            data = await resp.json(content_type=None)
            if not data or len(data) <= 1:
                return []
            # data[0] はヘッダ行
            results = []
            for row in data[1:]:
                original, timestamp, status, mimetype = row[0], row[1], row[2], row[3]
                if not should_skip_url(original):
                    results.append({"url": original, "timestamp": timestamp})
            return results
    except Exception as e:
        print(f"  CDX API エラー: {e}")
        return []


# ========== ページメタデータ取得 ==========

async def async_fetch_metadata(session, sem, entry, idx, total):
    """Wayback Machineからページを取得し、メタデータを抽出"""
    async with sem:
        url = entry["url"]
        timestamp = entry["timestamp"]
        wb_url = f"{WAYBACK_URL}/{timestamp}id_/{url}"

        print(f"[{idx}/{total}] {url}")
        try:
            async with session.get(wb_url,
                                   timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC)) as resp:
                if resp.status != 200:
                    print(f"  → HTTP {resp.status}")
                    return {
                        "url": url, "timestamp": timestamp,
                        "title": "", "meta_description": "",
                        "h1": "", "h2": "", "h3": "",
                        "body_text": "", "note": f"HTTP {resp.status}",
                    }
                chunk = await resp.content.read(200000)
                html = decode_html(chunk)

                title = extract_title(html)
                desc = extract_meta_description(html)
                h1 = extract_headings(html, "h1")
                h2 = extract_headings(html, "h2")
                h3 = extract_headings(html, "h3")
                body_text = extract_body_text(html)

                short = title[:50] if title else "(なし)"
                print(f"  → title: {short} | text: {len(body_text)}文字")
                return {
                    "url": url, "timestamp": timestamp,
                    "title": title, "meta_description": desc,
                    "h1": h1, "h2": h2, "h3": h3,
                    "body_text": body_text, "note": "",
                }
        except asyncio.TimeoutError:
            print(f"  → タイムアウト")
            return {
                "url": url, "timestamp": timestamp,
                "title": "", "meta_description": "",
                "h1": "", "h2": "", "h3": "",
                "body_text": "", "note": "タイムアウト",
            }
        except Exception as e:
            print(f"  → エラー: {e}")
            return {
                "url": url, "timestamp": timestamp,
                "title": "", "meta_description": "",
                "h1": "", "h2": "", "h3": "",
                "body_text": "", "note": str(e)[:50],
            }


async def async_main(domain, output_path):
    """メイン処理"""
    headers = {"User-Agent": "Mozilla/5.0 (wayback-page-metadata-checker)"}

    async with aiohttp.ClientSession(headers=headers) as session:
        # 1. CDX APIで全URL取得
        print(f"\n=== CDX APIで全URL取得中: {domain} ===")
        entries = await async_get_all_urls(session, domain)

        if not entries:
            print("アーカイブされたページが見つかりませんでした")
            return []

        print(f"  → {len(entries)} ページ発見\n")

        # 2. 各ページのメタデータ取得
        print(f"=== メタデータ取得中 ===")
        sem = asyncio.Semaphore(CONCURRENCY)
        tasks = [
            async_fetch_metadata(session, sem, entry, i + 1, len(entries))
            for i, entry in enumerate(entries)
        ]

        results = []
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)

            if len(results) % 20 == 0:
                write_csv(results, output_path)
                print(f"  >>> 途中保存 ({len(results)}/{len(entries)}件)")

    return results


# ========== sync版フォールバック ==========

def sync_get_all_urls(domain):
    """同期版: CDX APIで全URL取得"""
    import urllib.request
    import urllib.parse

    params = urllib.parse.urlencode([
        ("url", f"{domain}/*"),
        ("output", "json"),
        ("fl", "original,timestamp,statuscode,mimetype"),
        ("filter", "statuscode:200"),
        ("filter", "mimetype:text/html"),
        ("collapse", "urlkey"),
        ("limit", "5000"),
    ])
    url = f"{CDX_API}?{params}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (wayback-page-metadata-checker)"
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            if not data or len(data) <= 1:
                return []
            results = []
            for row in data[1:]:
                original, timestamp = row[0], row[1]
                if not should_skip_url(original):
                    results.append({"url": original, "timestamp": timestamp})
            return results
    except Exception as e:
        print(f"CDX API エラー: {e}")
        return []


def sync_fetch_metadata(entry):
    """同期版: ページメタデータ取得"""
    import urllib.request

    url = entry["url"]
    timestamp = entry["timestamp"]
    wb_url = f"{WAYBACK_URL}/{timestamp}id_/{url}"

    try:
        req = urllib.request.Request(wb_url, headers={
            "User-Agent": "Mozilla/5.0 (wayback-page-metadata-checker)"
        })
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            chunk = resp.read(200000)
            html = decode_html(chunk)
            return {
                "url": url, "timestamp": timestamp,
                "title": extract_title(html),
                "meta_description": extract_meta_description(html),
                "h1": extract_headings(html, "h1"),
                "h2": extract_headings(html, "h2"),
                "h3": extract_headings(html, "h3"),
                "body_text": extract_body_text(html),
                "note": "",
            }
    except Exception as e:
        return {
            "url": url, "timestamp": timestamp,
            "title": "", "meta_description": "",
            "h1": "", "h2": "", "h3": "",
            "body_text": "", "note": str(e)[:50],
        }


# ========== CSV出力 ==========

def write_csv(results, output_path):
    """結果をCSVに書き出す"""
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["URL", "アーカイブ日", "title", "meta_description", "H1", "H2", "H3", "body_text", "備考"])
        for r in sorted(results, key=lambda x: x["url"]):
            ts = r["timestamp"]
            date_str = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if len(ts) >= 8 else ts
            writer.writerow([
                r["url"], date_str,
                r["title"], r["meta_description"],
                r["h1"], r["h2"], r["h3"],
                r["body_text"], r["note"],
            ])


# ========== Markdown出力 ==========

def write_markdown(results, output_path, domain):
    """結果をMarkdownファイルに書き出す"""
    sorted_results = sorted(results, key=lambda x: x["url"])
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {domain} 過去ページメタデータ\n\n")
        f.write(f"Wayback Machine から取得（{len(sorted_results)} ページ）\n\n")
        f.write("---\n\n")

        for r in sorted_results:
            ts = r["timestamp"]
            date_str = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if len(ts) >= 8 else ts
            if r["note"] and not r["title"]:
                continue  # 取得失敗ページはスキップ

            f.write(f"## {r['title'] or r['url']}\n\n")
            f.write(f"- **URL**: {r['url']}\n")
            f.write(f"- **アーカイブ日**: {date_str}\n")
            if r["meta_description"]:
                f.write(f"- **meta description**: {r['meta_description']}\n")
            if r["h1"]:
                f.write(f"- **H1**: {r['h1']}\n")
            if r["h2"]:
                f.write(f"- **H2**: {r['h2']}\n")
            if r["h3"]:
                f.write(f"- **H3**: {r['h3']}\n")
            f.write("\n")

            if r["body_text"]:
                # 本文は長いので先頭1000文字に制限
                body = r["body_text"]
                if len(body) > 1000:
                    body = body[:1000] + "..."
                f.write("<details>\n<summary>本文テキスト（クリックで展開）</summary>\n\n")
                f.write(f"{body}\n\n")
                f.write("</details>\n\n")

            f.write("---\n\n")


def main():
    parser = argparse.ArgumentParser(description="Wayback Machine 全ページメタデータ取得")
    parser.add_argument("domain", help="対象ドメイン（例: kanazawa-hp.com）")
    parser.add_argument("-o", "--output", default="wayback_pages.csv", help="出力CSVファイル名")
    args = parser.parse_args()

    domain = re.sub(r'^https?://', '', args.domain).rstrip('/')

    print(f"対象ドメイン: {domain}")
    print(f"出力先: {args.output}")

    if HAS_AIOHTTP:
        print("モード: async (aiohttp)\n")
        results = asyncio.run(async_main(domain, args.output))
    else:
        print("モード: sync (urllib)\n")
        print(f"=== CDX APIで全URL取得中: {domain} ===")
        entries = sync_get_all_urls(domain)
        if not entries:
            print("アーカイブされたページが見つかりませんでした")
            sys.exit(0)

        print(f"  → {len(entries)} ページ発見\n")

        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = []
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
            futures = {executor.submit(sync_fetch_metadata, e): e for e in entries}
            for i, future in enumerate(as_completed(futures)):
                result = future.result()
                results.append(result)
                short = result["title"][:40] if result["title"] else "(なし)"
                print(f"[{i+1}/{len(entries)}] {result['url']} → {short}")
                if len(results) % 20 == 0:
                    write_csv(results, args.output)

    if not results:
        print("結果なし")
        sys.exit(0)

    write_csv(results, args.output)

    # Markdown出力
    md_path = args.output.rsplit(".", 1)[0] + ".md"
    write_markdown(results, md_path, domain)

    # サマリ
    ok = [r for r in results if not r["note"]]
    failed = [r for r in results if r["note"]]
    print(f"\n{'='*60}")
    print(f"完了: {len(results)} ページ（成功: {len(ok)} / 失敗: {len(failed)}）")
    print(f"結果CSV: {args.output}")
    print(f"結果MD:  {md_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
