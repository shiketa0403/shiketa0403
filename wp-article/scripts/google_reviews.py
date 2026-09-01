#!/usr/bin/env python3
"""Googleマップの評点・レビューを Places API で取得する。

使い方:
  python wp-article/scripts/google_reviews.py "オリエント工業 上野ショールーム" --out wp-article/out/<slug>
  python wp-article/scripts/google_reviews.py "店舗名や住所を含む検索語" --out ... --max-places 2

APIキーの取得順:
  1. wp-article/config/sites.local.json の "_google_maps_api_key"
  2. 環境変数 GOOGLE_MAPS_API_KEY

Places API (New) を優先し、失敗したら旧版 Places API にフォールバックする
（Google Cloud側でどちらが有効化されていても動く）。

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

# Places API (New)
NEW_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
NEW_FIELD_MASK = ",".join([
    "places.displayName", "places.rating", "places.userRatingCount",
    "places.formattedAddress", "places.googleMapsUri", "places.reviews",
])

# 旧版 Places API
LEGACY_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
LEGACY_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
LEGACY_DETAIL_FIELDS = "name,rating,user_ratings_total,reviews,formatted_address,url"

HINT = """  取得に失敗しました。Google Cloud Console で次の3点を確認してください:
  1. 課金の有効化: 「お支払い」でプロジェクトに課金アカウントが紐付いているか
     （Places APIは無料枠内の利用でも課金設定が必須）
  2. APIの有効化: 「APIとサービス → ライブラリ」で「Places API (New)」を有効にする
     （「Places API」(旧版)しか無い場合はそちらでも可）
  3. キーの制限: 「認証情報 → 該当キー → APIの制限」で
     Places API (New) / Places API が許可されているか（「キーを制限しない」なら問題なし）"""


class PlacesError(Exception):
    pass


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


# ---------------------------------------------------------------- Places API (New)

def fetch_new_api(query: str, key: str, max_places: int) -> list[dict]:
    r = requests.post(
        NEW_SEARCH_URL,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": NEW_FIELD_MASK,
        },
        json={"textQuery": query, "languageCode": "ja", "regionCode": "JP",
              "pageSize": max(1, min(max_places, 20))},
        timeout=30,
    )
    data = r.json() if r.content else {}
    if r.status_code != 200:
        msg = (data.get("error") or {}).get("message", r.text[:300])
        raise PlacesError(f"Places API (New) HTTP {r.status_code}: {msg}")
    places = []
    for p in data.get("places", [])[:max_places]:
        reviews = [{
            "rating": rv.get("rating"),
            "time_description": rv.get("relativePublishedTimeDescription", ""),
            "text": ((rv.get("text") or {}).get("text") or "")[:500],
        } for rv in p.get("reviews", [])[:5]]
        places.append({
            "name": (p.get("displayName") or {}).get("text", ""),
            "address": p.get("formattedAddress", ""),
            "rating": p.get("rating"),
            "user_ratings_total": p.get("userRatingCount"),
            "maps_url": p.get("googleMapsUri", ""),
            "reviews": reviews,
        })
    return places


# ---------------------------------------------------------------- 旧版 Places API

def legacy_get(url: str, params: dict) -> dict:
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    status = data.get("status", "")
    if status not in ("OK", "ZERO_RESULTS"):
        raise PlacesError(f"旧版 Places API {status}: {data.get('error_message', '')}")
    return data


def fetch_legacy_api(query: str, key: str, max_places: int) -> list[dict]:
    search = legacy_get(LEGACY_SEARCH_URL, {"query": query, "language": "ja",
                                            "region": "jp", "key": key})
    places = []
    for c in search.get("results", [])[:max_places]:
        det = legacy_get(LEGACY_DETAILS_URL, {
            "place_id": c["place_id"], "fields": LEGACY_DETAIL_FIELDS,
            "language": "ja", "reviews_sort": "most_relevant", "key": key,
        }).get("result", {})
        reviews = [{
            "rating": rv.get("rating"),
            "time_description": rv.get("relative_time_description", ""),
            "text": (rv.get("text") or "")[:500],
        } for rv in det.get("reviews", [])[:5]]
        places.append({
            "name": det.get("name", c.get("name", "")),
            "address": det.get("formatted_address", ""),
            "rating": det.get("rating"),
            "user_ratings_total": det.get("user_ratings_total"),
            "maps_url": det.get("url", ""),
            "reviews": reviews,
        })
    return places


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="検索語（例: 'オリエント工業 上野ショールーム'）")
    ap.add_argument("--out", required=True, help="出力先ディレクトリ (out/<slug>)")
    ap.add_argument("--max-places", type=int, default=2, help="取得する店舗数の上限")
    args = ap.parse_args()

    key = get_api_key()

    places = None
    errors = []
    for label, fetch in (("Places API (New)", fetch_new_api),
                         ("旧版 Places API", fetch_legacy_api)):
        try:
            places = fetch(args.query, key, args.max_places)
            print(f"[情報] {label} で取得しました")
            break
        except PlacesError as e:
            errors.append(str(e))
        except requests.RequestException as e:
            errors.append(f"{label} 通信エラー: {e}")

    if places is None:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print(HINT, file=sys.stderr)
        sys.exit(1)

    if not places:
        print(f"該当なし: 「{args.query}」でGoogleマップに店舗が見つかりませんでした")
    else:
        for place in places:
            print(f"  {place['name']}: 評価 {place['rating']}"
                  f"（{place['user_ratings_total']}件） レビュー取得 {len(place['reviews'])}件")

    result = {"query": args.query, "places": places}
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / "google_reviews.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"保存: {out_path}")


if __name__ == "__main__":
    main()
