#!/usr/bin/env python3
"""
シェア畑スクレイピングCSV → WordPress投稿用CSV (csv/post.csv) へ変換

エリア（既定: 都道府県）単位で農園をまとめ、1記事1エリアの形式で
投稿用CSVを生成する。

使い方:
  # 都道府県単位で記事化（標準）
  python convert_sharebatake_csv.py

  # 市区町村単位
  python convert_sharebatake_csv.py --area-level city

  # 入出力指定
  python convert_sharebatake_csv.py --input csv/sharebatake_raw.csv --output csv/post.csv

  # 既存の post.csv を上書きせず追記（デフォルトは上書き）
  python convert_sharebatake_csv.py --append
"""

import argparse
import csv
import html
import re
from collections import defaultdict
from pathlib import Path

# 都道府県名 → ローマ字スラッグ（最低限の主要県のみ。未定義は romaji 化されず prefecture コードに fallback）
PREF_SLUG = {
    "北海道": "hokkaido", "青森県": "aomori", "岩手県": "iwate", "宮城県": "miyagi",
    "秋田県": "akita", "山形県": "yamagata", "福島県": "fukushima",
    "茨城県": "ibaraki", "栃木県": "tochigi", "群馬県": "gunma", "埼玉県": "saitama",
    "千葉県": "chiba", "東京都": "tokyo", "神奈川県": "kanagawa",
    "新潟県": "niigata", "富山県": "toyama", "石川県": "ishikawa", "福井県": "fukui",
    "山梨県": "yamanashi", "長野県": "nagano", "岐阜県": "gifu", "静岡県": "shizuoka",
    "愛知県": "aichi", "三重県": "mie",
    "滋賀県": "shiga", "京都府": "kyoto", "大阪府": "osaka", "兵庫県": "hyogo",
    "奈良県": "nara", "和歌山県": "wakayama",
    "鳥取県": "tottori", "島根県": "shimane", "岡山県": "okayama", "広島県": "hiroshima",
    "山口県": "yamaguchi",
    "徳島県": "tokushima", "香川県": "kagawa", "愛媛県": "ehime", "高知県": "kochi",
    "福岡県": "fukuoka", "佐賀県": "saga", "長崎県": "nagasaki", "熊本県": "kumamoto",
    "大分県": "oita", "宮崎県": "miyazaki", "鹿児島県": "kagoshima", "沖縄県": "okinawa",
}


def esc(s: str) -> str:
    """HTML属性・本文エスケープ。空入力は空のまま。"""
    if not s:
        return ""
    return html.escape(s, quote=True)


def slugify_area(area_label: str, level: str) -> str:
    """エリア名から英小文字スラッグを生成。"""
    if level == "prefecture":
        return f"sharebatake-{PREF_SLUG.get(area_label, 'area')}"
    # city レベルは prefecture+city が混ざるので簡易ハッシュにする
    safe = re.sub(r"[^a-z0-9-]", "", area_label.lower())
    return f"sharebatake-{safe or 'area'}"


def render_intro(area_label: str, count: int) -> str:
    return (
        f"{esc(area_label)}にあるシェア畑（手ぶらで通える貸し農園）"
        f"<span class=\"st-mymarker-s\">{count}農園</span>の料金・アクセス・特徴を"
        f"一覧でまとめました。"
        f"\n\n"
        f"シェア畑は、農具・種苗・肥料がすべてそろっていて、菜園アドバイザーのサポートを"
        f"受けながら無農薬野菜を育てられる貸し農園サービスです。"
        f"\n\n"
        f"はじめての家庭菜園でも、{esc(area_label)}内の通いやすい農園を選んで、"
        f"気軽にスタートできます。"
    )


def render_summary_table(rows):
    """エリア内農園の比較テーブル。"""
    parts = [
        '<h2>農園一覧（比較表）</h2>',
        '<table style="border-collapse: collapse; width: 100%;">',
        '<tbody>',
        '<tr>'
        '<th style="background-color: #4a4a4a;"><span style="color: #ffffff;">農園名</span></th>'
        '<th style="background-color: #4a4a4a;"><span style="color: #ffffff;">所在地</span></th>'
        '<th style="background-color: #4a4a4a;"><span style="color: #ffffff;">利用料金</span></th>'
        '<th style="background-color: #4a4a4a;"><span style="color: #ffffff;">アクセス</span></th>'
        '</tr>',
    ]
    for r in rows:
        parts.append(
            "<tr>"
            f"<td style=\"vertical-align: middle;\">{esc(r['name'])}</td>"
            f"<td style=\"vertical-align: middle;\">{esc(r.get('address') or '')}</td>"
            f"<td style=\"vertical-align: middle;\">{esc(r.get('fee') or '不明')}</td>"
            f"<td style=\"vertical-align: middle;\">{esc(r.get('access') or '不明')}</td>"
            "</tr>"
        )
    parts.append('</tbody></table>')
    return "\n".join(parts)


