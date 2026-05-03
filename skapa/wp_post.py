"""skyperfectv.heteml.net への WordPress 下書き投稿。

08_final.html の `<!-- IMG: ... -->` プレースホルダを、
WordPressメディアにアップロードした画像のURLに置換し、下書き保存する。

使い方:
    python -m skapa.wp_post エムオン
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import sys
from pathlib import Path
from typing import Any

from . import config, sheet_loader
from .sheet_loader import Channel


def _auth_header() -> dict[str, str]:
    if not config.WP_USERNAME or not config.WP_APP_PASSWORD:
        raise RuntimeError(
            "SKYPERFECT_WP_USERNAME / SKYPERFECT_WP_APP_PASSWORD が未設定です。"
        )
    creds = f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}"
    token = base64.b64encode(creds.encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _api_url(endpoint: str) -> str:
    return f"{config.WP_API_ENDPOINT}/{endpoint.lstrip('/')}"


def upload_media(file_path: Path, alt_text: str = "") -> dict[str, Any]:
    """画像をWordPressメディアライブラリにアップロード。"""
    import requests

    mime_type, _ = mimetypes.guess_type(file_path.name)
    if not mime_type:
        mime_type = "application/octet-stream"

    headers = _auth_header()
    headers["Content-Disposition"] = f'attachment; filename="{file_path.name}"'
    headers["Content-Type"] = mime_type

    with open(file_path, "rb") as f:
        body = f.read()

    resp = requests.post(
        _api_url("media"),
        headers=headers,
        data=body,
        timeout=60,
    )
    if resp.status_code >= 400:
        # 詳細レスポンスを表示してデバッグしやすく
        print(
            f"[wp_post] エラー応答 ({resp.status_code}): {resp.text[:1000]}",
            file=sys.stderr,
        )
    resp.raise_for_status()
    media = resp.json()

    # alt_text を後追いで設定
    if alt_text and media.get("id"):
        requests.post(
            _api_url(f"media/{media['id']}"),
            headers={**_auth_header(), "Content-Type": "application/json"},
            data=json.dumps({"alt_text": alt_text}),
            timeout=30,
        )
        media["alt_text"] = alt_text

    return media


def replace_image_placeholders(html: str, channel_name: str, screenshots_dir: Path) -> tuple[str, list[dict]]:
    """`<!-- IMG: スカパー公式 -->` などのプレースホルダを実 <img> タグに置換。

    Returns:
        (置換後HTML, アップロード済みmedia情報リスト)
    """
    placeholder_to_file = {
        "スカパー公式": (screenshots_dir / "skapa_top.png", "スカパー公式サイト"),
        "チャンネルページ": (screenshots_dir / "channel_page.png", channel_name),
    }

    uploaded: list[dict] = []
    for label, (path, alt) in placeholder_to_file.items():
        placeholder = f"<!-- IMG: {label} -->"
        if placeholder not in html:
            continue
        if not path.exists():
            print(f"[wp_post] 警告: {path} が存在しません。プレースホルダを削除します。", file=sys.stderr)
            html = html.replace(placeholder, "")
            continue

        print(f"[wp_post] {label} 画像をアップロード: {path}")
        media = upload_media(path, alt_text=alt)
        url = media.get("source_url") or media.get("guid", {}).get("rendered", "")
        img_tag = f'<img src="{url}" alt="{alt}" />'
        html = html.replace(placeholder, img_tag)
        uploaded.append(media)

    return html, uploaded


def extract_title(slug: str) -> str:
    """Step 2/3 出力から記事タイトル候補1番目を抽出。"""
    title_re = re.compile(r"記事タイトル案[\s\S]*?\n\s*1[.\s]\s*(.+?)(?:[（(]|$)", re.M)
    for fname in ("03_structure_audit.md", "02_structure.md"):
        path = config.channel_draft_dir(slug) / fname
        if not path.exists():
            continue
        m = title_re.search(path.read_text(encoding="utf-8"))
        if m:
            return m.group(1).strip().rstrip("|｜").strip()
    return ""


def create_or_update_post(title: str, content: str, slug: str, *, status: str | None = None) -> dict[str, Any]:
    """投稿を作成または更新（既存ID保存があれば更新）。"""
    import requests

    status = status or config.WP_POST_STATUS
    state_path = config.channel_draft_dir(slug) / "wp_post_id.json"
    headers = {**_auth_header(), "Content-Type": "application/json"}

    payload = {
        "title": title,
        "content": content,
        "status": status,
        "slug": slug,
    }

    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        post_id = state.get("id")
        if post_id:
            print(f"[wp_post] 既存投稿 ID={post_id} を更新")
            resp = requests.post(
                _api_url(f"posts/{post_id}"),
                headers=headers,
                data=json.dumps(payload),
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()

    print(f"[wp_post] 新規投稿を作成 (status={status})")
    resp = requests.post(
        _api_url("posts"),
        headers=headers,
        data=json.dumps(payload),
        timeout=60,
    )
    resp.raise_for_status()
    post = resp.json()
    state_path.write_text(
        json.dumps({"id": post["id"], "link": post.get("link", "")}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return post


def post_channel(ch: Channel, *, status: str | None = None) -> dict[str, Any]:
    """エムオン等のチャンネル記事を投稿する。"""
    final_path = config.channel_draft_dir(ch.slug) / config.STEP_FILENAMES[8]
    if not final_path.exists():
        raise RuntimeError(
            f"08_final.html がありません: {final_path}\n先にStep 1〜8 を実行してください。"
        )

    html = final_path.read_text(encoding="utf-8")
    screens_dir = config.channel_draft_dir(ch.slug) / "screenshots"

    print(f"[wp_post] 画像プレースホルダを置換中...")
    html, _ = replace_image_placeholders(html, ch.name, screens_dir)

    title = extract_title(ch.slug)
    if not title:
        title = f"{ch.name}のスカパー料金は月額いくら？契約方法と最新情報"
        print(f"[wp_post] 警告: タイトル抽出失敗、フォールバック使用: {title}", file=sys.stderr)

    print(f"[wp_post] タイトル: {title}")
    print(f"[wp_post] スラッグ: {ch.slug}")

    post = create_or_update_post(title, html, ch.slug, status=status)
    print(f"[wp_post] 完了 → {post.get('link', '(unknown)')}")
    return post


def main() -> int:
    parser = argparse.ArgumentParser(description="スカパー記事 WordPress 投稿")
    parser.add_argument("channel", help="チャンネル名 / 正式名称 / スラッグ / No")
    parser.add_argument(
        "--status",
        default=None,
        choices=["draft", "publish", "private"],
        help="投稿ステータス（デフォルト: draft）",
    )
    args = parser.parse_args()

    channels = sheet_loader.load_local()
    ch = sheet_loader.find(channels, args.channel)
    if not ch:
        print(f"エラー: チャンネルが見つかりません: {args.channel}", file=sys.stderr)
        return 1

    print(f"対象: No.{ch.no} {ch.name}（slug: {ch.slug}）")
    post = post_channel(ch, status=args.status)
    print(f"\n投稿ID: {post.get('id')}")
    print(f"URL: {post.get('link')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
