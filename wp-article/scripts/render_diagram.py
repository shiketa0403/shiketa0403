#!/usr/bin/env python3
"""diagrams.json → PNG 生成（Playwright）。

使い方:
  python wp-article/scripts/render_diagram.py wp-article/out/<slug>

入力: <dir>/diagrams.json（書式は prompts/11_図解作成指示書.md 参照）
出力: <dir>/images/*.png と、各画像の実寸を追記した <dir>/diagrams_result.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Windows環境でstdoutがcp932になり日本語・記号の出力で落ちるのを防ぐ
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "diagram_template.html"


def main():
    if len(sys.argv) < 2:
        print("usage: render_diagram.py <out/slug dir>", file=sys.stderr)
        sys.exit(2)
    outdir = Path(sys.argv[1])
    spec_path = outdir / "diagrams.json"
    if not spec_path.exists():
        print(f"ERROR: {spec_path} がありません", file=sys.stderr)
        sys.exit(1)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    images_dir = outdir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    jobs = []
    if spec.get("eyecatch"):
        jobs.append(spec["eyecatch"])
    jobs.extend(spec.get("diagrams", []))
    if not jobs:
        print("ERROR: 描画対象がありません", file=sys.stderr)
        sys.exit(1)

    from playwright.sync_api import sync_playwright

    from pw_util import launch_chromium

    results = []
    with sync_playwright() as p:
        browser = launch_chromium(p)
        page = browser.new_page(viewport={"width": 1400, "height": 900},
                                device_scale_factor=1)
        page.goto(TEMPLATE.resolve().as_uri())
        page.wait_for_load_state("load")
        page.evaluate("document.fonts.ready")

        for job in jobs:
            fname = job.get("file")
            if not fname:
                print(f"  スキップ: fileが未指定 ({job.get('type')})", file=sys.stderr)
                continue
            try:
                if job.get("type") == "custom":
                    # 自由デザイン: out/<slug>/diagrams/*.html を直接描画。
                    # HTML内に id="canvas" の要素が必須（その範囲を撮影する）
                    html_path = (outdir / job["html"]).resolve()
                    if not html_path.exists():
                        raise FileNotFoundError(f"custom html not found: {html_path}")
                    page.goto(html_path.as_uri())
                    page.wait_for_load_state("load")
                    page.evaluate("document.fonts.ready")
                else:
                    page.goto(TEMPLATE.resolve().as_uri())
                    page.wait_for_load_state("load")
                    page.evaluate("document.fonts.ready")
                    page.evaluate("spec => render(spec)", job)
                page.wait_for_timeout(150)
                el = page.locator("#canvas")
                box = el.bounding_box()
                el.screenshot(path=str(images_dir / fname))
                results.append({"file": fname, "type": job.get("type"),
                                "alt": job.get("alt", ""),
                                "width": int(box["width"]), "height": int(box["height"])})
                print(f"  生成: {fname} ({int(box['width'])}x{int(box['height'])})")
            except Exception as e:
                print(f"  失敗: {fname}: {e}", file=sys.stderr)
                results.append({"file": fname, "error": str(e)})
        browser.close()

    (outdir / "diagrams_result.json").write_text(
        json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = [r for r in results if "error" not in r]
    print(f"完了: {len(ok)}/{len(results)} 枚生成 → {images_dir}")
    if len(ok) < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
