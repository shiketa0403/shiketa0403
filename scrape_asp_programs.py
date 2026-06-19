#!/usr/bin/env python3
"""
ASPプログラム一覧スクレイピングスクリプト

使い方:
  1. pip install playwright && playwright install chromium
  2. python scrape_asp_programs.py --asp a8
  3. ブラウザが開くので手動でログイン
  4. ログイン後、ターミナルでEnterキーを押す
  5. 自動で全ページ巡回してCSV出力

対応ASP: a8, accesstrade, afb, moshimo
"""

import argparse
import csv
import os
import sys
import time

from playwright.sync_api import sync_playwright

OUTPUT_DIR = "csv"

ASP_CONFIG = {
    "a8": {
        "name": "A8.net",
        "login_url": "https://www.a8.net/as/as_login/",
        "search_url": "https://www.a8.net/as/as_prg_s/?sort=new&category=all&appeal=all&payout=all&keyword=&searchMethod=program&page=1&perPage=100",
        "output": "a8_programs.csv",
    },
    "accesstrade": {
        "name": "アクセストレード",
        "login_url": "https://member.accesstrade.net/atv3/login.html",
        "search_url": "https://member.accesstrade.net/atv3/search_program.html",
        "output": "accesstrade_programs.csv",
    },
    "afb": {
        "name": "afb",
        "login_url": "https://www.afi-b.com/partner/login",
        "search_url": "https://www.afi-b.com/partner/search/program",
        "output": "afb_programs.csv",
    },
    "moshimo": {
        "name": "もしもアフィリエイト",
        "login_url": "https://af.moshimo.com/af/shop/login",
        "search_url": "https://af.moshimo.com/af/shop/promotion/search",
        "output": "moshimo_programs.csv",
    },
}


def scrape_a8(page):
    """A8.netのプログラム一覧を全ページ取得"""
    programs = []
    page_num = 1

    # まず検索ページに遷移（全プログラム、100件表示）
    search_url = ASP_CONFIG["a8"]["search_url"]
    page.goto(search_url, wait_until="networkidle", timeout=30000)
    time.sleep(2)

    while True:
        print(f"  ページ {page_num} 取得中...")

        # プログラム名を取得（A8のプログラム一覧のセレクタ）
        # A8の検索結果ページでプログラム名が表示される要素を探す
        items = page.query_selector_all("span.programTitle, a.programDetailLink, .prg-name, .program-name, h3.program-title")

        if not items:
            # フォールバック: テーブル内のリンクやテキストを取得
            items = page.query_selector_all("table.searchResult td a, .search-result-item .title, .program-list-item .name")

        if not items:
            # さらにフォールバック: ページ内の全テキストからプログラム名っぽいものを取得
            print(f"  セレクタが見つかりません。ページのHTMLを確認します...")
            # デバッグ用: ページのタイトルとURL
            print(f"  URL: {page.url}")
            print(f"  Title: {page.title()}")
            # HTMLの一部を保存
            html = page.content()
            debug_path = os.path.join(OUTPUT_DIR, "a8_debug.html")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  デバッグHTML保存: {debug_path}")
            print(f"  手動でHTMLを確認してセレクタを調整してください")
            break

        for item in items:
            text = item.inner_text().strip()
            if text and len(text) > 2:
                programs.append({"program_name": text, "asp": "a8"})

        print(f"  {len(items)}件取得（累計: {len(programs)}件）")

        # 次のページへ
        next_btn = page.query_selector("a.nextPage, .pagination .next a, a[rel='next'], .pager-next a")
        if next_btn:
            next_btn.click()
            time.sleep(2)
            page.wait_for_load_state("networkidle", timeout=15000)
            page_num += 1
        else:
            print(f"  最終ページ到達（全{page_num}ページ）")
            break

    return programs


def scrape_accesstrade(page):
    """アクセストレードのプログラム一覧を全ページ取得"""
    programs = []
    page_num = 1

    page.goto(ASP_CONFIG["accesstrade"]["search_url"], wait_until="networkidle", timeout=30000)
    time.sleep(2)

    # 検索ボタンをクリック（全件検索）
    search_btn = page.query_selector("button[type='submit'], input[type='submit'], .search-btn, #searchBtn")
    if search_btn:
        search_btn.click()
        time.sleep(3)
        page.wait_for_load_state("networkidle", timeout=15000)

    while True:
        print(f"  ページ {page_num} 取得中...")

        items = page.query_selector_all(".program-name, .prg-name, td.program a, .search-result .title")

        if not items:
            html = page.content()
            debug_path = os.path.join(OUTPUT_DIR, "accesstrade_debug.html")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  セレクタが見つかりません。デバッグHTML保存: {debug_path}")
            break

        for item in items:
            text = item.inner_text().strip()
            if text and len(text) > 2:
                programs.append({"program_name": text, "asp": "accesstrade"})

        print(f"  {len(items)}件取得（累計: {len(programs)}件）")

        next_btn = page.query_selector("a.next, .pagination .next a, a[rel='next']")
        if next_btn:
            next_btn.click()
            time.sleep(2)
            page.wait_for_load_state("networkidle", timeout=15000)
            page_num += 1
        else:
            break

    return programs


