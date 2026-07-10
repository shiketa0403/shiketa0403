"""公式ページの事実確認スクリプト（記事作成前のファクトチェック）。

channel_notes の視聴可能サービスマトリクス・公式サイト・参照URLを
Playwright で実際に開き、以下を抽出して fact_check.md に保存する:

- 最終URL（リダイレクト検出）
- ページタイトル
- 本文テキスト（先頭部分）
- 料金らしき表記（〜円）の一覧
- 提供終了・404 などの警告キーワード検出

使用例:
    python3 -m skapa.fact_check エムオン
    python3 -m skapa.fact_check mtv

GitHub Actions（skapa_fact_check.yml）から実行し、結果をコミットする運用。
Claude Code はこの fact_check.md を読んでから記事を執筆することで、
検索結果の古い情報ではなく公式ページの現在の記載を根拠にできる。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import config, sheet_loader
from .screenshot import parse_service_matrix, extract_channel_official_url

# 提供終了・エラーを疑うキーワード
WARNING_KEYWORDS = [
    "提供を終了",
    "サービスを終了",
    "販売を終了",
    "放送を終了",
    "配信を終了",
    "終了いたしました",
    "終了しました",
    "ページが見つかりません",
    "お探しのページ",
    "404",
    "Not Found",
    "現在提供しておりません",
    "取り扱いがありません",
]

# 料金表記の抽出（例: 1,199円 / 770円）
PRICE_RE = re.compile(r"(?:月額)?[0-9][0-9,]{0,6}円(?:（税込）|\(税込\))?")


def collect_urls(slug: str) -> list[tuple[str, str]]:
    """channel_notes からチェック対象URLを (ラベル, URL) で集める。"""
    targets: list[tuple[str, str]] = []

    official = extract_channel_official_url(slug)
    if official:
        targets.append(("チャンネル公式TOP", official))

    for svc_name, url in parse_service_matrix(slug).items():
        targets.append((f"マトリクス:{svc_name}", url))

    # channel_notes の「参照URL」セクションからも収集（重複は除外）
    notes_path = config.channel_notes_path(slug)
    if notes_path.exists():
        text = notes_path.read_text(encoding="utf-8")
        m = re.search(r"##\s*参照URL\s*\n((?:- .+\n?)+)", text)
        if m:
            seen = {u for _, u in targets}
            for line in m.group(1).splitlines():
                url = line.lstrip("- ").strip()
                if url.startswith("http") and url not in seen and "wikipedia" not in url:
                    targets.append(("参照URL", url))
                    seen.add(url)

    return targets


def check_urls(targets: list[tuple[str, str]], *, timeout_ms: int = 30000) -> list[dict]:
    """各URLをPlaywrightで開き、事実確認用の情報を抽出する。"""
    from playwright.sync_api import sync_playwright

    results: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="ja-JP",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        for label, url in targets:
            entry: dict = {"label": label, "url": url}
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(2500)
                entry["status"] = resp.status if resp else None
                entry["final_url"] = page.url
                entry["title"] = page.title()
                body_text = page.inner_text("body")
                # 空白圧縮して先頭を保存
                compact = re.sub(r"\s+", " ", body_text).strip()
                entry["excerpt"] = compact[:2500]
                entry["prices"] = sorted(set(PRICE_RE.findall(compact)))[:20]
                entry["warnings"] = [kw for kw in WARNING_KEYWORDS if kw in compact or kw in entry["title"]]
                if entry["status"] and entry["status"] >= 400:
                    entry["warnings"].append(f"HTTP {entry['status']}")
                if entry["final_url"].rstrip("/") != url.rstrip("/"):
                    entry["warnings"].append(f"リダイレクト検出 → {entry['final_url']}")
            except Exception as e:  # noqa: BLE001
                entry["error"] = str(e)[:300]
            results.append(entry)
            print(f"[fact_check] {label}: {url}" + (" ⚠️" + "/".join(entry.get("warnings", [])) if entry.get("warnings") else " OK"))

        browser.close()
    return results


def render_markdown(ch, results: list[dict]) -> str:
    lines = [
        f"# 事実確認レポート: {ch.name}（{ch.slug}）",
        "",
        "GitHub Actions + Playwright で公式ページを直接取得した結果。",
        "**記事の料金・提供可否はこのレポートの記載を最優先の根拠とすること**（Web検索結果より優先）。",
        "",
    ]
    warn_total = sum(1 for r in results if r.get("warnings") or r.get("error"))
    lines.append(f"チェックURL数: {len(results)} ／ 警告あり: {warn_total}")
    lines.append("")

    for r in results:
        lines.append(f"## {r['label']}")
        lines.append("")
        lines.append(f"- URL: {r['url']}")
        if r.get("error"):
            lines.append(f"- ❌ 取得エラー: {r['error']}")
            lines.append("")
            continue
        lines.append(f"- HTTPステータス: {r.get('status')}")
        lines.append(f"- タイトル: {r.get('title', '')}")
        if r.get("warnings"):
            lines.append(f"- ⚠️ 警告: {' / '.join(r['warnings'])}")
        if r.get("prices"):
            lines.append(f"- 料金表記: {'、'.join(r['prices'])}")
        lines.append("")
        lines.append("### ページ本文（先頭抜粋）")
        lines.append("")
        lines.append("```")
        lines.append(r.get("excerpt", ""))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="公式ページの事実確認レポート生成")
    parser.add_argument("channel", help="チャンネル名 / 正式名称 / スラッグ / No")
    args = parser.parse_args()

    channels = sheet_loader.load_local()
    ch = sheet_loader.find(channels, args.channel)
    if not ch:
        print(f"エラー: チャンネルが見つかりません: {args.channel}", file=sys.stderr)
        return 1

    print(f"対象: No.{ch.no} {ch.name}（slug: {ch.slug}）")
    targets = collect_urls(ch.slug)
    if not targets:
        print("エラー: channel_notes にチェック対象URLがありません（マトリクス・公式TOPを先に記載してください）", file=sys.stderr)
        return 1

    results = check_urls(targets)
    out_dir = config.DRAFTS_DIR / ch.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "fact_check.md"
    out_path.write_text(render_markdown(ch, results), encoding="utf-8")
    print(f"\n出力: {out_path}")
    warn_total = sum(1 for r in results if r.get("warnings") or r.get("error"))
    print(f"チェックURL数: {len(results)} ／ 警告あり: {warn_total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
