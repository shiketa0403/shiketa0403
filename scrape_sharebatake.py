#!/usr/bin/env python3
"""
シェア畑（https://www.sharebatake.com/）のスクレイパー

トップページから農園詳細ページのURLを発見し、各ページから以下を抽出して
CSV (csv/sharebatake_raw.csv) に出力する：

  url, name, prefecture, city, address, fee, area_size,
  features, access, facilities, official_url

サイトがBot対策（Cloudflare等）を有効にしているため、Playwrightで
ヘッドレスChromeを起動して取得する。

使い方:
  # 全件
  python scrape_sharebatake.py

  # 件数を絞って試す
  python scrape_sharebatake.py --max-farms 10

  # 出力先を変更
  python scrape_sharebatake.py --output csv/sharebatake_raw.csv
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

BASE_URL = "https://www.sharebatake.com/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# 詳細ページとみなすパスのパターン（サイトの実構造を確認後に微調整可）
FARM_URL_PATTERNS = [
    re.compile(r"^/farm/[^/]+/?$"),
    re.compile(r"^/farms/[^/]+/?$"),
    re.compile(r"^/[a-z0-9_-]+/farm/[^/]+/?$"),
]

# 47都道府県（住所先頭からの抽出用）
PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県",
    "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]

# 詳細ページから抽出するラベル候補
LABEL_KEYS = {
    "fee": ["利用料金", "料金", "月額", "ご利用料金", "利用料"],
    "area_size": ["区画サイズ", "区画", "区画面積", "1区画", "面積"],
    "address": ["住所", "所在地", "アクセス（住所）"],
    "access": ["アクセス", "最寄駅", "交通"],
    "facilities": ["設備", "備品", "サポート", "提供サービス"],
    "features": ["特徴", "おすすめポイント", "PR"],
    "official_url": ["公式サイト", "URL", "ホームページ"],
}


def fetch_html(page, url, wait_ms=2500):
    """Playwright で1ページ取得し HTML を返す。失敗時は空文字。"""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(wait_ms)
        return page.content()
    except Exception as e:
        print(f"  ! fetch失敗: {url} ({e})", file=sys.stderr)
        return ""


def discover_farm_urls(page, seed_urls, max_pages=30):
    """シード URL から再帰的に農園詳細ページの URL を集める。

    BFS で /farm/ 系のリンクを集めるが、過剰巡回を防ぐため max_pages で打ち切る。
    """
    from bs4 import BeautifulSoup

    visited = set()
    found = []
    queue = list(seed_urls)

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        print(f"[discover] {url}")
        html = fetch_html(page, url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("javascript:") or href.startswith("#"):
                continue
            absolute = urljoin(url, href)
            if urlparse(absolute).netloc != urlparse(BASE_URL).netloc:
                continue
            path = urlparse(absolute).path
            if any(p.match(path) for p in FARM_URL_PATTERNS):
                if absolute not in found:
                    found.append(absolute)
            elif "/farm" in path or "/area" in path or "/pref" in path:
                # 中間ページ（地域・都道府県インデックス）も探索
                if absolute not in visited and len(visited) < max_pages:
                    queue.append(absolute)
        time.sleep(0.5)

    return found


def extract_with_jsonld(soup):
    """JSON-LD があれば name / address / url を取り出す。"""
    out = {}
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("@type", "")
            if t in ("LocalBusiness", "Organization", "Place") or "Place" in str(t):
                out.setdefault("name", item.get("name", ""))
                addr = item.get("address")
                if isinstance(addr, dict):
                    out.setdefault("address", addr.get("streetAddress") or addr.get("addressLocality", ""))
                elif isinstance(addr, str):
                    out.setdefault("address", addr)
                out.setdefault("official_url", item.get("url", ""))
    return out


def extract_label_value_pairs(soup):
    """<dl><dt><dd> や <table><th><td> からラベル・値ペアを集める。"""
    pairs = []
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            pairs.append((dt.get_text(" ", strip=True), dd.get_text(" ", strip=True)))
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if th and td:
                pairs.append((th.get_text(" ", strip=True), td.get_text(" ", strip=True)))
    return pairs


def parse_farm_page(html, url):
    """農園詳細ページの HTML から構造化データを抽出する。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    data = {
        "url": url,
        "name": "",
        "prefecture": "",
        "city": "",
        "address": "",
        "fee": "",
        "area_size": "",
        "features": "",
        "access": "",
        "facilities": "",
        "official_url": "",
    }

    # 1) JSON-LD から優先取得
    jsonld = extract_with_jsonld(soup)
    for k, v in jsonld.items():
        if v:
            data[k] = v

    # 2) <h1> から農園名
    if not data["name"]:
        h1 = soup.find("h1")
        if h1:
            data["name"] = h1.get_text(" ", strip=True)
    if not data["name"]:
        title = soup.find("title")
        if title:
            data["name"] = re.split(r"[\|｜\-－]", title.get_text(strip=True))[0].strip()

    # 3) ラベル・値ペアから埋める
    pairs = extract_label_value_pairs(soup)
    for label, value in pairs:
        for key, candidates in LABEL_KEYS.items():
            if data[key]:
                continue
            if any(c in label for c in candidates):
                data[key] = value
                break

    # 4) 住所から都道府県・市区町村を抽出
    if data["address"]:
        for pref in PREFECTURES:
            if data["address"].startswith(pref):
                data["prefecture"] = pref
                rest = data["address"][len(pref):]
                m = re.match(r"([^\s\d０-９]+?[市区町村郡])", rest)
                if m:
                    data["city"] = m.group(1)
                break

    # 値の長さを丸める（CSV肥大化を防ぐ）
    for k in ("features", "facilities", "access"):
        if data[k] and len(data[k]) > 400:
            data[k] = data[k][:400] + "..."

    return data


