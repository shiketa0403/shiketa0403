#!/usr/bin/env python3
"""
地域×現金化 業者マスタの裏取りスクリプト

local-genkinka/master_{area}.csv の各業者を Google Places API (New) で検証し、
営業状態(営業中/閉業)・正式住所・緯度経度・電話・公式サイト・営業時間を取得して
local-genkinka/verify_{area}.csv に書き出す。

--screenshots 指定時は、公式サイト(マスタ記載 + Places取得)のスクリーンショットを
local-genkinka/screenshots/{area}/ に保存する(20KB未満はブロック判定でスキップ)。

使い方:
  GOOGLE_PLACES_API_KEY=xxx python local_genkinka_verify.py --area ikebukuro --screenshots

注意:
- Places APIは「検証」専用。レビュー本文は取得・保存しない(Maps Platform規約)。
  評価点・件数のみ参考値として記録する。
"""

import argparse
import csv
import difflib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

PLACES_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.businessStatus",
    "places.location",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.regularOpeningHours.weekdayDescriptions",
    "places.rating",
    "places.userRatingCount",
])

STATUS_JA = {
    "OPERATIONAL": "営業中",
    "CLOSED_TEMPORARILY": "一時休業",
    "CLOSED_PERMANENTLY": "閉業",
    "": "不明",
}


def search_places(api_key, query, max_results=3):
    body = json.dumps({
        "textQuery": query,
        "languageCode": "ja",
        "regionCode": "JP",
        "maxResultCount": max_results,
    }).encode("utf-8")
    req = urllib.request.Request(
        PLACES_ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8")).get("places", [])
    except urllib.error.HTTPError as e:
        print(f"  [ERROR] Places API {e.code}: {e.read().decode('utf-8')[:200]}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  [ERROR] Places API: {e}", file=sys.stderr)
        return []


def normalize_name(name):
    name = re.sub(r"[\s　()（）・]", "", name)
    return name.lower()


def name_similarity(a, b):
    return round(difflib.SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio(), 2)


def safe_filename(name):
    return re.sub(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠ー]", "_", name)[:40]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--area", required=True, help="エリア名 (master_{area}.csv)")
    parser.add_argument("--screenshots", action="store_true", help="公式サイトのスクショも取得")
    parser.add_argument("--max-results", type=int, default=3)
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    if not api_key:
        print("エラー: 環境変数 GOOGLE_PLACES_API_KEY が未設定です", file=sys.stderr)
        sys.exit(1)

    base = Path("local-genkinka")
    master_path = base / f"master_{args.area}.csv"
    if not master_path.exists():
        print(f"エラー: {master_path} が見つかりません", file=sys.stderr)
        sys.exit(1)

    with open(master_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"マスタ読み込み: {master_path} ({len(rows)}件)")

    out_rows = []
    screenshot_targets = {}  # 業者名 -> set(url)

    for row in rows:
        gyosha = row.get("業者名", "").strip()
        area_ja = row.get("エリア", "").strip()
        if not gyosha:
            continue
        query = f"{gyosha} {area_ja}"
        print(f"検索: {query}")
        places = search_places(api_key, query, args.max_results)
        if not places:
            out_rows.append({
                "入力業者名": gyosha, "候補順位": 0, "名称": "(候補なし)",
                "営業状態": "候補なし", "住所": "", "電話": "", "公式サイト": "",
                "緯度": "", "経度": "", "営業時間": "", "評価点": "", "評価件数": "",
                "名称類似度": "",
            })
            continue
        for i, p in enumerate(places, 1):
            disp = p.get("displayName", {}).get("text", "")
            status = STATUS_JA.get(p.get("businessStatus", ""), p.get("businessStatus", "不明"))
            loc = p.get("location", {})
            hours = " / ".join(p.get("regularOpeningHours", {}).get("weekdayDescriptions", []))
            website = p.get("websiteUri", "")
            out_rows.append({
                "入力業者名": gyosha,
                "候補順位": i,
                "名称": disp,
                "営業状態": status,
                "住所": p.get("formattedAddress", ""),
                "電話": p.get("nationalPhoneNumber", ""),
                "公式サイト": website,
                "緯度": loc.get("latitude", ""),
                "経度": loc.get("longitude", ""),
                "営業時間": hours,
                "評価点": p.get("rating", ""),
                "評価件数": p.get("userRatingCount", ""),
                "名称類似度": name_similarity(gyosha, disp),
            })
            if i == 1 and website:
                screenshot_targets.setdefault(gyosha, set()).add(website)

        # マスタ記載の公式サイトもスクショ対象に加える
        master_url = row.get("公式サイト", "").strip()
        if master_url.startswith("http"):
            screenshot_targets.setdefault(gyosha, set()).add(master_url)

    out_path = base / f"verify_{args.area}.csv"
    fieldnames = ["入力業者名", "候補順位", "名称", "営業状態", "住所", "電話", "公式サイト",
                  "緯度", "経度", "営業時間", "評価点", "評価件数", "名称類似度"]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"検証結果を書き出し: {out_path} ({len(out_rows)}行)")

    if args.screenshots and screenshot_targets:
        from screenshot import take_screenshot  # 既存スクリプトを流用
        shot_dir = base / "screenshots" / args.area
        shot_dir.mkdir(parents=True, exist_ok=True)
        for gyosha, urls in screenshot_targets.items():
            for j, url in enumerate(sorted(urls), 1):
                out_png = shot_dir / f"{safe_filename(gyosha)}_{j}.png"
                try:
                    take_screenshot(url, str(out_png))
                    if out_png.exists() and out_png.stat().st_size < 20 * 1024:
                        print(f"  [SKIP] 20KB未満(ブロック判定): {url}")
                        out_png.unlink()
                except Exception as e:
                    print(f"  [ERROR] スクショ失敗 {url}: {e}", file=sys.stderr)
        print(f"スクリーンショット保存先: {shot_dir}")


if __name__ == "__main__":
    main()
