#!/usr/bin/env python3
"""
CSV一括投稿スクリプト

CSVフォーマット:
  title,content,status,category,tags
  "記事タイトル","<p>本文HTML</p>",publish,"カテゴリ名","タグ1,タグ2"

使い方:
  # ドライラン（投稿せず内容確認）
  python wp_bulk_post.py csv/articles.csv --dry-run

  # 下書きで一括投稿
  python wp_bulk_post.py csv/articles.csv

  # 公開で一括投稿
  python wp_bulk_post.py csv/articles.csv --status publish

  # 投稿間隔を指定（秒）
  python wp_bulk_post.py csv/articles.csv --status publish --delay 3
"""

import argparse
import csv
import sys
import time
import urllib.parse

from wp_post import api_request, create_post


def get_or_create_category(name):
    """カテゴリ名から ID を取得（なければエラー）"""
    cats = api_request(f"categories?search={urllib.parse.quote(name)}")
    for c in cats:
        if c["name"] == name:
            return c["id"]
    print(f"  ✗ カテゴリ '{name}' が見つかりません。WordPress側で先に作成してください。")
    return None


def get_or_create_tag(name):
    """タグ名から ID を取得（なければエラー）"""
    tags = api_request(f"tags?search={urllib.parse.quote(name)}")
    for t in tags:
        if t["name"].lower() == name.lower():
            return t["id"]
    print(f"  ✗ タグ '{name}' が見つかりません。WordPress側で先に作成してください。")
    return None


def bulk_post_from_csv(csv_path, default_status="draft", delay=2, dry_run=False):
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"CSVから {len(rows)} 件の記事を読み込みました")
    if dry_run:
        print("=== ドライラン（実際には投稿しません） ===")

    success = 0
    errors = 0

    for i, row in enumerate(rows, 1):
        title = row.get("title", "").strip()
        content = row.get("content", "").strip()
        status = row.get("status", "").strip() or default_status
        category_name = row.get("category", "").strip()
        tags_str = row.get("tags", "").strip()

        if not title or not content:
            print(f"[{i}/{len(rows)}] スキップ（タイトルまたは本文が空）")
            errors += 1
            continue

        print(f"\n[{i}/{len(rows)}] {title}")

        if dry_run:
            print(f"  ステータス: {status}")
            if category_name:
                print(f"  カテゴリ: {category_name}")
            if tags_str:
                print(f"  タグ: {tags_str}")
            print(f"  本文: {content[:80]}...")
            success += 1
            continue

        # カテゴリID取得
        category_ids = []
        if category_name:
            cat_id = get_or_create_category(category_name)
            if cat_id is None:
                print(f"  ✗ スキップ（カテゴリ '{category_name}' が存在しません）")
                errors += 1
                continue
            category_ids = [cat_id]

        # タグID取得
        tag_ids = []
        if tags_str:
            for tag_name in tags_str.split(","):
                tag_name = tag_name.strip()
                if tag_name:
                    tag_id = get_or_create_tag(tag_name)
                    if tag_id is not None:
                        tag_ids.append(tag_id)

        try:
            create_post(title, content, status, category_ids or None, tag_ids or None)
            success += 1
        except Exception as e:
            print(f"  ✗ 投稿失敗: {e}")
            errors += 1

        if i < len(rows) and delay > 0:
            time.sleep(delay)

    print(f"\n=== 完了: 成功 {success}件 / エラー {errors}件 ===")


def main():
    parser = argparse.ArgumentParser(description="CSV一括投稿")
    parser.add_argument("csv_file", help="CSVファイルのパス")
    parser.add_argument("--status", default="draft", choices=["draft", "publish", "pending", "private"])
    parser.add_argument("--delay", type=float, default=2, help="投稿間隔（秒）")
    parser.add_argument("--dry-run", action="store_true", help="投稿せず内容確認のみ")

    args = parser.parse_args()
    bulk_post_from_csv(args.csv_file, args.status, args.delay, args.dry_run)


if __name__ == "__main__":
    main()
