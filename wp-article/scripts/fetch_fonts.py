#!/usr/bin/env python3
"""図解用の日本語フォントをダウンロードする（初回セットアップ時に1回実行）。

Google Fonts（SIL Open Font License）から以下を取得して
wp-article/templates/fonts/ に保存する:

- Noto Sans JP        … 極太ゴシック（迫力・標準）可変フォント
- Zen Maru Gothic     … 丸ゴシック（ポップ・親しみ）Bold / Black
- Shippori Mincho     … 明朝（高級感・エレガント）SemiBold

使い方:
  python wp-article/scripts/fetch_fonts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

# Windows環境でstdoutがcp932になり日本語・記号の出力で落ちるのを防ぐ
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


FONTS_DIR = Path(__file__).resolve().parent.parent / "templates" / "fonts"
BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl"

FONTS = {
    "NotoSansJP.ttf": f"{BASE}/notosansjp/NotoSansJP%5Bwght%5D.ttf",
    "ZenMaruGothic-Bold.ttf": f"{BASE}/zenmarugothic/ZenMaruGothic-Bold.ttf",
    "ZenMaruGothic-Black.ttf": f"{BASE}/zenmarugothic/ZenMaruGothic-Black.ttf",
    "ShipporiMincho-SemiBold.ttf": f"{BASE}/shipporimincho/ShipporiMincho-SemiBold.ttf",
}


def main():
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for name, url in FONTS.items():
        dest = FONTS_DIR / name
        if dest.exists() and dest.stat().st_size > 100_000:
            print(f"  済: {name} ({dest.stat().st_size // 1024}KB)")
            ok += 1
            continue
        try:
            print(f"  取得中: {name} ...")
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            dest.write_bytes(r.content)
            print(f"  保存: {name} ({len(r.content) // 1024}KB)")
            ok += 1
        except Exception as e:
            print(f"  失敗: {name}: {e}", file=sys.stderr)
    print(f"完了: {ok}/{len(FONTS)} フォント → {FONTS_DIR}")
    if ok < len(FONTS):
        print("失敗したものは再実行で取得できます。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
