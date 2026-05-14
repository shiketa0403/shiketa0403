#!/usr/bin/env python3
"""
sharebatake.com 探査スクリプト（使い捨て）

目的:
  - エリア一覧ページ（例: 大田区）と、そこから辿った農園詳細ページの
    構造を把握する。
  - 本番のスクレイパー設計に必要な「実際に取れるラベル・値・画像URL」を
    artifact として吐き出す。

出力（--out-dir 配下、既定 probe_out/）:
  - list.html  / list.png   : エリア一覧ページの生HTMLとフルスクショ
  - detail.html / detail.png: 1農園分の詳細ページの生HTMLとフルスクショ
  - summary.txt             : 抽出できた要素のサマリー（人間が読む用）
  - farm_links.txt          : 一覧から拾った農園詳細URLの一覧

使い方:
  # エリア一覧URLを直接渡す
  python probe_sharebatake.py --list-url https://www.sharebatake.com/.../ota/

  # 渡さない場合はトップから「大田区」リンクを探して辿る
  python probe_sharebatake.py
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

BASE_URL = "https://www.sharebatake.com/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def render_page(page, url, wait_ms=3500):
    """1ページ取得して HTML を返す。失敗時は空文字。"""
    print(f"[load] {url}", flush=True)
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(wait_ms)
    # 遅延読み込み対策のスクロール
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1500)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(800)
    return page.content()


def discover_otaku_list_url(page):
    """トップから「大田区」を含むリンクを探す。"""
    html = render_page(page, BASE_URL)
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if "大田区" in text:
            candidates.append((text, urljoin(BASE_URL, a["href"])))
    if not candidates:
        # 都道府県インデックスを経由する必要があるかも
        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            if "東京" in text and "/" not in a["href"]:
                continue
            if "東京" in text:
                print(f"  候補(東京): {text} -> {a['href']}", flush=True)
    print(f"  大田区候補: {len(candidates)}件", flush=True)
    for t, u in candidates[:5]:
        print(f"    - {t} -> {u}", flush=True)
    if not candidates:
        return None
    # /ota/ 系のパスを優先
    candidates.sort(key=lambda x: 0 if re.search(r"ota|otaku|/13111", x[1]) else 1)
    return candidates[0][1]


def extract_farm_links(html, base_url):
    """一覧ページの HTML から農園詳細ページURLらしきものを抽出。"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)
        if href.startswith("#") or href.startswith("javascript:"):
            continue
        absolute = urljoin(base_url, href)
        if urlparse(absolute).netloc != urlparse(BASE_URL).netloc:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        # 「詳細」ボタンや、農園名らしきものを優先
        score = 0
        if "詳細" in text:
            score += 5
        if "シェア畑" in text:
            score += 3
        path = urlparse(absolute).path
        if re.search(r"/(farm|garden|sharebatake)/", path):
            score += 3
        if path.count("/") >= 3:  # 深いパスは詳細ページの可能性高
            score += 1
        links.append((score, absolute, text[:60]))
    links.sort(reverse=True)
    return links


