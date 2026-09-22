#!/usr/bin/env python3
"""
地域×現金化 記事の投稿スクリプト（credit-genkinka.heteml.net 向け）

- local-genkinka/articles/{area}.html を本文として読み込む
- local-genkinka/images_{area}.json があれば、指定のスクショをWPメディアに
  アップロードし、対応する <h3>見出し</h3> の直後に <img> を挿入する
  (アップロード失敗・ファイルなしの場合はimgなしで続行=省略ルール)
- WordPress REST API で投稿を作成する(既定: draft)

wp_config.py は呼び出し側(GitHub Actions)が生成する。

使い方:
  python genkinka_publish.py --area ikebukuro \
    --title "池袋のクレジットカード現金化店舗まとめ..." \
    --slug creditcard-genkinka-ikebukuro --status draft
"""

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from wp_post import create_post
from screenshot import upload_to_wordpress


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--area", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--status", default="draft")
    args = parser.parse_args()

    base = Path("local-genkinka")
    article_path = base / "articles" / f"{args.area}.html"
    if not article_path.exists():
        print(f"エラー: {article_path} が見つかりません", file=sys.stderr)
        sys.exit(1)
    content = article_path.read_text(encoding="utf-8")

    images_path = base / f"images_{args.area}.json"
    if images_path.exists():
        images = json.loads(images_path.read_text(encoding="utf-8"))
        for i, img in enumerate(images, 1):
            h3 = img["h3"]
            png = Path(img["png"])
            alt = img.get("alt", h3)
            anchor = f"<h3>{h3}</h3>"
            if anchor not in content:
                print(f"  [SKIP] 見出しが本文にありません: {h3}")
                continue
            if not png.exists():
                print(f"  [SKIP] 画像なし: {png}")
                continue
            # 日本語ファイル名はHTTPヘッダー(latin-1)で送れないため、ASCII名にコピーしてから上げる
            ascii_name = img.get("name") or f"{args.area}-shop-{i}"
            tmp_png = Path(tempfile.gettempdir()) / f"{ascii_name}.png"
            shutil.copyfile(png, tmp_png)
            result = upload_to_wordpress(tmp_png, title=alt)
            if not result or not result.get("url"):
                print(f"  [SKIP] アップロード失敗: {png}")
                continue
            tag = f'<img class="alignnone size-full" src="{result["url"]}" alt="{alt}" />'
            content = content.replace(anchor, anchor + "\n" + tag, 1)
            print(f"  画像挿入: {h3} -> {result['url']}")
    else:
        print(f"画像マップなし({images_path})。imgなしで投稿します")

    create_post(
        title=args.title,
        content=content,
        status=args.status,
        slug=args.slug,
    )


if __name__ == "__main__":
    main()
