"""スカパー公式サイト & 各CSサービスのチャンネルページのスクリーンショット取得。

Playwright を使うため、別環境（GitHub Actions）から実行する想定。
ローカル（このClaude Code環境）からは実行不可（プロキシ・ブラウザ無し）。

新テンプレ対応：
- channel_notes/{slug}.md の「視聴可能サービスマトリクス」から
  各サービス（スカパー／ひかりTV／auひかりTV／J:COM）の個別ページURLを抽出
- マトリクスで ✓ のサービスのみスクショ取得
- ケーブルテレビ（J:COM以外）はスクショ対象外

旧テンプレ対応（互換性のため残す）：
- 07_link_candidates.md からスカパー公式チャンネルURLを抽出
- skapa_top.png（スカパー公式トップ）、channel_page.png（チャンネル個別）

使い方:
    python -m skapa.screenshot AT-X
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


# サービス名 → スクショファイル名・IMGラベル のマッピング
SERVICE_TO_FILENAME = {
    "スカパー": "skapa.png",
    "ひかりTV": "hikari_tv.png",
    "auひかりTV": "au_hikari_tv.png",
    "J:COM": "jcom.png",
}

# チャンネル公式TOPページの抽出パターン（channel_notes/{slug}.md の `## 公式サイト` セクション）
CHANNEL_OFFICIAL_URL_RE = re.compile(
    r"##\s*公式サイト\s*\n+(?:- )?TOP[：:]\s*(https?://\S+)",
    re.MULTILINE,
)


def extract_channel_official_url(slug: str) -> str | None:
    """channel_notes/{slug}.md の `## 公式サイト - TOP: URL` を抽出。"""
    notes_path = config.KNOWLEDGE_DIR / "channel_notes" / f"{slug}.md"
    if not notes_path.exists():
        return None
    text = notes_path.read_text(encoding="utf-8")
    m = CHANNEL_OFFICIAL_URL_RE.search(text)
    return m.group(1).rstrip(")）") if m else None


def extract_channel_url(slug: str) -> str | None:
    """Step 7の出力から該当チャンネルのスカパー公式URLを抽出（旧テンプレ用・互換）。
    なければ None。
    """
    candidates_path = config.channel_draft_dir(slug) / "07_link_candidates.md"
    if not candidates_path.exists():
        return None
    text = candidates_path.read_text(encoding="utf-8")
    m = CHANNEL_URL_RE.search(text)
    return m.group(0) if m else None


def parse_service_matrix(slug: str) -> dict[str, str]:
    """channel_notes/{slug}.md の視聴可能サービスマトリクスから
    サービス名 → 個別ページURL の辞書を返す。

    マトリクスで ✓ かつ URL が空欄でないサービスのみ含まれる。
    対応サービス：スカパー / ひかりTV / auひかりTV / J:COM
    """
    notes_path = config.KNOWLEDGE_DIR / "channel_notes" / f"{slug}.md"
    if not notes_path.exists():
        return {}

    text = notes_path.read_text(encoding="utf-8")

    # マトリクスセクションを抽出
    matrix_match = re.search(
        r"## 視聴可能サービスマトリクス.*?\n((?:\|.+\n)+)",
        text,
        re.DOTALL,
    )
    if not matrix_match:
        return {}

    matrix_block = matrix_match.group(1)
    result: dict[str, str] = {}

    # サービス名の判定パターン
    # 注意: 「auひかり」を「ひかりTV」より先に評価する（「auひかりTV」が
    # r"ひかりTV" に部分一致して誤判定するのを防ぐ）。dictは挿入順を保持する。
    service_patterns = {
        "auひかりTV": re.compile(r"au\s*ひかり", re.IGNORECASE),
        "ひかりTV": re.compile(r"ひかりTV", re.IGNORECASE),
        "スカパー": re.compile(r"スカパー"),
        "J:COM": re.compile(r"J\s*[:：]\s*COM", re.IGNORECASE),
    }
    # URLを拾うパターン
    url_re = re.compile(r"https?://[^\s|）)]+")

    for line in matrix_block.splitlines():
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 7:
            continue

        service_cell = cells[0]
        # ヘッダー行はスキップ
        if service_cell in ("サービス", ""):
            continue

        # ケーブルテレビ（J:COM以外）は対象外（ユーザー指示によりスクショ取らない）
        if "ケーブルテレビ" in service_cell:
            continue

        kahi_cell = cells[1]
        url_cell = cells[6] if len(cells) > 6 else ""

        # 可否が ✓ でなければスキップ
        if "✓" not in kahi_cell:
            continue

        # サービス名特定
        matched_service: str | None = None
        for svc_name, pat in service_patterns.items():
            if pat.search(service_cell):
                matched_service = svc_name
                break
        if matched_service is None:
            continue

        # URL抽出（URL列にhttp〜が含まれる場合のみ）
        url_match = url_re.search(url_cell)
        if not url_match:
            continue

        result[matched_service] = url_match.group(0)

    return result


def screenshots_dir(slug: str) -> Path:
    d = config.channel_draft_dir(slug) / "screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def take_screenshots(ch: Channel, *, viewport_width: int = 1280, viewport_height: int = 800) -> dict[str, Path]:
    """サービス別スクリーンショットを取得して保存パスを返す。

    新テンプレ（マトリクス対応）：
    - channel_notes マトリクスから ✓ サービスのURL取得 → 各サービス分撮影
    - ファイル名: skapa.png / hikari_tv.png / au_hikari_tv.png / jcom.png

    旧テンプレ互換（マトリクスがない場合）：
    - skapa_top.png（スカパー公式トップ）
    - channel_page.png（チャンネル個別）
    """
    from playwright.sync_api import sync_playwright

    out_dir = screenshots_dir(ch.slug)

    # マトリクスから取得を試みる
    service_urls = parse_service_matrix(ch.slug)

    targets: list[tuple[str, str, str]] = []

    if service_urls:
        # 新テンプレ：マトリクス対応
        # チャンネル公式TOPページも撮影（H2「〇〇とは」直下に挿入）
        official_url = extract_channel_official_url(ch.slug)
        if official_url:
            targets.append(("channel_official.png", official_url, "チャンネル公式"))
        for svc_name, url in service_urls.items():
            filename = SERVICE_TO_FILENAME[svc_name]
            targets.append((filename, url, svc_name))
    else:
        # 旧テンプレ互換
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
    print(f"\n取得済みスクショ: {len(results)}")
    for label, path in results.items():
        print(f"  {label}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
