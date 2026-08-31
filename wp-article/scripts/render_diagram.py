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

# キャンバス外にはみ出したテキスト要素を検出するJS。
# 装飾図形（テキストを含まない要素）の意図的なはみ出しは対象外。
OVERFLOW_CHECK_JS = """
() => {
  const canvas = document.getElementById('canvas');
  if (!canvas) return [{tag: '(no #canvas)', text: '', overflow: {}}];
  const c = canvas.getBoundingClientRect();
  const tol = 4;
  const bad = [];
  for (const el of canvas.querySelectorAll('*')) {
    if (!(el.textContent || '').trim()) continue;  // 文字を含む要素だけ検査
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    const over = {
      right: Math.round(r.right - c.right),
      left: Math.round(c.left - r.left),
      bottom: Math.round(r.bottom - c.bottom),
      top: Math.round(c.top - r.top),
    };
    const dirs = {};
    for (const [k, v] of Object.entries(over)) if (v > tol) dirs[k] = v;
    if (Object.keys(dirs).length) {
      bad.push({
        tag: el.tagName.toLowerCase()
          + (el.className && typeof el.className === 'string'
             ? '.' + el.className.trim().split(/\\s+/).join('.') : ''),
        text: (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 24),
        overflow: dirs,
      });
    }
  }
  return bad.slice(0, 8);
}
"""


def check_overflow(page) -> list[dict]:
    """#canvas からはみ出しているテキスト要素の一覧を返す（空なら合格）。"""
    return page.evaluate(OVERFLOW_CHECK_JS)


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
                overflow = check_overflow(page)
                if overflow:
                    detail = "; ".join(
                        f"<{o['tag']}>「{o['text']}」が"
                        + "・".join(f"{k}に{v}px" for k, v in o["overflow"].items())
                        for o in overflow)
                    print(f"  ✗ はみ出し検出: {fname}", file=sys.stderr)
                    for o in overflow:
                        dirs = "・".join(f"{k}方向に{v}px" for k, v in o["overflow"].items())
                        print(f"     <{o['tag']}>「{o['text']}」 → {dirs} はみ出し",
                              file=sys.stderr)
                    print("     修正例: グリッド列は固定pxでなく 1fr 指定 / 子要素の固定widthを外す /"
                          " * {box-sizing:border-box} を確認 / パディング・gapの合計を見直す",
                          file=sys.stderr)
                    results.append({"file": fname, "type": job.get("type"),
                                    "alt": job.get("alt", ""),
                                    "width": int(box["width"]), "height": int(box["height"]),
                                    "error": f"canvas外はみ出し: {detail}"})
                    continue
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
