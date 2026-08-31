#!/usr/bin/env python3
"""完成記事をWordPressに下書き投稿する（マルチサイト対応）。

使い方:
  python wp-article/scripts/wp_publish.py wp-article/out/<slug> --site lovedoll [--status draft]

必要ファイル:
  wp-article/config/sites.local.json  … 認証情報（gitignore対象）
  <dir>/meta.json    … {"title": "...", "slug": "...", "category": "...", "tags": "a,b"}
  <dir>/final.html   … {{IMG:ファイル名}} プレースホルダ入り本文
  <dir>/images.json  … {"eyecatch": "...", "images": [{"file","alt","width","height"}]}
  <dir>/images/*.png … 画像実体

処理:
  1. images/ の画像をメディアにアップロード（alt付き）
  2. {{IMG:...}} を <img class="alignnone size-full wp-image-{id}" ...> に置換
  3. アイキャッチを featured image に設定
  4. カテゴリ・タグを取得/作成して下書き投稿
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import struct
import sys
import time
from pathlib import Path

import requests

# Windows環境でstdoutがcp932になり日本語・記号の出力で落ちるのを防ぐ
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sites.local.json"
UA = "wp-article-pipeline/1.0"


def die(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_site(site_key: str) -> dict:
    if not CONFIG_PATH.exists():
        die(f"{CONFIG_PATH} がありません。sites.example.json をコピーして作成してください")
    sites = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if site_key not in sites:
        die(f"サイトキー '{site_key}' が sites.local.json にありません。定義済み: {', '.join(sites)}")
    site = sites[site_key]
    for k in ("url", "username", "app_password"):
        if not site.get(k) or "YOUR_" in str(site.get(k, "")):
            die(f"sites.local.json の '{site_key}.{k}' が未記入です")
    return site


class WP:
    def __init__(self, site: dict):
        self.base = site["url"].rstrip("/") + "/wp-json/wp/v2"
        token = base64.b64encode(
            f"{site['username']}:{site['app_password']}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}", "User-Agent": UA}

    def _req(self, method: str, path: str, **kw):
        r = requests.request(method, f"{self.base}/{path}",
                             headers={**self.headers, **kw.pop("headers", {})},
                             timeout=90, **kw)
        if r.status_code >= 400:
            die(f"WordPress API {method} {path} → {r.status_code}: {r.text[:300]}")
        return r.json()

    def upload_media(self, path: Path, alt: str) -> dict:
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        headers = {"Content-Type": mime,
                   "Content-Disposition": f'attachment; filename="{path.name}"'}
        media = self._req("POST", "media", headers=headers, data=path.read_bytes())
        if alt:
            self._req("POST", f"media/{media['id']}", json={"alt_text": alt})
        return media

    def ensure_term(self, taxonomy: str, name: str) -> int:
        """カテゴリ/タグを名前で検索し、無ければ作成してIDを返す。"""
        found = self._req("GET", taxonomy, params={"search": name, "per_page": 100})
        for t in found:
            if t["name"] == name:
                return t["id"]
        created = self._req("POST", taxonomy, json={"name": name})
        return created["id"]

    def create_post(self, payload: dict) -> dict:
        return self._req("POST", "posts", json=payload)


def png_size(path: Path) -> tuple[int, int]:
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", head[16:24])
        return w, h
    return 0, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", help="out/<slug> ディレクトリ")
    ap.add_argument("--site", required=True, help="sites.local.json のサイトキー")
    ap.add_argument("--status", default="draft",
                    choices=["draft", "publish", "pending", "private"])
    args = ap.parse_args()

    outdir = Path(args.dir)
    meta_p, final_p, imgjson_p = outdir / "meta.json", outdir / "final.html", outdir / "images.json"
    for p in (meta_p, final_p):
        if not p.exists():
            die(f"{p} がありません")
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    html = final_p.read_text(encoding="utf-8")
    imginfo = json.loads(imgjson_p.read_text(encoding="utf-8")) if imgjson_p.exists() else {"images": []}
    manifest = {i["file"]: i for i in imginfo.get("images", [])}

    site = load_site(args.site)
    wp = WP(site)
    print(f"投稿先: {site['url']}")

    # 認証プリフライト: アップロードを始める前に資格情報を検証する
    r = requests.get(f"{wp.base}/users/me", headers=wp.headers, timeout=30)
    if r.status_code == 200:
        me = r.json()
        print(f"認証OK: {me.get('name', '?')} (ユーザーID {me.get('id', '?')})")
    else:
        code = ""
        try:
            code = r.json().get("code", "")
        except Exception:
            pass
        if code == "rest_not_logged_in" or r.status_code == 401 and not code:
            die("認証に失敗しました (401)。\n"
                "  よくある原因: sites.local.json の username がWordPressの実際の\n"
                "  ユーザー名と一致していない（存在しないユーザー名だとこのエラーになります）。\n"
                "  WordPress管理画面 → ユーザー で正しいユーザー名を確認してください。\n"
                "  ヘッダーがサーバーに剥がされている場合も同じ症状です。")
        if code == "incorrect_password":
            die("認証に失敗しました: アプリケーションパスワードが正しくありません。\n"
                "  再発行して sites.local.json を更新してください。")
        die(f"認証チェック失敗 ({r.status_code}): {r.text[:300]}")

    # 1. 画像アップロード
    images_dir = outdir / "images"
    uploaded: dict[str, dict] = {}
    eyecatch_file = imginfo.get("eyecatch")
    files_needed = set(re.findall(r"\{\{IMG:([^}]+)\}\}", html))
    if eyecatch_file:
        files_needed.add(eyecatch_file)

    for fname in sorted(files_needed):
        fpath = images_dir / fname
        if not fpath.exists():
            print(f"  警告: {fname} が images/ に無いためスキップ（プレースホルダは除去）")
            continue
        alt = manifest.get(fname, {}).get("alt", "")
        media = wp.upload_media(fpath, alt)
        w, h = png_size(fpath)
        uploaded[fname] = {"id": media["id"], "url": media["source_url"],
                           "alt": alt, "w": w, "h": h}
        print(f"  アップロード: {fname} → ID {media['id']}")
        time.sleep(0.5)

    # 2. プレースホルダ置換
    def replace(m: re.Match) -> str:
        fname = m.group(1)
        u = uploaded.get(fname)
        if not u:
            return ""  # 撮影スキップ等で実体が無い場合は除去
        size_attr = f' width="{u["w"]}" height="{u["h"]}"' if u["w"] else ""
        return (f'<img class="alignnone size-full wp-image-{u["id"]}" '
                f'src="{u["url"]}" alt="{u["alt"]}"{size_attr} />')

    html = re.sub(r"\{\{IMG:([^}]+)\}\}", replace, html)
    if "{{IMG:" in html:
        die("未解決の画像プレースホルダが残っています")

    # 3. カテゴリ・タグ
    payload = {
        "title": meta["title"],
        "slug": meta.get("slug", ""),
        "content": html,
        "status": args.status,
    }
    if meta.get("category"):
        payload["categories"] = [wp.ensure_term("categories", meta["category"])]
    tags = [t.strip() for t in str(meta.get("tags", "")).split(",") if t.strip()]
    if tags:
        payload["tags"] = [wp.ensure_term("tags", t) for t in tags]
    if eyecatch_file and eyecatch_file in uploaded:
        payload["featured_media"] = uploaded[eyecatch_file]["id"]

    # 4. 投稿
    post = wp.create_post(payload)
    edit_url = f"{site['url'].rstrip('/')}/wp-admin/post.php?post={post['id']}&action=edit"
    print(f"\n投稿完了 ({args.status})")
    print(f"  記事ID : {post['id']}")
    print(f"  タイトル: {meta['title']}")
    print(f"  プレビュー: {post.get('link', '')}")
    print(f"  編集画面 : {edit_url}")
    if eyecatch_file and eyecatch_file in uploaded:
        print("  アイキャッチ: 設定済み")

    (outdir / "publish_result.json").write_text(json.dumps(
        {"post_id": post["id"], "link": post.get("link"), "edit_url": edit_url,
         "status": args.status,
         "media": {k: v["id"] for k, v in uploaded.items()}},
        ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