def scrape_afb(page):
    """afbのプログラム一覧を全ページ取得"""
    programs = []
    page_num = 1

    page.goto(ASP_CONFIG["afb"]["search_url"], wait_until="networkidle", timeout=30000)
    time.sleep(2)

    while True:
        print(f"  ページ {page_num} 取得中...")

        items = page.query_selector_all(".program-name, .prg-title, .promotion-name, td a.program-link")

        if not items:
            html = page.content()
            debug_path = os.path.join(OUTPUT_DIR, "afb_debug.html")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  セレクタが見つかりません。デバッグHTML保存: {debug_path}")
            break

        for item in items:
            text = item.inner_text().strip()
            if text and len(text) > 2:
                programs.append({"program_name": text, "asp": "afb"})

        print(f"  {len(items)}件取得（累計: {len(programs)}件）")

        next_btn = page.query_selector("a.next, .pagination .next a, a[rel='next']")
        if next_btn:
            next_btn.click()
            time.sleep(2)
            page.wait_for_load_state("networkidle", timeout=15000)
            page_num += 1
        else:
            break

    return programs


def scrape_moshimo(page):
    """もしもアフィリエイトのプログラム一覧を全ページ取得"""
    programs = []
    page_num = 1

    page.goto(ASP_CONFIG["moshimo"]["search_url"], wait_until="networkidle", timeout=30000)
    time.sleep(2)

    while True:
        print(f"  ページ {page_num} 取得中...")

        items = page.query_selector_all(".promotion-name, .program-title, .shop-name, td.promotion a")

        if not items:
            html = page.content()
            debug_path = os.path.join(OUTPUT_DIR, "moshimo_debug.html")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  セレクタが見つかりません。デバッグHTML保存: {debug_path}")
            break

        for item in items:
            text = item.inner_text().strip()
            if text and len(text) > 2:
                programs.append({"program_name": text, "asp": "moshimo"})

        print(f"  {len(items)}件取得（累計: {len(programs)}件）")

        next_btn = page.query_selector("a.next, .pagination .next a, a[rel='next']")
        if next_btn:
            next_btn.click()
            time.sleep(2)
            page.wait_for_load_state("networkidle", timeout=15000)
            page_num += 1
        else:
            break

    return programs


SCRAPERS = {
    "a8": scrape_a8,
    "accesstrade": scrape_accesstrade,
    "afb": scrape_afb,
    "moshimo": scrape_moshimo,
}


def main():
    parser = argparse.ArgumentParser(description="ASPプログラム一覧スクレイピング")
    parser.add_argument("--asp", required=True, choices=["a8", "accesstrade", "afb", "moshimo", "all"],
                        help="対象ASP（allで全ASP）")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    targets = list(SCRAPERS.keys()) if args.asp == "all" else [args.asp]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        for asp_key in targets:
            config = ASP_CONFIG[asp_key]
            print(f"\n=== {config['name']} ===")

            # ログインページを開く
            print(f"ログインページを開きます: {config['login_url']}")
            page.goto(config["login_url"], wait_until="networkidle", timeout=30000)

            input(f"\n{config['name']}にログインしてください。ログイン完了後、Enterキーを押してください...")

            # スクレイピング実行
            print("プログラム一覧を取得中...")
            scraper = SCRAPERS[asp_key]
            programs = scraper(page)

            if programs:
                output_path = os.path.join(OUTPUT_DIR, config["output"])
                with open(output_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=["program_name", "asp"])
                    writer.writeheader()
                    writer.writerows(programs)
                print(f"\n完了: {len(programs)}件 → {output_path}")
            else:
                print(f"\n取得できませんでした。デバッグHTMLを確認してセレクタを調整してください。")

        browser.close()

    print("\n=== 全ASP完了 ===")
    print("取得したCSVをアップロードしてください。VCデータと突合してASP対応表を作成します。")


if __name__ == "__main__":
    main()
