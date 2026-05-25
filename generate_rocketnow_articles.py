"""
csv/rocketnow_stores.csv から記事HTMLを生成し
csv/rocketnow_post.csv（WP投稿フォーマット）に出力する。

使い方:
  python generate_rocketnow_articles.py
  python generate_rocketnow_articles.py --input csv/yoshinoya.csv --output csv/yoshinoya_post.csv
"""

import argparse
import csv
import os
import re

import pykakasi

_kks = pykakasi.kakasi()


def to_romaji(text: str) -> str:
    result = _kks.convert(text)
    parts = [item["hepburn"] for item in result if item["hepburn"].strip()]
    slug = "-".join(parts)
    slug = re.sub(r"-+", "-", slug).strip("-").lower()
    return slug


# チェーンごとのメニュー情報（手動メンテ）
CHAIN_MENU = {
    "吉野家": {
        "genre": "牛丼・丼もの",
        "items": [
            ("牛丼（並）", "468円"),
            ("牛丼（中）", "528円"),
            ("牛丼（大）", "583円"),
            ("牛丼（特盛）", "759円"),
            ("牛丼（超特盛）", "869円"),
            ("牛丼（メガ）", "979円"),
            ("牛カルビ丼（並）", "748円"),
            ("牛カルビ丼（大）", "858円"),
            ("豚丼（並）", "436円"),
            ("豚丼（大）", "551円"),
            ("牛皿定食（並）", "638円"),
            ("から揚げ定食", "748円"),
            ("牛鮭定食", "748円"),
        ],
    },
}

DEFAULT_MENU = {
    "genre": "飲食",
    "items": [],
}


def make_title(store_name: str) -> str:
    return f"ロケットナウで{store_name}は頼める？配達料・メニュー・営業時間まとめ"


def make_slug(store_name: str, chain_name: str = "", fallback_id: str = "") -> str:
    # 店舗名から「チェーン名」と末尾の「店」を除外してローマ字化
    # 例: "吉野家 水道橋三崎町店" → "水道橋三崎町" → "suidobashi-misakicho"
    base = store_name
    if chain_name:
        base = base.replace(chain_name, "")
    base = re.sub(r"店$", "", base.strip())
    base = base.strip()
    slug = to_romaji(base) if base else ""
    if not slug:
        slug = f"store-{fallback_id[:8]}" if fallback_id else "store"
    return slug


def format_phone(phone: str) -> str:
    """+81 3-3515-2454 → 03-3515-2454 に整形"""
    if not phone:
        return "要確認"
    phone = phone.strip()
    if phone.startswith("+81"):
        rest = phone[3:].lstrip()
        if rest.startswith("-"):
            rest = rest[1:]
        return "0" + rest
    return phone


def make_maps_embed(lat, lng) -> str:
    if not lat or not lng:
        return ""
    return (
        f'<iframe src="https://maps.google.com/maps?q={lat},{lng}&z=16&output=embed" '
        f'width="100%" height="300" style="border:0;" allowfullscreen="" loading="lazy"></iframe>'
    )


def make_hours_display(hours: str) -> str:
    if not hours:
        return "要確認"
    lines = [h.strip() for h in hours.split("/")]
    return "<br>".join(lines)


