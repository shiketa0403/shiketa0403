#!/usr/bin/env python3
"""
スクリーンショット取得 & WordPress メディアアップロード

使い方:
  # スクリーンショット取得のみ（ローカル保存）
  python screenshot.py capture --url "https://example.com" --output screenshot.png

  # スクリーンショット取得 + WordPress アップロード
  python screenshot.py capture --url "https://example.com" --upload

  # CSV から一括取得 + アップロード
  python screenshot.py bulk --csv csv/vc_raw_utf8.csv --upload
"""

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def get_wp_config():
    """wp_config.py から設定を読み込む"""
    try:
        from wp_config import WP_CONFIG
        return WP_CONFIG
    except ImportError:
        print("エラー: wp_config.py が見つかりません", file=sys.stderr)
        sys.exit(1)


def get_auth_header(config):
    credentials = f"{config['username']}:{config['app_password']}"
    token = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {token}"}


def take_screenshot(url, output_path, width=1280, height=800, wait_ms=10000):
    """Playwright でスクリーンショットを取得"""
    from playwright.sync_api import sync_playwright

    print(f"スクリーンショット取得中: {url}")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": width, "height": height},
            locale="ja-JP",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        )
        # ヘッドレス検出を回避
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)
        page = context.new_page()
        try:
            # domcontentloaded で待ち、その後 JS レンダリングを待つ
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            # networkidle も試みる（タイムアウトしても続行）
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            # JS レンダリング待機
            page.wait_for_timeout(wait_ms)
            # スクロールで遅延読み込みをトリガー
            page.evaluate("window.scrollTo(0, 300)")
            page.wait_for_timeout(2000)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(1000)
            # Cookie同意バナーなどを閉じる試み
            for selector in [
                'button:has-text("同意")', 'button:has-text("Accept")',
                'button:has-text("OK")', 'button:has-text("閉じる")',
                '[id*="cookie"] button', '[class*="cookie"] button',
                '[id*="consent"] button', '[class*="consent"] button',
            ]:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=500):
                        btn.click()
                        page.wait_for_timeout(1000)
                        break
                except Exception:
                    continue
            page.screenshot(path=str(output_path), full_page=False)
            print(f"  保存: {output_path}")
        except Exception as e:
            print(f"  エラー: {e}", file=sys.stderr)
            browser.close()
            return False
        browser.close()
    return True


def upload_to_wordpress(image_path, title=""):
    """WordPress REST API で画像をメディアアップロード"""
    config = get_wp_config()
    url = f"{config['site_url']}/wp-json/wp/v2/media"

    with open(image_path, "rb") as f:
        image_data = f.read()

    filename = os.path.basename(image_path)
    headers = get_auth_header(config)
    headers["Content-Type"] = "image/png"
    ascii_filename = filename.encode('ascii', 'ignore').decode()
    if not ascii_filename or ascii_filename == '.png':
        ascii_filename = f"screenshot-{int(time.time())}.png"
    headers["Content-Disposition"] = f'attachment; filename="{ascii_filename}"'

    req = urllib.request.Request(url, data=image_data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            image_url = result["source_url"]
            media_id = result["id"]
            print(f"  アップロード成功: ID={media_id}")
            print(f"  URL: {image_url}")
            return {"id": media_id, "url": image_url}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  アップロードエラー {e.code}: {error_body}", file=sys.stderr)
        return None
    except (urllib.error.URLError, OSError) as e:
        print(f"  アップロード接続エラー: {e}", file=sys.stderr)
        return None


def slugify(text):
    """テキストからファイル名用のASCIIスラッグを生成"""
    ascii_text = re.sub(r'[^\w\s-]', '', text, flags=re.ASCII)
    ascii_text = re.sub(r'[\s_]+', '-', ascii_text.strip().lower())
    if ascii_text:
        return ascii_text[:50]
    import hashlib
    return "ss-" + hashlib.md5(text.encode()).hexdigest()[:10]


def capture_and_upload(url, name="", output_dir="screenshots", upload=False):
    """スクリーンショット取得 → オプションでアップロード"""
    os.makedirs(output_dir, exist_ok=True)

    slug = slugify(name) if name else slugify(url.replace("https://", "").replace("http://", ""))
    filename = f"{slug}.png"
    output_path = Path(output_dir) / filename

    success = take_screenshot(url, output_path)
    if not success:
        return None

    # ファイルサイズが 20KB 未満 = ブロックされた可能性が高い（スキップ）
    file_size = os.path.getsize(output_path)
    if file_size < 20 * 1024:
        print(f"  スキップ: ファイルサイズが小さすぎます ({file_size} bytes) — サイトにブロックされた可能性")
        return {"file": str(output_path), "skipped": True, "reason": "blocked"}

    result = {"file": str(output_path), "skipped": False}

    if upload:
        wp_result = upload_to_wordpress(output_path, title=name)
        if wp_result:
            result.update(wp_result)

    return result


def bulk_capture(csv_path, output_dir="screenshots", upload=False, delay=2):
    """CSV から広告主サイトURLを取得し一括スクリーンショット"""
    import csv

    results = []
    seen_urls = set()

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("広告主サイトURL", "").strip()
            name = row.get("プログラム名", "").strip()

            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            # http → https
            if url.startswith("http://"):
                url = "https://" + url[7:]
            elif not url.startswith("https://"):
                url = "https://" + url

            result = capture_and_upload(url, name=name, output_dir=output_dir, upload=upload)
            if result:
                result["name"] = name
                result["url"] = url
                results.append(result)

            if delay > 0:
                time.sleep(delay)

    # 結果をJSONで出力
    output_json = Path(output_dir) / "results.json"
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n結果: {output_json} ({len(results)}件)")

    return results


def main():
    parser = argparse.ArgumentParser(description="スクリーンショット取得 & WordPress アップロード")
    sub = parser.add_subparsers(dest="command")

    # capture: 単体取得
    p_cap = sub.add_parser("capture", help="単体スクリーンショット取得")
    p_cap.add_argument("--url", required=True, help="対象URL")
    p_cap.add_argument("--name", default="", help="画像名")
    p_cap.add_argument("--output-dir", default="screenshots", help="出力ディレクトリ")
    p_cap.add_argument("--upload", action="store_true", help="WordPress にアップロード")

    # bulk: 一括取得
    p_bulk = sub.add_parser("bulk", help="CSV から一括取得")
    p_bulk.add_argument("--csv", required=True, help="CSVファイルパス")
    p_bulk.add_argument("--output-dir", default="screenshots", help="出力ディレクトリ")
    p_bulk.add_argument("--upload", action="store_true", help="WordPress にアップロード")
    p_bulk.add_argument("--delay", type=int, default=2, help="取得間隔（秒）")

    args = parser.parse_args()

    if args.command == "capture":
        result = capture_and_upload(
            args.url, name=args.name,
            output_dir=args.output_dir, upload=args.upload,
        )
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "bulk":
        bulk_capture(
            args.csv, output_dir=args.output_dir,
            upload=args.upload, delay=args.delay,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
