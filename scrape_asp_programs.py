#!/usr/bin/env python3
"""
ASPプログラム一覧スクレイピングスクリプト

使い方:
  1. python -m playwright install chromium   （初回のみ）
  2. python scrape_asp_programs.py --asp a8
  3. ブラウザが開くので手動でログイン
  4. ログイン後、ターミナルでEnterキーを押す
  5. 自動で全ページ巡回してCSV出力（csv/a8_programs.csv）

対応ASP: a8 / accesstrade / afb / moshimo（全て実装済み）
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


# --- アクセストレード（member.accesstrade.net、AJAXページング） ---
import re as _re


def _extract_at_cards(page):
    """現在表示中のアクセストレードのプログラムカードを抽出"""
    results = []
    cards = page.query_selector_all("section.program")
    for card in cards:
        name_el = card.query_selector("p.program_name")
        cat_el = card.query_selector("span.program_category")
        status_el = card.query_selector("label.label")

        raw_name = name_el.inner_text().strip() if name_el else ""
        # 「（1155209）案件名」形式 → IDと案件名を分離
        program_id = ""
        program_name = raw_name
        m = _re.match(r"^[（(]\s*(\d+)\s*[）)]\s*(.*)$", raw_name, _re.S)
        if m:
            program_id = m.group(1)
            program_name = m.group(2).strip()

        category = cat_el.inner_text().strip() if cat_el else ""
        status = status_el.inner_text().strip() if status_el else ""

        # 報酬（dl.program_hosyu の dt/dd を結合）
        reward_parts = []
        hosyu = card.query_selector("dl.program_hosyu")
        if hosyu:
            dts = hosyu.query_selector_all("dt")
            dds = hosyu.query_selector_all("dd")
            for i in range(min(len(dts), len(dds))):
                cond = dts[i].inner_text().strip()
                amt = dds[i].inner_text().strip()
                reward_parts.append(f"{cond}:{amt}")
        reward = " / ".join(reward_parts)

        if program_name:
            results.append({
                "program_name": program_name,
                "company_name": "",  # アクセストレードのカードに会社名はない
                "program_id": program_id,
                "category": category,
                "reward": reward,
                "status": status,
                "asp": "accesstrade",
            })
    return results


def scrape_accesstrade(page):
    """アクセストレードのプログラム一覧を全ページ取得（AJAXページング）"""
    programs = []

    # 表示件数を100件に変更して再検索（クリック数を減らす）
    try:
        page.wait_for_selector("section.program", timeout=15000)
        line_sel = page.query_selector("#lineMax")
        if line_sel:
            page.select_option("#lineMax", "100")
            # 検索ボタンを押して反映（form再送信）
            search_btn = page.query_selector(
                "button[type=submit], input[type=submit], .btn_search, #searchBtn")
            if search_btn:
                search_btn.click()
            time.sleep(3)
            page.wait_for_selector("section.program", timeout=15000)
    except Exception as e:
        print(f"  100件表示への切り替えをスキップ: {e}")

    current_page = 1
    max_pages = 200
    prev_first = None

    while current_page <= max_pages:
        print(f"  ページ {current_page} 取得中...")
        try:
            page.wait_for_selector("section.program", timeout=15000)
        except Exception:
            print("  プログラムが見つかりません（終了）")
            break

        cards = _extract_at_cards(page)
        if not cards:
            print("  カード0件（終了）")
            break

        first_id = cards[0].get("program_id", "")
        if first_id and first_id == prev_first:
            time.sleep(2)
            cards = _extract_at_cards(page)
            first_id = cards[0].get("program_id", "") if cards else ""
            if first_id == prev_first:
                print("  ページが更新されていません（最終ページと判断、終了）")
                break

        programs.extend(cards)
        prev_first = first_id
        print(f"  {len(cards)}件取得（累計: {len(programs)}件）")

        # 次ページ（data-page = current+1）のリンクを探す
        next_links = page.query_selector_all(f"a[data-page='{current_page + 1}']")
        if not next_links:
            print("  次ページリンクなし（最終ページ、終了）")
            break
        try:
            next_links[0].click()
        except Exception as e:
            print(f"  次へクリック失敗: {e}（終了）")
            break
        time.sleep(3)
        current_page += 1

    return programs


# --- afb（www.afi-b.com、URL方式ページング） ---
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


def _set_page_param(url, page_num):
    """URLの p パラメータをpage_numに差し替える"""
    parts = urlparse(url)
    q = parse_qs(parts.query, keep_blank_values=True)
    q["p"] = [str(page_num)]
    new_query = urlencode(q, doseq=True)
    return urlunparse(parts._replace(query=new_query, fragment="pagination"))


def _extract_afb_cards(page):
    """afbのプロモーションカードを抽出"""
    results = []
    cards = page.query_selector_all("div.promotion")
    for card in cards:
        h5s = card.query_selector_all("h5")
        company_name = h5s[0].inner_text().strip() if len(h5s) >= 1 else ""
        program_name = h5s[1].inner_text().strip() if len(h5s) >= 2 else (
            h5s[0].inner_text().strip() if h5s else "")
        # 会社名と案件名が1つしかない場合は案件名扱い、会社名は空に
        if len(h5s) < 2:
            company_name = ""

        # ステータス（img alt）
        status = ""
        img = card.query_selector("div.short_pid_name img")
        if img:
            status = (img.get_attribute("alt") or "").strip()

        # PID とカテゴリ（short_pid_nameのテキストから）
        program_id = ""
        category = ""
        spn = card.query_selector("div.short_pid_name")
        if spn:
            txt = spn.inner_text().strip()
            m = _re.search(r"PID[:：]\s*(\d+)", txt)
            if m:
                program_id = m.group(1)
            # 【PID:xxx】を除去した残りをカテゴリ候補に
            cat = _re.sub(r"【PID[:：]\s*\d+】", "", txt)
            cat = _re.sub(r"\s+", " ", cat).strip()
            category = cat

        # 報酬
        reward = ""
        rem = card.query_selector("div.remuneration")
        if rem:
            reward = _re.sub(r"\s+", " ", rem.inner_text().strip())[:120]

        if program_name:
            results.append({
                "program_name": program_name,
                "company_name": company_name,
                "program_id": program_id,
                "category": category,
                "reward": reward,
                "status": status,
                "asp": "afb",
            })
    return results


def scrape_afb(page):
    """afbのプロモーション一覧を全ページ取得（URL方式ページング）"""
    programs = []
    try:
        page.wait_for_selector("div.promotion", timeout=15000)
    except Exception:
        print("  プロモーションが見つかりません。一覧ページを表示してから実行してください。")
        return programs

    base_url = page.url
    page_num = 1
    max_pages = 100
    prev_first = None

    while page_num <= max_pages:
        url = _set_page_param(base_url, page_num)
        print(f"  ページ {page_num} 取得中...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  ナビゲーション失敗: {e}（終了）")
            break
        time.sleep(2)

        try:
            page.wait_for_selector("div.promotion", timeout=15000)
        except Exception:
            print("  カードが見つかりません（最終ページ、終了）")
            break

        cards = _extract_afb_cards(page)
        if not cards:
            print("  カード0件（終了）")
            break

        # 最終ページ検知: program_id が空でも program_name で判定する
        first_key = cards[0].get("program_id", "") or cards[0].get("program_name", "")
        if first_key and first_key == prev_first:
            print("  前ページと同じ内容（最終ページと判断、終了）")
            break

        programs.extend(cards)
        prev_first = first_key
        print(f"  {len(cards)}件取得（累計: {len(programs)}件）")
        page_num += 1

    return programs


# --- もしもアフィリエイト（af.moshimo.com、URL方式テーブル） ---


def _extract_moshimo_rows(page):
    """もしものプロモーション検索テーブルから案件を抽出"""
    results = []
    trs = page.query_selector_all("table tr")
    for tr in trs:
        name_td = tr.query_selector("td.promotion-name")
        if not name_td:
            continue
        program_name = name_td.inner_text().strip()

        # ID (input[name="lump[]"])
        program_id = ""
        inp = tr.query_selector("input[name='lump[]']")
        if inp:
            program_id = inp.get_attribute("value") or ""

        # 報酬
        reward = ""
        rew_td = tr.query_selector("td.max-result")
        if rew_td:
            reward = _re.sub(r"\s+", " ", rew_td.inner_text().strip())

        # ステータス
        status = ""
        st_td = tr.query_selector("td.apply-status")
        if st_td:
            status = st_td.inner_text().strip()

        if program_name:
            results.append({
                "program_name": program_name,
                "company_name": "",
                "program_id": program_id,
                "category": "",
                "reward": reward,
                "status": status,
                "asp": "moshimo",
            })
    return results


def scrape_moshimo(page):
    """もしもアフィリエイトのプロモーション一覧を全ページ取得"""
    programs = []

    # 表示件数を100件に変更
    try:
        page.wait_for_selector("td.promotion-name", timeout=15000)
        selects = page.query_selector_all("select")
        for sel in selects:
            opts = sel.query_selector_all("option")
            for opt in opts:
                if "100" in (opt.inner_text() or "") and "件" in (opt.inner_text() or ""):
                    sel.select_option(value="100")
                    # フォーム送信
                    form_btn = page.query_selector("button[type=submit], input[type=submit]")
                    if form_btn:
                        form_btn.click()
                    time.sleep(3)
                    break
            else:
                continue
            break
    except Exception as e:
        print(f"  100件表示への切り替えをスキップ: {e}")

    base_url = page.url
    page_num = 1
    max_pages = 200
    prev_first = None

    while page_num <= max_pages:
        print(f"  ページ {page_num} 取得中...")
        if page_num > 1:
            url = _re.sub(r'page=\d+', f'page={page_num}', base_url)
            if 'page=' not in url:
                sep = '&' if '?' in url else '?'
                url = f"{url}{sep}page={page_num}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"  ナビゲーション失敗: {e}（終了）")
                break
            time.sleep(2)

        try:
            page.wait_for_selector("td.promotion-name", timeout=15000)
        except Exception:
            print("  案件が見つかりません（最終ページ、終了）")
            break

        cards = _extract_moshimo_rows(page)
        if not cards:
            print("  0件（終了）")
            break

        first_key = cards[0].get("program_id", "") or cards[0].get("program_name", "")
        if first_key and first_key == prev_first:
            print("  前ページと同じ内容（最終ページと判断、終了）")
            break

        programs.extend(cards)
        prev_first = first_key
        print(f"  {len(cards)}件取得（累計: {len(programs)}件）")

        # 次へリンクがあるか確認
        next_link = page.query_selector("a.next")
        if not next_link:
            print("  次へリンクなし（最終ページ、終了）")
            break

        page_num += 1

    return programs


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

        prompts = {
            "a8": "a8 にログインしてください。\nログイン完了後、このターミナルでEnterキーを押してください...",
            "accesstrade": (
                "アクセストレードにログイン後、\n"
                "「プログラム検索」で全プログラム一覧を表示してください。\n"
                "（プログラム情報ページ: merchant/search.html / 案件カードが並んだ状態）\n"
                "一覧が表示されたら、このターミナルでEnterキーを押してください..."),
            "afb": (
                "afb にログイン後、\n"
                "「プロモーション検索」→ プロモーション一覧（promolist）を表示してください。\n"
                "（案件カードが50件並んだ状態）\n"
                "一覧が表示されたら、このターミナルでEnterキーを押してください..."),
            "moshimo": (
                "もしもアフィリエイトにログイン後、\n"
                "「プロモーション検索」で全案件一覧を表示してください。\n"
                "（案件がテーブルで並んだ状態）\n"
                "一覧が表示されたら、このターミナルでEnterキーを押してください..."),
        }
        input(f"\n{prompts.get(asp_key, asp_key + ' の一覧を表示後Enter...')}")

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