def build_html(store: dict, chain_name: str) -> str:
    menu_info = CHAIN_MENU.get(chain_name, DEFAULT_MENU)
    title_name = store["name"]
    hours_html = make_hours_display(store.get("hours", ""))
    maps_embed = make_maps_embed(store.get("lat"), store.get("lng"))

    # メニューHTML
    menu_rows = ""
    for item_name, price in menu_info.get("items", []):
        menu_rows += f"""
<tr>
<td style="width:50%;text-align:center;vertical-align:middle;">{item_name}</td>
<td style="width:50%;text-align:center;vertical-align:middle;">{price}</td>
</tr>"""

    menu_section = ""
    if menu_rows:
        menu_section = f"""
<h2>ロケットナウで頼める{chain_name}のメニュー</h2>
<table style="border-collapse:collapse;width:100%;">
<tbody>
<tr>
<th style="width:50%;background-color:#4a4a4a;text-align:center;"><span style="color:#ffffff;">メニュー</span></th>
<th style="width:50%;background-color:#4a4a4a;text-align:center;"><span style="color:#ffffff;">価格（税込）</span></th>
</tr>
{menu_rows}
</tbody>
</table>"""

    html = f"""<span class="hutoaka">ロケットナウ</span>で<span class="st-mymarker-s">{title_name}</span>に配達対応しています。
アプリから注文すると、最短30分程度で届けてもらえます。

<h2>{title_name}の店舗情報</h2>
<table style="border-collapse:collapse;width:100%;">
<tbody>
<tr>
<td style="width:50%;text-align:center;vertical-align:middle;background-color:#4a4a4a;"><strong><span style="color:#ffffff;">店舗名</span></strong></td>
<td style="width:50%;text-align:center;vertical-align:middle;">{store.get("name", "")}</td>
</tr>
<tr>
<td style="width:50%;text-align:center;vertical-align:middle;background-color:#4a4a4a;"><strong><span style="color:#ffffff;">住所</span></strong></td>
<td style="width:50%;text-align:center;vertical-align:middle;">{store.get("address", "")}</td>
</tr>
<tr>
<td style="width:50%;text-align:center;vertical-align:middle;background-color:#4a4a4a;"><strong><span style="color:#ffffff;">電話番号</span></strong></td>
<td style="width:50%;text-align:center;vertical-align:middle;">{format_phone(store.get("phone", ""))}</td>
</tr>
<tr>
<td style="width:50%;text-align:center;vertical-align:middle;background-color:#4a4a4a;"><strong><span style="color:#ffffff;">営業時間</span></strong></td>
<td style="width:50%;text-align:center;vertical-align:middle;">{hours_html}</td>
</tr>
<tr>
<td style="width:50%;text-align:center;vertical-align:middle;background-color:#4a4a4a;"><strong><span style="color:#ffffff;">ジャンル</span></strong></td>
<td style="width:50%;text-align:center;vertical-align:middle;">{menu_info["genre"]}</td>
</tr>
</tbody>
</table>

{maps_embed}
{menu_section}

ロケットナウのアプリをダウンロードして、配達先住所を入力すると注文できます。

初回注文時は<span class="st-mymarker-s">最大4,000円OFFクーポン</span>利用可能。

詳細は以下よりアプリダウンロード
"""
    return html.strip()


def load_stores(input_path: str) -> list[dict]:
    with open(input_path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_post_csv(rows: list[dict], output_path: str):
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    fieldnames = ["title", "content", "status", "category", "tags", "slug"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"保存完了: {output_path} ({len(rows)} 件)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="csv/rocketnow_stores.csv")
    parser.add_argument("--output", default="csv/rocketnow_post.csv")
    parser.add_argument("--status", default="draft", choices=["draft", "publish"])
    parser.add_argument("--category", default="ロケットナウ")
    parser.add_argument("--limit", type=int, default=0, help="生成する記事数の上限（0=無制限）")
    args = parser.parse_args()

    stores = load_stores(args.input)
    if args.limit > 0:
        stores = stores[:args.limit]
        print(f"{len(stores)} 件に絞って記事を生成します（--limit {args.limit}）")
    else:
        print(f"{len(stores)} 件の店舗データを読み込みました")

    rows = []
    for store in stores:
        chain = store.get("chain", "")
        name = store.get("name", "")
        if not name:
            continue

        title = make_title(name)
        content = build_html(store, chain)
        slug = make_slug(name, chain, store.get("place_id", ""))
        tags = f"{chain},ロケットナウ,デリバリー,フードデリバリー"

        rows.append({
            "title": title,
            "content": content,
            "status": args.status,
            "category": args.category,
            "tags": tags,
            "slug": slug,
        })
        print(f"  生成: {title} → slug: {slug}")

    save_post_csv(rows, args.output)


if __name__ == "__main__":
    main()
