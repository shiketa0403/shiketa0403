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
import os
import re
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


def capture_and_upload_screenshot(url, name):
    """スクリーンショットを取得しWordPressにアップロード。画像URLを返す。"""
    try:
        from screenshot import capture_and_upload
    except ImportError:
        print("  ✗ screenshot.py が見つかりません。スクリーンショットをスキップします。")
        return None

    result = capture_and_upload(url, name=name, output_dir="screenshots", upload=True)
    if result is None:
        return None
    if result.get("skipped"):
        print(f"  ✗ スクリーンショットがブロックされました（{result.get('reason', 'unknown')}）")
        return None
    return result.get("url")


def insert_screenshot_into_content(content, screenshot_wp_url, case_name):
    """記事HTMLのアフィリエイト情報テーブル直前にスクリーンショットを挿入する"""
    marker = f"<h2>{case_name}のアフィリエイト情報</h2>"
    if marker not in content:
        return content

    img_tag = (
        f'<img class="alignnone size-full" src="{screenshot_wp_url}" '
        f'alt="{case_name}" width="1280" height="800" />'
    )
    replacement = f"{marker}\n{img_tag}"
    return content.replace(marker, replacement)


def get_existing_titles():
    """WordPressの既存記事タイトルを全件取得する（下書き・公開すべて）"""
    titles = set()
    for status in ["publish", "draft", "pending", "private"]:
        page = 1
        while True:
            posts = api_request(f"posts?per_page=100&page={page}&status={status}")
            if not posts:
                break
            for p in posts:
                titles.add(p["title"]["rendered"])
            if len(posts) < 100:
                break
            page += 1
    return titles


def bulk_post_from_csv(csv_path, default_status="draft", delay=2, dry_run=False):
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"CSVから {len(rows)} 件の記事を読み込みました")
    if dry_run:
        print("=== ドライラン（実際には投稿しません） ===")

    # 既存記事のタイトルを取得して重複チェックに使う
    if not dry_run:
        print("WordPress の既存記事を確認中...")
        existing_titles = get_existing_titles()
        print(f"  既存記事: {len(existing_titles)}件")
    else:
        existing_titles = set()

    success = 0
    errors = 0

    for i, row in enumerate(rows, 1):
        title = row.get("title", "").strip()
        content = row.get("content", "").strip()
        status = row.get("status", "").strip() or default_status
        category_name = row.get("category", "").strip()
        tags_str = row.get("tags", "").strip()
        slug = row.get("slug", "").strip()
        screenshot_target = row.get("screenshot_url", "").strip()

        if not title or not content:
            print(f"[{i}/{len(rows)}] スキップ（タイトルまたは本文が空）")
            errors += 1
            continue

        print(f"\n[{i}/{len(rows)}] {title}")

        # 重複チェック
        if title in existing_titles:
            print(f"  ⏭ スキップ（同じタイトルの記事が既に存在します）")
            continue

        # スクリーンショット取得 → 記事に挿入
        if screenshot_target and not dry_run:
            case_name = re.sub(r'(とアフィリエイト提携できるASPはどこ？|のアフィリエイトはどこのASP？)$', '', title)
            print(f"  スクリーンショット取得中: {screenshot_target}")
            screenshot_wp_url = capture_and_upload_screenshot(screenshot_target, name=slug or case_name)
            if screenshot_wp_url:
                content = insert_screenshot_into_content(content, screenshot_wp_url, case_name)
                print(f"  ✓ スクリーンショットを記事に挿入しました")

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
            create_post(title, content, status, category_ids or None, tag_ids or None, slug=slug or None)
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
