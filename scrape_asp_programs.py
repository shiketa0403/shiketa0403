#!/usr/bin/env python3
"""
ASPプログラム一覧スクレイピングスクリプト

使い方:
  1. python -m playwright install chromium   （初回のみ）
  2. python scrape_asp_programs.py --asp a8
  3. ブラウザが開くので手動でログイン
  4. ログイン後、ターミナルでEnterキーを押す
  5. 自動で全ページ巡回してCSV出力（csv/a8_programs.csv）

対応ASP: a8（実装済み） / accesstrade, afb, moshimo（HTML取得後に対応）
"""

import argparse
import csv
import os
import sys
import time

from playwright.sync_api import sync_playwright

OUTPUT_DIR = "csv"

# A8新管理画面の検索URL（pageSize=100で1ページ100件表示）
A8_SEARCH_URL = "https://media-console.a8.net/program/search/keyword?pageNo={page}&pageSize=100&sortKey=NORMAL"
A8_LOGIN_URL = "https://www.a8.net/"


def _extract_a8_cards(page):
    """現在表示中のページからプログラムカード情報を抽出"""
    results = []
    cards = page.query_selector_all("div.pgCard")
    for card in cards:
        name_el = card.query_selector("h3.pgName")
        ec_el = card.query_selector("p.ecName")
        status_el = card.query_selector(".pgStatus")

        program_name = name_el.inner_text().strip() if name_el else ""
        company_name = ec_el.inner_text().strip() if ec_el else ""
        status = status_el.inner_text().strip() if status_el else ""

        program_id = ""
        category = ""
        reward = ""
        rows = card.query_selector_all("table tr")
        for tr in rows:
            th = tr.query_selector("th")
            td = tr.query_selector("td")
            if not th or not td:
                continue
            th_text = th.inner_text().strip()
            td_text = td.inner_text().strip()
            if "プログラムID" in th_text:
                program_id = td_text
            elif "カテゴリ" in th_text:
                category = td_text
            elif "成果報酬" in th_text:
                reward = td_text

        if program_name:
            results.append({
                "program_name": program_name,
                "company_name": company_name,
                "program_id": program_id,
                "category": category,
                "reward": reward,
                "status": status,
                "asp": "a8",
            })
    return results


def _goto_a8_search(page):
    """検索ページ1に到達する（SPAの/homeリダイレクト対策でリトライ）"""
    url = A8_SEARCH_URL.format(page=1)
    for attempt in range(8):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  ナビゲーション中断（リトライ {attempt + 1}/8）")
        time.sleep(3)
        # プログラムカードが出ていれば成功
        try:
            page.wait_for_selector("h3.pgName", timeout=8000)
            return True
        except Exception:
            cur = page.url
            print(f"  検索ページ未到達（現在地: {cur}）リトライ {attempt + 1}/8")
            time.sleep(2)
    return False


def scrape_a8(page):
    """A8.netのプログラム一覧を全ページ取得（media-console.a8.net、SPA）"""
    programs = []

    # 検索ページ1に到達（リトライ込み）
    if not _goto_a8_search(page):
        print("  検索ページに到達できませんでした。ログイン状態を確認してください。")
        return programs

    page_num = 1
    max_pages = 500
    prev_first_id = None

    while page_num <= max_pages:
        print(f"  ページ {page_num} 取得中...")

        try:
            page.wait_for_selector("h3.pgName", timeout=15000)
        except Exception:
            print(f"  プログラムが見つかりません（終了）")
            break

        # 重複ページ検出（前ページと同じ先頭IDなら更新されていない）
        cards = _extract_a8_cards(page)
        if not cards:
            print(f"  カード0件（終了）")
            break

        first_id = cards[0].get("program_id", "")
        if first_id and first_id == prev_first_id:
            # ページ送りが反映されるまで少し待って再取得
            time.sleep(2)
            cards = _extract_a8_cards(page)
            first_id = cards[0].get("program_id", "") if cards else ""
            if first_id == prev_first_id:
                print(f"  ページが更新されていません（最終ページと判断、終了）")
                break

        programs.extend(cards)
        prev_first_id = first_id
        print(f"  {len(cards)}件取得（累計: {len(programs)}件）")

        # 次へボタンを探す
        next_btn = page.query_selector("button.pagerNext")
        if not next_btn:
            print(f"  次へボタンなし（最終ページ、終了）")
            break

        # disabled なら最終ページ
        is_disabled = next_btn.get_attribute("disabled")
        if is_disabled is not None:
            print(f"  次へボタンが無効（最終ページ、終了）")
            break

        # 次ページへ
        try:
            next_btn.click()
        except Exception as e:
            print(f"  次へクリック失敗: {e}（終了）")
            break

        time.sleep(2)
        page_num += 1

    return programs


# --- 他ASPは実際のHTML構造取得後に実装 ---
def scrape_accesstrade(page):
    print("  アクセストレードは未実装です。HTMLを取得後に対応します。")
    return []


def scrape_afb(page):
    print("  afbは未実装です。HTMLを取得後に対応します。")
    return []


def scrape_moshimo(page):
    print("  もしもは未実装です。HTMLを取得後に対応します。")
    return []


SCRAPERS = {
    "a8": scrape_a8,
    "accesstrade": scrape_accesstrade,
    "afb": scrape_afb,
    "moshimo": scrape_moshimo,
}

LOGIN_URLS = {
    "a8": A8_LOGIN_URL,
    "accesstrade": "https://member.accesstrade.net/atv3/login.html",
    "afb": "https://www.afi-b.com/login/",
    "moshimo": "https://af.moshimo.com/af/shop/login",
}

OUTPUT_FILES = {
    "a8": "a8_programs.csv",
    "accesstrade": "accesstrade_programs.csv",
    "afb": "afb_programs.csv",
    "moshimo": "moshimo_programs.csv",
}

FIELDNAMES = ["program_name", "company_name", "program_id", "category", "reward", "status", "asp"]


def main():
    parser = argparse.ArgumentParser(description="ASPプログラム一覧スクレイピング")
    parser.add_argument("--asp", required=True, choices=["a8", "accesstrade", "afb", "moshimo"],
                        help="対象ASP")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    asp_key = args.asp

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        login_url = LOGIN_URLS[asp_key]
        print(f"\n=== {asp_key} ===")
        print(f"ログインページを開きます: {login_url}")
        page.goto(login_url, wait_until="domcontentloaded", timeout=30000)

        input(f"\n{asp_key} にログインしてください。\nログイン完了後、このターミナルでEnterキーを押してください...")

        print("プログラム一覧を取得開始...")
        scraper = SCRAPERS[asp_key]
        programs = scraper(page)

        if programs:
            output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILES[asp_key])
            with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()
                writer.writerows(programs)
            print(f"\n✅ 完了: {len(programs)}件 → {output_path}")
            print(f"このCSVファイルをチャットにアップロードしてください。")
        else:
            print(f"\n⚠️ 取得できませんでした。")

        input("\nEnterキーでブラウザを閉じます...")
        browser.close()


if __name__ == "__main__":
    main()