def run(seed_urls, output_path, max_farms, max_discover_pages):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
            user_agent=USER_AGENT,
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => false });"
        )
        page = context.new_page()

        farm_urls = discover_farm_urls(page, seed_urls, max_pages=max_discover_pages)
        print(f"\n発見した農園URL: {len(farm_urls)}件")
        if max_farms:
            farm_urls = farm_urls[:max_farms]
            print(f"  (--max-farms により {len(farm_urls)} 件に絞り込み)")

        rows = []
        for i, url in enumerate(farm_urls, 1):
            print(f"[{i}/{len(farm_urls)}] {url}")
            html = fetch_html(page, url)
            if not html:
                continue
            row = parse_farm_page(html, url)
            if not row["name"]:
                print("  ! 農園名が取れず、スキップ")
                continue
            print(f"  -> {row['name']} / {row['prefecture']}{row['city']}")
            rows.append(row)
            time.sleep(0.7)

        browser.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "url", "name", "prefecture", "city", "address",
        "fee", "area_size", "features", "access", "facilities", "official_url",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"\n書き出し: {output_path} ({len(rows)}件)")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="シェア畑スクレイパー")
    parser.add_argument(
        "--seed", action="append", default=[],
        help="探索開始URL（複数可）。省略時はトップページ。",
    )
    parser.add_argument(
        "--output", default="csv/sharebatake_raw.csv",
        help="出力CSVパス",
    )
    parser.add_argument("--max-farms", type=int, default=0, help="取得農園数の上限（0=無制限）")
    parser.add_argument("--max-discover-pages", type=int, default=40, help="探索ページ数上限")
    args = parser.parse_args()

    seeds = args.seed or [BASE_URL, urljoin(BASE_URL, "/farm/")]
    count = run(
        seed_urls=seeds,
        output_path=Path(args.output),
        max_farms=args.max_farms,
        max_discover_pages=args.max_discover_pages,
    )
    if count == 0:
        print("! 1件も取得できませんでした。サイト構造変更やBot対策の影響を確認してください。", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
