#!/usr/bin/env python3
"""
X (Twitter) 自動投稿スクリプト

スプレッドシートの A 列に並んだポストを順番に投稿する。
- A2 から順に投稿、最終行まで来たら A2 に戻り、末尾の周回数を +1
- B 列に投稿日時を書き込み（進捗表示）
- D1: 次に投稿する行番号
- D2: 周回数（ポスト末尾に半角スペース付きで追加される）

環境変数:
  X_AUTH_TOKEN, X_CT0           : X の Cookie
  GSPREAD_SHEET_ID              : スプレッドシート ID
  GOOGLE_SERVICE_ACCOUNT_JSON   : Service Account の JSON 文字列
  GSPREAD_WORKSHEET_NAME        : シート名（省略時は 1 枚目）
  INTERVAL_MINUTES              : 投稿間隔（分）
  DURATION_HOURS                : 実行時間（時間）
"""
import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone

import gspread
from google.oauth2.service_account import Credentials
from twikit import Client

JST = timezone(timedelta(hours=9), name="JST")

SHEET_ID = os.environ["GSPREAD_SHEET_ID"]
WORKSHEET_NAME = os.environ.get("GSPREAD_WORKSHEET_NAME", "").strip()
AUTH_TOKEN = os.environ["X_AUTH_TOKEN"]
CT0 = os.environ["X_CT0"]
SA_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]

INTERVAL_MIN = int(os.environ.get("INTERVAL_MINUTES", "30"))
DURATION_HOURS = float(os.environ.get("DURATION_HOURS", "1"))

POINTER_CELL = "D1"
CYCLE_CELL = "D2"


def now_jst() -> datetime:
    return datetime.now(JST)


def open_worksheet():
    creds = Credentials.from_service_account_info(
        json.loads(SA_JSON),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    return sh.worksheet(WORKSHEET_NAME) if WORKSHEET_NAME else sh.sheet1


def read_int_cell(ws, cell, default):
    try:
        v = ws.acell(cell).value
        return int(v) if v not in (None, "") else default
    except (ValueError, TypeError):
        return default


def find_target(posts, next_row, cycle):
    """
    A 列（posts は 1 行目=ヘッダー含むリスト）の中から、
    次に投稿すべき行番号と現在の周回数を決定する。

    Returns: (target_row, cycle) または (None, cycle) 投稿可能な行なし
    """
    last_row = len(posts)
    if last_row < 2:
        return None, cycle

    if next_row < 2:
        next_row = 2
    if next_row > last_row:
        next_row = 2
        cycle += 1

    scanned = 0
    while scanned <= last_row:
        if next_row <= last_row and posts[next_row - 1].strip():
            return next_row, cycle
        next_row += 1
        if next_row > last_row:
            next_row = 2
            cycle += 1
        scanned += 1

    return None, cycle


async def post_one(ws, client) -> bool:
    """1 回分の投稿処理。成功時 True。"""
    posts = ws.col_values(1)
    next_row = read_int_cell(ws, POINTER_CELL, 2)
    cycle = read_int_cell(ws, CYCLE_CELL, 1)
    if cycle < 1:
        cycle = 1

    target, cycle = find_target(posts, next_row, cycle)
    if target is None:
        print("A 列に投稿可能な行がありません。")
        return False

    text = posts[target - 1].strip()
    post_text = f"{text} {cycle}"

    print(f"投稿準備: 行{target} 周回{cycle} 文字数={len(post_text)}")
    print(f"本文プレビュー: {post_text[:80]!r}")

    success = False
    try:
        result = await client.create_tweet(text=post_text)
        success = True
        stamp = now_jst().strftime("%m/%d %H:%M")
        ws.update_acell(f"B{target}", stamp)
        print(f"[OK] 行{target} 周回{cycle}: tweet_id={getattr(result, 'id', '?')}")
    except Exception as e:
        import traceback
        print(f"[NG] 行{target} 周回{cycle} 失敗: {type(e).__name__}: {e}")
        traceback.print_exc()

    # ポインタは成功・失敗にかかわらず進める
    last_row = len(posts)
    new_next = target + 1
    new_cycle = cycle
    if new_next > last_row:
        new_next = 2
        new_cycle = cycle + 1

    try:
        ws.update_acell(POINTER_CELL, new_next)
        ws.update_acell(CYCLE_CELL, new_cycle)
    except Exception as e:
        print(f"[WARN] ポインタ更新失敗: {e}")

    return success


async def main():
    print(f"=== X 自動投稿 開始 {now_jst().strftime('%Y/%m/%d %H:%M:%S')} ===")
    print(f"間隔: {INTERVAL_MIN}分  実行時間: {DURATION_HOURS}時間")

    print(f"twikit version: {__import__('twikit').__version__ if hasattr(__import__('twikit'), '__version__') else '?'}")
    print(f"AUTH_TOKEN 長さ: {len(AUTH_TOKEN)}, CT0 長さ: {len(CT0)}")

    print("スプレッドシート接続中...")
    ws = open_worksheet()
    print(f"シート接続OK: {ws.title}")

    print("X クライアント初期化中...")
    client = Client("ja")
    client.set_cookies({"auth_token": AUTH_TOKEN, "ct0": CT0})
    print("X クライアント準備完了")

    end_time = now_jst() + timedelta(hours=DURATION_HOURS)
    interval_sec = INTERVAL_MIN * 60

    iteration = 0
    while now_jst() < end_time:
        iteration += 1
        print(f"\n--- 投稿 #{iteration} ({now_jst().strftime('%H:%M:%S')}) ---")
        await post_one(ws, client)

        # 次の投稿が終了時刻を超えるなら終了
        next_at = now_jst() + timedelta(seconds=interval_sec)
        if next_at >= end_time:
            print("次回投稿予定が終了時刻を超えるため終了")
            break
        print(f"次回まで {INTERVAL_MIN} 分待機...")
        time.sleep(interval_sec)

    print(f"\n=== 完了 {now_jst().strftime('%Y/%m/%d %H:%M:%S')} ===")


if __name__ == "__main__":
    asyncio.run(main())
