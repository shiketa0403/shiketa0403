"""スカパー公式サイト & CSチャンネルページのスクリーンショット取得。

Playwright を使うため、別環境（GitHub Actions）から実行する想定。
ローカル（このClaude Code環境）からは実行不可（プロキシ・ブラウザ無し）。

使い方:
    python -m skapa.screenshot エムオン
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import config, sheet_loader
from .sheet_loader import Channel


# 共通URL（全チャンネルで使う）
SKYPERFECTV_TOP_URL = "https://www.skyperfectv.co.jp/"
SKYPERFECTV_PLAN_URL = "https://www.skyperfectv.co.jp/plan/"

# Step 7 の出力からスカパー公式チャンネルURLを拾うパターン（basic配下のみ採用）
CHANNEL_URL_RE = re.compile(
    r'https://www\.skyperfectv\.co\.jp/plan/channel/basic/[0-9]+'
)


def extract_channel_url(slug: str) -> str | None:
    """Step 7の出力から該当チャンネルのスカパー公式URLを抽出。
    なければ None。
    """
    candidates_path = config.channel_draft_dir(slug) / "07_link_candidates.md"
    if not candidates_path.exists():
        return None
    text = candidates_path.read_text(encoding="utf-8")
    m = CHANNEL_URL_RE.search(text)
    return m.group(0) if m else None


def screenshots_dir(slug: str) -> Path:
    d = config.channel_draft_dir(slug) / "screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def take_screenshots(ch: Channel, *, viewport_width: int = 1280, viewport_height: int = 800) -> dict[str, Path]:
    """2枚のスクリーンショットを取得して保存パスを返す。

    1. スカパー公式（共通: トップページ）
    2. 該当チャンネルページ（あれば）/ なければスカパー申込ページ
    """
    from playwright.sync_api import sync_playwright

    out_dir = screenshots_dir(ch.slug)

    channel_url = extract_channel_url(ch.slug) or SKYPERFECTV_PLAN_URL
    targets = [
        ("skapa_top.png", SKYPERFECTV_TOP_URL, "スカパー公式"),
        ("channel_page.png", channel_url, "チャンネルページ"),
    ]

    results: dict[str, Path] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            locale="ja-JP",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        for filename, url, label in targets:
            print(f"[screenshot] {label}: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2500)  # JSレンダリング待機
                target = out_dir / filename
                page.screenshot(path=str(target), full_page=False)
                results[label] = target
                print(f"[screenshot]   -> {target}")
            except Exception as e:
                print(f"[screenshot]   ! 失敗: {e}", file=sys.stderr)

        browser.close()

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="スカパー記事用スクリーンショット取得")
    parser.add_argument("channel", help="チャンネル名 / 正式名称 / スラッグ / No")
    args = parser.parse_args()

    channels = sheet_loader.load_local()
    ch = sheet_loader.find(channels, args.channel)
    if not ch:
        print(f"エラー: チャンネルが見つかりません: {args.channel}", file=sys.stderr)
        return 1

    print(f"対象: No.{ch.no} {ch.name}（slug: {ch.slug}）")
    results = take_screenshots(ch)
    print(f"\n取得済みスクショ: {len(results)}/2")
    for label, path in results.items():
        print(f"  {label}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
