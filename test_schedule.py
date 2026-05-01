#!/usr/bin/env python3
"""
X 予約投稿 動作確認スクリプト（最小構成）

ローカル PC から実行し、create_scheduled_tweet が通るか確認する。
成功すれば、X の「下書き > 予約投稿」タブに該当ポストが現れる。

実行方法:
  1. このリポジトリのルートに .env を作成し、X_AUTH_TOKEN と X_CT0 を記入
  2. pip install -r requirements.txt
  3. python test_schedule.py

環境変数:
  X_AUTH_TOKEN  : X の Cookie auth_token
  X_CT0         : X の Cookie ct0
"""
import asyncio
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from twikit import Client

load_dotenv()

JST = timezone(timedelta(hours=9), name="JST")


async def main() -> int:
    auth_token = os.environ.get("X_AUTH_TOKEN", "").strip()
    ct0 = os.environ.get("X_CT0", "").strip()

    if not auth_token or not ct0:
        print("[ERROR] .env に X_AUTH_TOKEN と X_CT0 を設定してください")
        return 1

    print(f"AUTH_TOKEN 長さ: {len(auth_token)}, CT0 長さ: {len(ct0)}")

    scheduled_dt = datetime.now(JST) + timedelta(minutes=5)
    scheduled_ts = int(scheduled_dt.timestamp())
    text = (
        f"テスト投稿（予約投稿APIの動作確認、不要なら削除します）"
        f" {scheduled_dt.strftime('%H:%M')}"
    )

    print(f"予約時刻: {scheduled_dt.strftime('%Y/%m/%d %H:%M:%S')} (unix={scheduled_ts})")
    print(f"本文: {text!r}")

    print("X クライアント初期化中...")
    client = Client("ja")
    client.set_cookies({"auth_token": auth_token, "ct0": ct0})
    print("X クライアント準備完了")

    print("予約投稿を作成中...")
    try:
        tweet_id = await client.create_scheduled_tweet(
            scheduled_at=scheduled_ts,
            text=text,
        )
    except Exception as e:
        print(f"[NG] 予約失敗: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 2

    print(f"[OK] 予約成功 tweet_id={tweet_id}")
    print()
    print("確認方法:")
    print("  1. https://x.com を開く")
    print("  2. ポスト作成画面 -> 下書き -> 予約投稿 タブ")
    print(f"  3. {scheduled_dt.strftime('%H:%M')} 予定の投稿があれば成功")
    print()
    print("不要なポストはその画面から削除してください。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
