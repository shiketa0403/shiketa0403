"""
吉野家（または任意チェーン）の東京23区内全店舗をGoogle Places APIで取得し
csv/rocketnow_stores.csv に出力する。

使い方:
  python fetch_rocketnow_stores.py
  python fetch_rocketnow_stores.py --chain "松屋"
  python fetch_rocketnow_stores.py --chain "吉野家" --output csv/yoshinoya.csv
"""

import argparse
import csv
import os
import time
import requests

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# 東京23区の代表座標 (緯度, 経度)
TOKYO_23KU = [
    ("千代田区", 35.6940, 139.7536),
    ("中央区",   35.6706, 139.7727),
    ("港区",     35.6581, 139.7514),
    ("新宿区",   35.6938, 139.7034),
    ("文京区",   35.7078, 139.7519),
    ("台東区",   35.7126, 139.7817),
    ("墨田区",   35.7099, 139.8015),
    ("江東区",   35.6720, 139.8172),
    ("品川区",   35.6090, 139.7300),
    ("目黒区",   35.6418, 139.6985),
    ("大田区",   35.5617, 139.7159),
    ("世田谷区", 35.6464, 139.6531),
    ("渋谷区",   35.6640, 139.6982),
    ("中野区",   35.7075, 139.6634),
    ("杉並区",   35.6994, 139.6366),
    ("豊島区",   35.7281, 139.7194),
    ("北区",     35.7535, 139.7336),
    ("荒川区",   35.7350, 139.7827),
    ("板橋区",   35.7509, 139.7094),
    ("練馬区",   35.7357, 139.6522),
    ("足立区",   35.7751, 139.8044),
    ("葛飾区",   35.7337, 139.8481),
    ("江戸川区", 35.7066, 139.8686),
]

SEARCH_RADIUS_M = 3000  # 各区の代表座標から3km圏内を検索


def search_places(chain_name: str, lat: float, lng: float) -> list[dict]:
    """Places API (New) Text Search で店舗を検索する"""
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.location,places.regularOpeningHours,"
            "places.internationalPhoneNumber,places.googleMapsUri"
        ),
    }
    body = {
        "textQuery": f"{chain_name} 東京",
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": SEARCH_RADIUS_M,
            }
        },
        "languageCode": "ja",
        "maxResultCount": 20,
    }
    resp = requests.post(url, headers=headers, json=body, timeout=10)
    resp.raise_for_status()
    return resp.json().get("places", [])


def parse_place(place: dict, chain_name: str) -> dict:
    name = place.get("displayName", {}).get("text", "")
    address = place.get("formattedAddress", "")
    phone = place.get("internationalPhoneNumber", "")
    maps_url = place.get("googleMapsUri", "")
    loc = place.get("location", {})
    lat = loc.get("latitude", "")
    lng = loc.get("longitude", "")

    # 営業時間（平日テキスト）
    hours_raw = place.get("regularOpeningHours", {}).get("weekdayDescriptions", [])
    hours = " / ".join(hours_raw) if hours_raw else ""

    return {
        "chain": chain_name,
        "name": name,
        "address": address,
        "phone": phone,
        "lat": lat,
        "lng": lng,
        "hours": hours,
        "maps_url": maps_url,
        "place_id": place.get("id", ""),
    }


def fetch_stores(chain_name: str) -> list[dict]:
    seen_ids = set()
    stores = []

    for ku_name, lat, lng in TOKYO_23KU:
        print(f"  検索中: {ku_name} ({lat}, {lng})")
        try:
            places = search_places(chain_name, lat, lng)
        except Exception as e:
            print(f"    エラー: {e}")
            time.sleep(2)
            continue

        for place in places:
            pid = place.get("id", "")
            if pid in seen_ids:
                continue
            # 店舗名にチェーン名が含まれるもののみ対象
            display = place.get("displayName", {}).get("text", "")
            if chain_name not in display:
                continue
            seen_ids.add(pid)
            stores.append(parse_place(place, chain_name))

        time.sleep(0.3)  # レート制限対策

    return stores


def save_csv(stores: list[dict], output_path: str):
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    fieldnames = ["chain", "name", "address", "phone", "lat", "lng", "hours", "maps_url", "place_id"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stores)
    print(f"\n保存完了: {output_path} ({len(stores)} 件)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain", default="吉野家", help="チェーン名（例: 吉野家）")
    parser.add_argument("--output", default="csv/rocketnow_stores.csv", help="出力CSVパス")
    args = parser.parse_args()

    if not GOOGLE_MAPS_API_KEY:
        print("エラー: 環境変数 GOOGLE_MAPS_API_KEY が設定されていません")
        return

    print(f"=== {args.chain} の東京23区内店舗を取得します ===")
    stores = fetch_stores(args.chain)
    print(f"\n取得完了: {len(stores)} 店舗")
    save_csv(stores, args.output)

    # プレビュー（先頭5件）
    print("\n--- 先頭5件プレビュー ---")
    for s in stores[:5]:
        print(f"  {s['name']} | {s['address']} | {s['hours'][:30] if s['hours'] else '時間不明'}")


if __name__ == "__main__":
    main()