def render_farm_block(r):
    """1農園分の見出し＋詳細テーブル。"""
    name = esc(r["name"])
    rows = [
        ("所在地", r.get("address")),
        ("最寄駅・アクセス", r.get("access")),
        ("利用料金", r.get("fee")),
        ("区画サイズ", r.get("area_size")),
        ("設備・サポート", r.get("facilities")),
        ("特徴", r.get("features")),
    ]
    body = [f"<h3>{name}</h3>"]
    body.append('<table style="border-collapse: collapse; width: 100%;">')
    body.append("<tbody>")
    for label, value in rows:
        body.append(
            "<tr>"
            f"<th style=\"width: 30%; text-align: center; vertical-align: middle; background-color: #4a4a4a;\">"
            f"<span style=\"color: #ffffff;\">{label}</span></th>"
            f"<td style=\"vertical-align: middle;\">{esc(value or '不明')}</td>"
            "</tr>"
        )
    body.append("</tbody></table>")
    if r.get("url"):
        body.append(
            f'<p>農園詳細: <a href="{esc(r["url"])}" target="_blank" rel="noopener">'
            f'シェア畑公式ページを見る</a></p>'
        )
    return "\n".join(body)


def render_outro(area_label: str) -> str:
    return (
        "<h2>シェア畑のメリット</h2>\n"
        "<ul>\n"
        "<li>農具・種苗・肥料・水道などが全てそろっていて、手ぶらで通える</li>\n"
        "<li>菜園アドバイザーが定期的に巡回し、初心者でも栽培方法を相談できる</li>\n"
        "<li>無農薬・有機栽培で、安心して食べられる野菜を収穫できる</li>\n"
        "<li>イベント（収穫祭など）で他の利用者と交流できる</li>\n"
        "</ul>\n"
        "\n"
        "<h2>申し込みの流れ</h2>\n"
        "<ol>\n"
        "<li>気になる農園を選んで、見学・説明会に申し込む</li>\n"
        "<li>料金プラン・区画サイズを決めて契約</li>\n"
        "<li>初日にスタッフから使い方の説明を受け、栽培スタート</li>\n"
        "</ol>\n"
        "\n"
        f'<p>{esc(area_label)}でシェア畑を始めたい方は、'
        '<span class="hutoaka">気になる農園の見学申し込み</span>から検討してみてください。</p>'
    )


def build_article(area_label: str, level: str, rows):
    """1エリア分の記事 (title, content, slug, tags) を返す。"""
    rows = sorted(rows, key=lambda r: (r.get("city", ""), r["name"]))
    title = f"{area_label}のシェア畑一覧｜料金・アクセス・特徴まとめ"
    content_parts = [
        render_intro(area_label, len(rows)),
        "",
        render_summary_table(rows),
        "",
        f"<h2>{esc(area_label)}のシェア畑 各農園の詳細</h2>",
    ]
    for r in rows:
        content_parts.append("")
        content_parts.append(render_farm_block(r))
    content_parts.append("")
    content_parts.append(render_outro(area_label))

    tags = ["シェア畑", "貸し農園", area_label]
    return {
        "title": title,
        "content": "\n".join(content_parts),
        "status": "",  # ワークフロー側のデフォルトに任せる
        "category": "貸し農園",
        "tags": ",".join(tags),
        "slug": slugify_area(area_label, level),
    }


def group_rows(rows, level):
    groups = defaultdict(list)
    for r in rows:
        if level == "city":
            key = (r.get("prefecture", "") + r.get("city", "")).strip()
        else:
            key = r.get("prefecture", "").strip()
        if not key:
            key = "エリア不明"
        groups[key].append(r)
    return groups


def main():
    parser = argparse.ArgumentParser(description="シェア畑スクレイピング結果 → 投稿CSV")
    parser.add_argument("--input", default="csv/sharebatake_raw.csv")
    parser.add_argument("--output", default="csv/post.csv")
    parser.add_argument(
        "--area-level", choices=["prefecture", "city"], default="prefecture",
        help="エリアの粒度（既定: prefecture）",
    )
    parser.add_argument("--append", action="store_true", help="既存出力に追記")
    parser.add_argument("--min-farms", type=int, default=1, help="エリアあたり最低農園数（未満は除外）")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.exists():
        raise SystemExit(f"入力CSVが見つかりません: {in_path}")

    with open(in_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"入力: {len(rows)} 農園")

    groups = group_rows(rows, args.area_level)
    print(f"エリア数: {len(groups)} (粒度: {args.area_level})")

    articles = []
    for area, items in sorted(groups.items()):
        if len(items) < args.min_farms:
            continue
        articles.append(build_article(area, args.area_level, items))
    print(f"生成記事数: {len(articles)}")

    fields = ["title", "content", "status", "category", "tags", "slug"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.append and out_path.exists() else "w"
    write_header = not (args.append and out_path.exists())
    with open(out_path, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            writer.writeheader()
        for a in articles:
            writer.writerow(a)
    print(f"書き出し: {out_path}")


if __name__ == "__main__":
    main()
