#!/usr/bin/env python3
"""
WordPress REST API 自動投稿スクリプト

使い方:
  # 単体記事投稿
  python wp_post.py post --title "記事タイトル" --content "<p>本文HTML</p>" --status publish

  # 記事一覧取得
  python wp_post.py list

  # 記事削除
  python wp_post.py delete --id 123

  # カテゴリ作成
  python wp_post.py create-category --name "新カテゴリ"

  # カテゴリ一覧
  python wp_post.py list-categories
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
import base64

from wp_config import WP_CONFIG


def get_auth_header():
    credentials = f"{WP_CONFIG['username']}:{WP_CONFIG['app_password']}"
    token = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {token}"}


def api_request(endpoint, method="GET", data=None):
    url = f"{WP_CONFIG['site_url']}/wp-json/wp/v2/{endpoint}"
    headers = get_auth_header()
    headers["Content-Type"] = "application/json"

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            error_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = "(レスポンス読み取り不可)"
        print(f"エラー {e.code}: {error_body}", file=sys.stderr)
        sys.exit(1)


# === 記事操作 ===

def create_post(title, content, status="draft", category_ids=None, tag_ids=None):
    data = {
        "title": title,
        "content": content,
        "status": status,
    }
    if category_ids:
        data["categories"] = category_ids
    if tag_ids:
        data["tags"] = tag_ids

    result = api_request("posts", "POST", data)
    print(f"✓ 投稿成功: [{result['id']}] {result['title']['rendered']} ({result['status']})")
    print(f"  URL: {result['link']}")
    return result


def list_posts(per_page=20, status="any"):
    posts = api_request(f"posts?per_page={per_page}&status={status}")
    if not posts:
        print("記事がありません")
        return
    print(f"記事一覧 ({len(posts)}件):")
    for p in posts:
        print(f"  [{p['id']}] {p['title']['rendered']} ({p['status']})")
    return posts


def update_post(post_id, **kwargs):
    result = api_request(f"posts/{post_id}", "POST", kwargs)
    print(f"✓ 更新成功: [{result['id']}] {result['title']['rendered']}")
    return result


def delete_post(post_id, force=False):
    endpoint = f"posts/{post_id}?force={'true' if force else 'false'}"
    result = api_request(endpoint, "DELETE")
    print(f"✓ 削除成功: ID {post_id}")
    return result


# === カテゴリ操作 ===

def create_category(name, parent=0):
    data = {"name": name}
    if parent:
        data["parent"] = parent
    result = api_request("categories", "POST", data)
    print(f"✓ カテゴリ作成: [{result['id']}] {result['name']}")
    return result


def list_categories():
    cats = api_request("categories?per_page=100")
    print(f"カテゴリ一覧 ({len(cats)}件):")
    for c in cats:
        print(f"  [{c['id']}] {c['name']} (記事数: {c['count']})")
    return cats


# === タグ操作 ===

def create_tag(name):
    result = api_request("tags", "POST", {"name": name})
    print(f"✓ タグ作成: [{result['id']}] {result['name']}")
    return result


def get_or_create_tag(name):
    """タグが存在すれば取得、なければ作成"""
    tags = api_request(f"tags?search={urllib.parse.quote(name)}")
    for t in tags:
        if t["name"].lower() == name.lower():
            return t
    return api_request("tags", "POST", {"name": name})


def list_tags():
    tags = api_request("tags?per_page=100")
    print(f"タグ一覧 ({len(tags)}件):")
    for t in tags:
        print(f"  [{t['id']}] {t['name']} (記事数: {t['count']})")
    return tags


# === CLI ===

def main():
    parser = argparse.ArgumentParser(description="WordPress 自動投稿ツール")
    sub = parser.add_subparsers(dest="command")

    # post
    p_post = sub.add_parser("post", help="記事を投稿")
    p_post.add_argument("--title", required=True)
    p_post.add_argument("--content", required=True)
    p_post.add_argument("--status", default="draft", choices=["draft", "publish", "pending", "private"])
    p_post.add_argument("--categories", type=int, nargs="*")
    p_post.add_argument("--tags", type=int, nargs="*")

    # list
    sub.add_parser("list", help="記事一覧")

    # update
    p_update = sub.add_parser("update", help="記事を更新")
    p_update.add_argument("--id", type=int, required=True)
    p_update.add_argument("--title")
    p_update.add_argument("--content")
    p_update.add_argument("--status", choices=["draft", "publish", "pending", "private"])

    # delete
    p_delete = sub.add_parser("delete", help="記事を削除")
    p_delete.add_argument("--id", type=int, required=True)
    p_delete.add_argument("--force", action="store_true")

    # categories
    p_cat = sub.add_parser("create-category", help="カテゴリ作成")
    p_cat.add_argument("--name", required=True)
    p_cat.add_argument("--parent", type=int, default=0)
    sub.add_parser("list-categories", help="カテゴリ一覧")

    # tags
    p_tag = sub.add_parser("create-tag", help="タグ作成")
    p_tag.add_argument("--name", required=True)
    sub.add_parser("list-tags", help="タグ一覧")

    args = parser.parse_args()

    if args.command == "post":
        create_post(args.title, args.content, args.status, args.categories, args.tags)
    elif args.command == "list":
        list_posts()
    elif args.command == "update":
        kwargs = {}
        if args.title:
            kwargs["title"] = args.title
        if args.content:
            kwargs["content"] = args.content
        if args.status:
            kwargs["status"] = args.status
        update_post(args.id, **kwargs)
    elif args.command == "delete":
        delete_post(args.id, args.force)
    elif args.command == "create-category":
        create_category(args.name, args.parent)
    elif args.command == "list-categories":
        list_categories()
    elif args.command == "create-tag":
        create_tag(args.name)
    elif args.command == "list-tags":
        list_tags()
    else:
        parser.print_help()


if __name__ == "__main__":
    import urllib.parse
    main()
