#!/usr/bin/env python3
"""
X 一括予約投稿スクリプト

スプレッドシートのA列のポストを、X の予約投稿APIで一括予約する。
- 間隔: 実行時に対話で選択 (10/15/30/60分)
- 件数: 実行時に対話で入力
- 開始時刻: 実行時刻の10分後
- 周回数: 実行ごとに1から開始、A列を1周するごとに +1
- 行ポインタ(D1): スプレッドシートに保存して継続

環境変数 (.env):
  X_AUTH_TOKEN, X_CT0           : X の Cookie
  GSPREAD_SHEET_ID              : スプレッドシート ID
  GSPREAD_SERVICE_ACCOUNT_FILE  : Service Account JSON へのパス (デフォルト: service_account.json)
  GSPREAD_WORKSHEET_NAME        : シート名（省略時は 1 枚目）
"""
import asyncio
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from twikit import Client

load_dotenv()

JST = timezone(timedelta(hours=9), name="JST")
POINTER_CELL = "D1"
INTERVAL_OPTIONS = {"1": 10, "2": 15, "3": 30, "4": 60}

SHEET_ID = os.environ.get("GSPREAD_SHEET_ID", "").strip()
SA_FILE = os.environ.get("GSPREAD_SERVICE_ACCOUNT_FILE", "service_account.json").strip()
WORKSHEET_NAME = os.environ.get("GSPREAD_WORKSHEET_NAME", "").strip()
AUTH_TOKEN = os.environ.get("X_AUTH_TOKEN", "").strip()
CT0 = os.environ.get("X_CT0", "").strip()


def now_jst() -> datetime:
    return datetime.now(JST)


def open_worksheet():
    sa_path = Path(SA_FILE)
    if not sa_path.is_file():
        raise FileNotFoundError(
            f"Service Account JSON が見つかりません: {sa_path.resolve()}\n"
            f"リポジトリ直下に service_account.json を配置するか、"
            f".env の GSPREAD_SERVICE_ACCOUNT_FILE で正しいパスを指定してください。"
        )
    creds = Credentials.from_service_account_file(
        str(sa_path),
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


def prompt_interval() -> int:
    print("間隔を選んでください:")
    for k, v in INTERVAL_OPTIONS.items():
        print(f"  {k}) {v}分")
    while True:
        ans = input("番号 (1-4): ").strip()
        if ans in INTERVAL_OPTIONS:
            return INTERVAL_OPTIONS[ans]
        print("  → 1〜4 で入力してください")


def prompt_count() -> int:
    while True:
        ans = input("件数 (1-100): ").strip()
        try:
            n = int(ans)
            if 1 <= n <= 100:
                return n
        except ValueError:
            pass
        print("  → 1〜100 の整数で入力してください")


def check_required_env():
    missing = []
    if not SHEET_ID:
        missing.append("GSPREAD_SHEET_ID")
    if not AUTH_TOKEN:
        missing.append("X_AUTH_TOKEN")
    if not CT0:
        missing.append("X_CT0")
    if missing:
        print(f"[ERROR] .env に以下が設定されていません: {', '.join(missing)}")
        sys.exit(1)


async def main() -> int:
    check_required_env()

    print("=== X 一括予約投稿 ===")
    interval_min = prompt_interval()
    count = prompt_count()

    start_dt = now_jst() + timedelta(minutes=10)
    end_dt = start_dt + timedelta(minutes=interval_min * (count - 1))

    print()
    print("予約計画:")
    print(f"  間隔: {interval_min}分")
    print(f"  件数: {count}件")
    print(f"  開始: {start_dt.strftime('%m/%d %H:%M')}（実行時刻の10分後）")
    print(f"  終了: {end_dt.strftime('%m/%d %H:%M')}")
    print()
    if input("このまま実行しますか？ (y/N): ").strip().lower() not in ("y", "yes"):
        print("中止しました。")
        return 0

    print()
    print("スプレッドシート接続中...")
    try:
        ws = open_worksheet()
    except Exception as e:
        print(f"[ERROR] スプレッドシート接続失敗: {e}")
        return 1
    print(f"シート接続OK: {ws.title}")

    posts = ws.col_values(1)
    last_row = len(posts)
    if last_row < 2:
        print("[ERROR] A 列にポストがありません（A2 以降が空）")
        return 1

    next_row = read_int_cell(ws, POINTER_CELL, 2)
    if next_row < 2 or next_row > last_row:
        next_row = 2
    cycle = 1
    print(f"開始位置: 行{next_row}（D1の値、または範囲外なら行2にフォールバック）")
    print()

    print("X クライアント初期化中...")
    client = Client("ja")
    client.set_cookies({"auth_token": AUTH_TOKEN, "ct0": CT0})
    print("X クライアント準備完了")
    print()

    success = 0
    fail = 0
    SLEEP_BETWEEN = 5  # X のバースト判定回避のため、各リクエスト間に待機

    for i in range(1, count + 1):
        # 空白行を飛ばして投稿可能な行を見つける
        scanned = 0
        target = None
        while scanned <= last_row:
            if next_row > last_row:
                next_row = 2
                cycle += 1
            if posts[next_row - 1].strip():
                target = next_row
                break
            next_row += 1
            scanned += 1
        if target is None:
            print("[ERROR] A 列に投稿可能な行が一つもありません。中断します。")
            break

        text = posts[target - 1].strip()
        post_text = f"{text} {cycle}"
        scheduled_dt = start_dt + timedelta(minutes=interval_min * (i - 1))
        scheduled_ts = int(scheduled_dt.timestamp())

        prefix = f"[{i}/{count}] {scheduled_dt.strftime('%m/%d %H:%M')} 行{target} 周回{cycle}"
        post_succeeded = False
        try:
            tweet_id = await client.create_scheduled_tweet(
                scheduled_at=scheduled_ts,
                text=post_text,
            )
            print(f"{prefix}: 予約OK (id={tweet_id}) {post_text[:30]!r}")
            success += 1
            post_succeeded = True
            try:
                ws.update_acell(f"B{target}", f"予{scheduled_dt.strftime('%m/%d %H:%M')}")
            except Exception as e:
                print(f"  [WARN] B{target} 更新失敗: {e}")
        except Exception as e:
            print(f"{prefix}: 予約失敗 {type(e).__name__}: {e}")
            traceback.print_exc()
            fail += 1

        # 失敗時はポインタを進めず中断（同じ行を次回リトライできるように）
        if not post_succeeded:
            print(f"\n[中断] {i}件目で失敗したため、ここで停止します。")
            print(f"  D1 は進めません（同じ行から次回リトライできます）")
            print(f"  少し時間を空けてから再実行してください（X のレート制限と思われます）")
            break

        # ポインタを次の行へ（成功時のみ）
        next_row += 1
        if next_row > last_row:
            next_row = 2
            cycle += 1

        # 次のリクエストまで待機（最後のループでは不要）
        if i < count:
            await asyncio.sleep(SLEEP_BETWEEN)

    # 次回の開始位置を D1 に保存
    save_next = next_row if next_row <= last_row else 2
    try:
        ws.update_acell(POINTER_CELL, save_next)
        print(f"\nD1 = {save_next} に保存（次回はここから開始）")
    except Exception as e:
        print(f"\n[WARN] D1 更新失敗: {e}")

    print(f"\n=== 完了 成功:{success} / 失敗:{fail} ===")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
