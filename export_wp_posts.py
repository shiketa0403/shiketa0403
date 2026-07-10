#!/usr/bin/env python3
"""WordPress(gooq.jp) の全記事を取得して 記事管理.md と csv/wp_posts.csv に書き出す。

GitHub Actions（wp_export.yml）から実行し、生成ファイルをブランチにコミットして返す。
これにより、この環境（gooq.jpへ直接接続不可）からも実際の投稿状況を確認できる。
"""

import csv
import os
import time
from collections import Counter

from wp_post import api_request


def api_request_retry(endpoint, retries=5):
    """接続タイムアウト等の一時エラーに耐えるよう、指数バックオフでリトライする。
    HTTPError（ページ超過の400など）は api_request が None を返すのでそのまま返す。"""
    for attempt in range(retries):
        try:
            return api_request(endpoint, exit_on_error=False)
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt  # 1, 2, 4, 8, 16秒
            print(f"  リトライ {attempt + 1}/{retries}（{wait}s待機）: {type(e).__name__}: {e}")
            time.sleep(wait)
    return None


def fetch_all_posts():
    posts_by_id = {}
    for status in ["publish", "draft", "pending", "private", "future"]:
        page = 1
        while True:
            # exit_on_error=False: ページ超過の400を None として受けて break
            batch = api_request_retry(
                f"posts?per_page=100&page={page}&status={status}"
                f"&_fields=id,title,status,link,date,slug"
            )
            if not batch:
                break
            for p in batch:
                posts_by_id[p["id"]] = p
            if len(batch) < 100:
                break
            page += 1
            time.sleep(0.5)  # レート制限回避のため各リクエスト間に小休止
    posts = list(posts_by_id.values())
    posts.sort(key=lambda p: p.get("date", "") or "", reverse=True)
    return posts


def main():
    posts = fetch_all_posts()

    # CSV（機械処理用）
    os.makedirs("csv", exist_ok=True)
    with open("csv/wp_posts.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["id", "status", "date", "title", "slug", "link"])
        for p in posts:
            w.writerow([
                p["id"], p["status"], p.get("date", ""),
                p["title"]["rendered"], p.get("slug", ""), p.get("link", ""),
            ])

    # Markdown（人間が読む用）
    cnt = Counter(p["status"] for p in posts)
    latest = posts[0].get("date", "") if posts else "-"
    lines = [
        "# gooq.jp 記事管理（WordPress実データ）",
        "",
        f"最終取得記事の日時: {latest}　／　総数 {len(posts)}件",
        "ステータス別: " + " / ".join(f"{k}={v}" for k, v in cnt.items()),
        "",
        "| ID | 状態 | 日付 | タイトル |",
        "|---|---|---|---|",
    ]
    for p in posts:
        title = p["title"]["rendered"].replace("|", "｜").strip()
        date = (p.get("date", "") or "")[:10]
        lines.append(f"| {p['id']} | {p['status']} | {date} | {title} |")
    with open("記事管理.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"エクスポート完了: {len(posts)}件 / 記事管理.md, csv/wp_posts.csv を出力")


if __name__ == "__main__":
    main()
