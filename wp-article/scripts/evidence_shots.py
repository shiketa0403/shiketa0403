#!/usr/bin/env python3
"""shots.json → エビデンススクショ撮影（Playwright）。

使い方:
  python wp-article/scripts/evidence_shots.py wp-article/out/<slug>

入力: <dir>/shots.json（書式は prompts/12_エビデンス撮影指示書.md 参照）
出力: <dir>/images/*.png と <dir>/shots_result.json

ルール:
- 毎回新規コンテキスト（シークレットモード相当）
- selector指定があればその要素のみ、full_page=true なら全ページ、どちらも無ければビューポート
- 20KB未満はボットブロックとみなし削除してスキップ扱い
- 出典URL・日付の帯は付けない（画像そのまま）
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Windows環境でstdoutがcp932になり日本語・記号の出力で落ちるのを防ぐ
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
MIN_BYTES = 20 * 1024


def capture(page, shot: dict, out_path: Path) -> dict:
    url = shot["url"]
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass
    page.wait_for_timeout(3500)

    # Cookie同意バナー・年齢確認モーダル等を閉じる試み
    for sel in ['button:has-text("はい")', 'a:has-text("はい")',
                'button:has-text("18歳以上")', 'a:has-text("18歳以上")',
                'button:has-text("ENTER")', 'a:has-text("ENTER")',
                'button:has-text("同意")', 'button:has-text("Accept")',
                'button:has-text("OK")', 'button:has-text("閉じる")',
                '[id*="cookie"] button', '[class*="cookie"] button',
                '[id*="consent"] button', '[class*="consent"] button']:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=400):
                btn.click()
                page.wait_for_timeout(800)
                break
        except Exception:
            continue

    # 遅延読み込みを軽くトリガー
    page.evaluate("window.scrollTo(0, 400)")
    page.wait_for_timeout(1200)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(600)

    selector = shot.get("selector")
    if selector:
        el = page.locator(selector).first
        el.scroll_into_view_if_needed(timeout=8000)
        page.wait_for_timeout(500)
        el.screenshot(path=str(out_path))
    elif shot.get("full_page"):
        page.screenshot(path=str(out_path), full_page=True)
    else:
        page.screenshot(path=str(out_path), full_page=False)

    size = out_path.stat().st_size
    if size < MIN_BYTES:
        out_path.unlink(missing_ok=True)
        return {"status": "skipped", "reason": f"サイズ{size}B<20KB（ボットブロックの可能性）"}
    return {"status": "ok", "bytes": size}


def main():
    if len(sys.argv) < 2:
        print("usage: evidence_shots.py <out/slug dir>", file=sys.stderr)
        sys.exit(2)
    outdir = Path(sys.argv[1])
    shots_path = outdir / "shots.json"
    if not shots_path.exists():
        print(f"ERROR: {shots_path} がありません", file=sys.stderr)
        sys.exit(1)
    conf = json.loads(shots_path.read_text(encoding="utf-8"))
    shots = conf.get("shots", [])

    images_dir = outdir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    from pw_util import launch_chromium

    results = []
    with sync_playwright() as p:
        browser = launch_chromium(p, args=["--disable-blink-features=AutomationControlled"])
        for shot in shots:
            fname = shot.get("file")
            if not fname:
                continue
            out_path = images_dir / fname
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="ja-JP", user_agent=UA)
            ctx.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>false});")
            page = ctx.new_page()
            try:
                r = capture(page, shot, out_path)
            except Exception as e:
                out_path.unlink(missing_ok=True)
                r = {"status": "error", "reason": str(e)[:200]}
            ctx.close()
            r.update({"file": fname, "url": shot.get("url"),
                      "priority": shot.get("priority")})
            results.append(r)
            mark = {"ok": "✓", "skipped": "スキップ", "error": "失敗"}[r["status"]]
            print(f"  [{mark}] {fname} {r.get('reason', '')}")
            time.sleep(1.5)
        browser.close()

    manual = conf.get("manual_shots", [])
    out = {"results": results, "manual_shots": manual}
    (outdir / "shots_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"完了: 撮影 {ok}/{len(results)} 枚"
          + (f" / 手動撮影リスト {len(manual)} 件" if manual else ""))


if __name__ == "__main__":
    main()
