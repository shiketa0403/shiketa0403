#!/usr/bin/env python3
"""Googleマップの評点・レビューを Places API で取得する。

使い方:
  python wp-article/scripts/google_reviews.py "オリエント工業 上野ショールーム" --out wp-article/out/<slug>
  python wp-article/scripts/google_reviews.py "店舗名や住所を含む検索語" --out ... --max-places 2

APIキーの取得順:
  1. wp-article/config/sites.local.json の "_google_maps_api_key"
  2. 環境変数 GOOGLE_MAPS_API_KEY

出力: <out>/google_reviews.json（評点・件数・代表レビュー最大5件/店舗）
- レビュー本文は記事に転載せず、要約の材料としてのみ使うこと（prompts/01・04参照）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

# Windows環境でstdoutがcp932になり日本語・記号の出力で落ちるのを防ぐ
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sites.local.json"
SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
DETAIL_FIELDS = "name,rating,user_ratings_total,reviews,formatted_address,url"


def get_api_key() -> str:
    if CONFIG_PATH.exists():
        try:
            conf = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            key = conf.get("_google_maps_api_key", "")
            if key and "YOUR_" not in key:
                return key
        except Exception:
            pass
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if key:
        return key
    print("ERROR: Google Maps APIキーが見つかりません。\n"
          "  sites.local.json に \"_google_maps_api_key\": \"...\" を追加するか、\n"
          "  環境変数 GOOGLE_MAPS_API_KEY を設定してください。", file=sys.stderr)
    sys.exit(1)


def api_get(url: str, params: dict) -> dict:
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    status = data.get("status", "")
    if status not in ("OK", "ZERO_RESULTS"):
        msg = data.get("error_message", "")
        hint = ""
        if status == "REQUEST_DENIED":
            hint = ("\n  Places API が有効化されていないか、キーのAPI制限で弾かれています。"
                    "\n  Google Cloud Console → APIライブラリ → Places API → 有効にする を確認してください。")
        print(f"ERROR: Places API {status}: {msg}{hint}", file=sys.stderr)
        sys.exit(1)
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="検索語（例: 'オリエント工業 上野ショールーム'）")
    ap.add_argument("--out", required=True, help="出力先ディレクトリ (out/<slug>)")
    ap.add_argument("--max-places", type=int, default=2, help="取得する店舗数の上限")
    args = ap.parse_args()

    key = get_api_key()

    search = api_get(SEARCH_URL, {"query": args.query, "language": "ja",
                                  "region": "jp", "key": key})
    candidates = search.get("results", [])[:args.max_places]
    if not candidates:
        print(f"該当なし: 「{args.query}」でGoogleマップに店舗が見つかりませんでした")
        result = {"query": args.query, "places": []}
    else:
        places = []
        for c in candidates:
            det = api_get(DETAILS_URL, {
                "place_id": c["place_id"], "fields": DETAIL_FIELDS,
                "language": "ja", "reviews_sort": "most_relevant", "key": key,
            }).get("result", {})
            reviews = [{
                "rating": rv.get("rating"),
                "time_description": rv.get("relative_time_description", ""),
                "text": (rv.get("text") or "")[:500],
            } for rv in det.get("reviews", [])[:5]]
            place = {
                "name": det.get("name", c.get("name", "")),
                "address": det.get("formatted_address", ""),
                "rating": det.get("rating"),
                "user_ratings_total": det.get("user_ratings_total"),
                "maps_url": det.get("url", ""),
                "reviews": reviews,
            }
            places.append(place)
            print(f"  {place['name']}: 評価 {place['rating']}"
                  f"（{place['user_ratings_total']}件） レビュー取得 {len(reviews)}件")
        result = {"query": args.query, "places": places}

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / "google_reviews.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"保存: {out_path}")


if __name__ == "__main__":
    main()