def summarize_page(html, label):
    """HTMLから抽出できた要素を人間用にまとめる。"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    lines = [f"===== {label} =====", ""]

    # title / meta
    if soup.title:
        lines.append(f"<title>: {soup.title.get_text(strip=True)}")
    desc = soup.find("meta", attrs={"name": "description"})
    if desc and desc.get("content"):
        lines.append(f"<meta description>: {desc['content'][:200]}")
    og_image = soup.find("meta", attrs={"property": "og:image"})
    if og_image and og_image.get("content"):
        lines.append(f"<og:image>: {og_image['content']}")
    lines.append("")

    # 見出し
    for tag in ("h1", "h2", "h3"):
        for h in soup.find_all(tag):
            t = h.get_text(" ", strip=True)
            if t:
                lines.append(f"<{tag}> {t}")
    lines.append("")

    # JSON-LD
    for i, s in enumerate(soup.find_all("script", type="application/ld+json")):
        try:
            data = json.loads(s.string or "{}")
            lines.append(f"[JSON-LD #{i}]")
            lines.append(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
            lines.append("")
        except Exception as e:
            lines.append(f"[JSON-LD #{i}] parse error: {e}")

    # dl/dt/dd
    lines.append("--- dl/dt/dd pairs ---")
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            lines.append(
                f"  [{dt.get_text(' ', strip=True)[:30]}] "
                f"= {dd.get_text(' ', strip=True)[:200]}"
            )
    lines.append("")

    # table th/td
    lines.append("--- table th/td pairs ---")
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if th and td:
                lines.append(
                    f"  [{th.get_text(' ', strip=True)[:30]}] "
                    f"= {td.get_text(' ', strip=True)[:200]}"
                )
    lines.append("")

    # 画像
    lines.append("--- <img> URLs (上位20件) ---")
    imgs = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        alt = img.get("alt", "")
        if src:
            imgs.append((src, alt))
    for src, alt in imgs[:20]:
        lines.append(f"  {src}   [alt: {alt}]")
    lines.append(f"  (total: {len(imgs)} 件)")
    lines.append("")

    # 詳細ページ向け: ラベル/値が div ベースで組まれているケース
    lines.append("--- .farminfo_subtitle（見出し）と近傍テキスト ---")
    for sub in soup.select(".farminfo_subtitle"):
        label = sub.get_text(" ", strip=True)
        # 後続のテキストを兄弟要素から拾う
        nxt = sub.find_next_sibling()
        value = nxt.get_text(" ", strip=True)[:300] if nxt else ""
        lines.append(f"  [{label[:30]}] => {value}")
    lines.append("")

    lines.append("--- .tdL / .tdR ペア ---")
    tdls = soup.select(".tdL")
    tdrs = soup.select(".tdR")
    for tdl, tdr in zip(tdls, tdrs):
        lines.append(
            f"  [{tdl.get_text(' ', strip=True)[:30]}] "
            f"= {tdr.get_text(' ', strip=True)[:300]}"
        )
    lines.append("")

    lines.append("--- .area / .answer ペア（あれば） ---")
    areas = soup.select(".area")
    answers = soup.select(".answer")
    for a, b in zip(areas, answers):
        lines.append(
            f"  [{a.get_text(' ', strip=True)[:30]}] "
            f"= {b.get_text(' ', strip=True)[:300]}"
        )
    lines.append("")

    lines.append("--- <iframe> src 一覧（Google Maps 候補） ---")
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src") or iframe.get("data-src") or ""
        lines.append(f"  {src}")
    lines.append("")

    lines.append("--- 「円」を含むテキスト行（料金候補） ---")
    body_text = soup.get_text("\n")
    for raw in body_text.split("\n"):
        line = raw.strip()
        if "円" in line and 2 <= len(line) <= 120:
            lines.append(f"  {line}")
    lines.append("")

    # 各種クラス・タグの分布
    lines.append("--- class attribute 上位 ---")
    from collections import Counter
    classes = Counter()
    for el in soup.find_all(class_=True):
        for c in el.get("class", []):
            classes[c] += 1
    for c, n in classes.most_common(30):
        lines.append(f"  {n:4d}  .{c}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-url", default="", help="エリア一覧URL（空ならトップから大田区を探す）")
    parser.add_argument("--out-dir", default="probe_out")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
            user_agent=USER_AGENT,
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => false });"
        )
        page = context.new_page()

        # 1) エリア一覧URLを確定
        list_url = args.list_url
        if not list_url:
            print("--list-url 未指定。トップから大田区リンクを探します…", flush=True)
            list_url = discover_otaku_list_url(page)
            if not list_url:
                print("! 大田区リンクが見つかりません。トップHTMLだけ保存して終了します。", flush=True)
                (out_dir / "top.html").write_text(render_page(page, BASE_URL), encoding="utf-8")
                page.screenshot(path=str(out_dir / "top.png"), full_page=True)
                browser.close()
                sys.exit(2)
        print(f"\n>>> 一覧URL: {list_url}\n", flush=True)

        # 2) 一覧ページ取得
        list_html = render_page(page, list_url)
        (out_dir / "list.html").write_text(list_html, encoding="utf-8")
        page.screenshot(path=str(out_dir / "list.png"), full_page=True)

        # 3) 一覧から農園リンクを抽出
        farm_links = extract_farm_links(list_html, list_url)
        with open(out_dir / "farm_links.txt", "w", encoding="utf-8") as f:
            for score, url, text in farm_links[:40]:
                f.write(f"[score={score}] {url}    -- {text}\n")
        print(f"農園URL候補: {len(farm_links)}件（上位5を表示）", flush=True)
        for s, u, t in farm_links[:5]:
            print(f"  [score={s}] {u}  -- {t}", flush=True)

        # 4) 最有力候補で詳細ページ取得
        detail_url = next((u for s, u, t in farm_links if s >= 3), None)
        if not detail_url and farm_links:
            detail_url = farm_links[0][1]
        summary_parts = [summarize_page(list_html, f"LIST PAGE: {list_url}")]

        if detail_url:
            print(f"\n>>> 詳細URL: {detail_url}\n", flush=True)
            detail_html = render_page(page, detail_url)
            (out_dir / "detail.html").write_text(detail_html, encoding="utf-8")
            page.screenshot(path=str(out_dir / "detail.png"), full_page=True)
            summary_parts.append(summarize_page(detail_html, f"DETAIL PAGE: {detail_url}"))
        else:
            print("! 詳細URLが拾えませんでした", flush=True)

        (out_dir / "summary.txt").write_text("\n\n".join(summary_parts), encoding="utf-8")
        browser.close()

    print(f"\n=== 完了: {out_dir}/ に保存 ===")


if __name__ == "__main__":
    main()
