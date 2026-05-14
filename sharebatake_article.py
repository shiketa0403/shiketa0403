#!/usr/bin/env python3
"""
シェア畑データベース記事 生成・投稿スクリプト

フロー:
  1. 区/市名から sharebatake_scraper でデータ収集 + 各農園詳細ページのフルスクショ取得
  2. screenshot.upload_to_wordpress で WP メディアに画像アップロード
  3. sharebatake_ai で農園説明文・自治体情報を Claude API 生成
  4. テンプレートに埋め込んで HTML 組み立て
  5. wp_post.create_post で agriwarriors.jp に draft 投稿

呼び出し例:
  python sharebatake_article.py 大田区 --status draft

事前条件:
  - wp_config.py が agriwarriors.jp の認証情報で生成されていること
  - 環境変数 ANTHROPIC_API_KEY が設定されていること
  - WP 側に「東京」カテゴリ（slug: tokyo）が存在すること
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from typing import List, Optional

from sharebatake_scraper import Farm, scrape_area, TOKYO_AREA_MAP, lookup_area

A8_HREF = "https://px.a8.net/svt/ejp?a8mat=3ZFJ8K+ABII9E+3U16+60H7M"
HUB_URL = "https://agriwarriors.jp/shared-farm/"
HUB_ANCHOR = "シェア畑の口コミ・評判は本当?契約NGの人を200人調査で暴露"
CATEGORY_NAME = "東京"


def esc(s: Optional[str]) -> str:
    return html.escape(s or "", quote=True)


def _split_by_marker(text: str, marker: str) -> List[str]:
    """marker を区切り文字として、marker を残したまま分割し、空要素は除外。"""
    pieces = re.split(f"({re.escape(marker)})", text)
    out: List[str] = []
    current = ""
    for piece in pieces:
        if piece == marker:
            if current.strip():
                out.append(current.strip())
            current = marker
        else:
            current += piece
    if current.strip():
        out.append(current.strip())
    return out


def format_address(text: str) -> str:
    """住所を ※ ごとに <br> 改行（※は残す）。"""
    if not text:
        return ""
    parts = _split_by_marker(text, "※")
    return "<br>".join(esc(p) for p in parts) if parts else esc(text)


def format_fee(text: str) -> str:
    """利用料金を ※ ごとに <br> 改行（※は残す）。"""
    return format_address(text)


def format_access(text: str) -> str:
    """最寄駅・アクセスを整形。
    - 最初の ※ 以降は捨てる（Google Map 操作ヘルプ等の混入を除去）
    - 「駅からのアクセス」「バスでのアクセス」「お車でのアクセス」見出しと
      【駅名】ブロックの直前で改行
    """
    if not text:
        return ""
    cut = text.split("※", 1)[0].strip()
    # 連続空白を1つに正規化
    cut = re.sub(r"\s+", " ", cut)
    # 移動手段見出しの直前に改行（先頭でなければ）
    cut = re.sub(
        r"(?<!^)\s*(駅からのアクセス|バスでのアクセス|お車でのアクセス)",
        r"\n\1",
        cut,
    )
    # 【駅名】の直前に改行
    cut = re.sub(r"\s*(【[^】]+】)", r"\n\1", cut)
    cut = re.sub(r"\n+", "\n", cut)
    lines = [esc(l.strip()) for l in cut.split("\n") if l.strip()]
    return "<br>".join(lines)


def format_description_paragraphs(text: str) -> str:
    """AI 説明文を「。」ごとに段落（空行）で区切る。
    WordPress の wpautop が空行を <p> に変換するので、<br> や <p> は使わない。
    """
    if not text:
        return ""
    # AI が誤って付与した <p>/<br> を剥がす（wpautop に任せる）
    text = re.sub(r"</?p[^>]*>", "", text)
    text = re.sub(r"<br\s*/?>", "", text, flags=re.IGNORECASE)
    text = text.strip()
    if not text:
        return ""
    sentences = re.split(r"(。)", text)
    paragraphs: List[str] = []
    buf = ""
    for piece in sentences:
        if piece == "。":
            buf += "。"
            if buf.strip():
                paragraphs.append(buf.strip())
            buf = ""
        else:
            buf += piece
    if buf.strip():
        paragraphs.append(buf.strip())
    return "\n\n".join(p for p in paragraphs if p)


def render_status_tags(tags: List[str]) -> str:
    if not tags:
        return "-"
    return " / ".join(esc(t) for t in tags)


def render_map_iframe(farm: Farm) -> str:
    if farm.lat is None or farm.lng is None:
        return ""
    src = (
        f"https://maps.google.com/maps?q={farm.lat},{farm.lng}"
        f"&z=15&output=embed"
    )
    return (
        f'<iframe src="{src}" width="100%" height="320" '
        'style="border:0;" loading="lazy" referrerpolicy="no-referrer-when-downgrade" '
        'allowfullscreen></iframe>'
    )


def render_farm_table(farm: Farm) -> str:
    """2カラムテーブル（左=ラベル、右=値）"""
    # 各値の整形（HTML エスケープ済み or 完全な HTML 断片）
    cells = {
        "農園タイプ": esc("シェア畑 garden" if farm.is_garden else "シェア畑"),
        "住所": format_address(farm.address),
        "最寄駅・アクセス": format_access(farm.access),
        "利用料金（月額・税込）": format_fee(farm.fee),
        "入会金": esc(farm.entry_fee),
        "料金に含まれるもの": esc(farm.included_services),
        "施設・設備": esc(farm.facilities),
        "特徴タグ": render_status_tags(farm.status_tags),
    }
    label_order = list(cells.keys())
    map_html = render_map_iframe(farm)
    parts = ['<table style="border-collapse: collapse; width: 100%;">', "<tbody>"]
    for label in label_order:
        v = cells[label]
        parts.append(
            "<tr>"
            f'<th style="width: 30%; text-align: center; vertical-align: middle; '
            f'background-color: #4a4a4a;">'
            f'<span style="color: #ffffff;">{esc(label)}</span></th>'
            f'<td style="vertical-align: middle;">{v or "-"}</td>'
            "</tr>"
        )
    if map_html:
        parts.append(
            '<tr>'
            '<th style="width: 30%; text-align: center; vertical-align: middle; '
            'background-color: #4a4a4a;">'
            '<span style="color: #ffffff;">地図</span></th>'
            f'<td style="vertical-align: middle;">{map_html}</td>'
            '</tr>'
        )
    parts.append("</tbody></table>")
    return "\n".join(parts)


def render_farm_block(farm: Farm, description_html: str) -> str:
    """1農園分の H3 + 画像 + テーブル + 説明 + CTA"""
    parts = [f"<h3>{esc(farm.name)}</h3>"]
    if farm.screenshot_wp_url:
        parts.append(
            f'<img src="{esc(farm.screenshot_wp_url)}" '
            f'alt="{esc(farm.name)}" loading="lazy" />'
        )
    parts.append(render_farm_table(farm))
    if description_html:
        # 句点ごとに空行を挟む（WP の wpautop で <p> 化される）
        parts.append(format_description_paragraphs(description_html))
    parts.append(
        f'<a href="{A8_HREF}" rel="nofollow noopener">'
        f"{esc(farm.name)}の見学予約・詳細を見る</a>"
    )
    return "\n\n".join(parts)


def render_article(
    city_name: str,
    farms: List[Farm],
    descriptions: List[str],
    gov_info_html: Optional[str],
) -> str:
    """記事本文 HTML を返す。"""
    parts: List[str] = []
    parts.append(f"<h2>{esc(city_name)}でレンタルできる貸し農園一覧</h2>")
    for farm, desc in zip(farms, descriptions):
        parts.append(render_farm_block(farm, desc))

    if gov_info_html:
        parts.append("<h2>自治体などのレンタル畑情報</h2>")
        parts.append(format_description_paragraphs(gov_info_html))
    else:
        parts.append("<h2>自治体などのレンタル情報なし</h2>")

    parts.append(f'<p><a href="{HUB_URL}">{esc(HUB_ANCHOR)}</a></p>')
    return "\n\n".join(parts)


# === WordPress 連携 ===

def ensure_category_id(category_name: str) -> int:
    """カテゴリ名から ID を取得（無ければエラーで終了）"""
    import urllib.parse
    from wp_post import api_request

    cats = api_request(f"categories?search={urllib.parse.quote(category_name)}")
    for c in cats:
        if c["name"] == category_name:
            return c["id"]
    raise SystemExit(
        f"カテゴリ '{category_name}' が agriwarriors.jp に存在しません。"
        "事前に WordPress 側で作成してください。"
    )


def ensure_tag_id(tag_name: str) -> int:
    """タグ名から ID を取得（無ければ作成）"""
    import urllib.parse
    from wp_post import api_request

    tags = api_request(f"tags?search={urllib.parse.quote(tag_name)}")
    for t in tags:
        if t["name"].lower() == tag_name.lower():
            return t["id"]
    result = api_request("tags", "POST", {"name": tag_name})
    return result["id"]


def upload_screenshots(farms: List[Farm]) -> None:
    """各農園のスクショを WP メディアにアップして wp_url を埋める。"""
    from screenshot import upload_to_wordpress

    for farm in farms:
        if not farm.screenshot_path:
            continue
        path = Path(farm.screenshot_path)
        if not path.exists():
            print(f"! スクショ無し: {path}", file=sys.stderr)
            continue
        # 20KB 未満はブロック判定でスキップ
        if path.stat().st_size < 20 * 1024:
            print(f"! スクショサイズ過小（{path.stat().st_size}B）: {path}", file=sys.stderr)
            continue
        print(f"[upload] {farm.name}: {path.name}")
        result = upload_to_wordpress(str(path), title=farm.name)
        if result and "url" in result:
            farm.screenshot_wp_url = result["url"]


# === メイン ===

def main():
    parser = argparse.ArgumentParser(description="シェア畑データベース記事を生成・投稿")
    parser.add_argument("city", help="区/市名（例: 大田区）")
    parser.add_argument("--status", default="draft",
                        choices=["draft", "publish", "pending", "private"])
    parser.add_argument("--out-dir", default="out_sharebatake")
    parser.add_argument("--max-farms", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true",
                        help="WP 投稿せず、本文 HTML を標準出力に書き出す")
    parser.add_argument("--skip-upload", action="store_true",
                        help="スクショの WP メディアアップロードをスキップ（テスト用）")
    args = parser.parse_args()

    # 0. 早期検証: 区/市名がマップに存在するか
    sb_slug, wp_slug, addr_filter = lookup_area(args.city)
    print(f"[main] 対象: {args.city} -> sharebatake={sb_slug}, wp_slug={wp_slug}")

    # 0.5 ドライランでない場合、最初に WP 接続テスト + カテゴリ存在チェック
    if not args.dry_run:
        print("[main] WP 接続テスト + カテゴリ存在チェック…")
        cat_id = ensure_category_id(CATEGORY_NAME)
        print(f"[main] OK: カテゴリ '{CATEGORY_NAME}' ID={cat_id}")

    # 1. スクレイピング
    out_dir = Path(args.out_dir)
    farms = scrape_area(args.city, out_dir=out_dir, max_farms=args.max_farms)
    if not farms:
        raise SystemExit(f"対象農園が0件: {args.city}")
    print(f"[main] 取得 {len(farms)} 農園")

    # 2. スクショアップロード
    if not args.skip_upload and not args.dry_run:
        upload_screenshots(farms)

    # 3. AI 説明文
    from sharebatake_ai import generate_farm_description, generate_local_gov_info

    descriptions: List[str] = []
    for i, farm in enumerate(farms, 1):
        print(f"[main] AI 農園説明 ({i}/{len(farms)}): {farm.name}")
        try:
            desc = generate_farm_description(farm.to_dict())
        except Exception as e:
            print(f"  ! AI失敗 → 空文字: {e}", file=sys.stderr)
            desc = ""
        descriptions.append(desc)

    # 4. 自治体情報
    print(f"[main] AI 自治体情報: {args.city}")
    try:
        gov_info = generate_local_gov_info(args.city)
    except Exception as e:
        print(f"  ! AI失敗 → なし扱い: {e}", file=sys.stderr)
        gov_info = None

    # 5. HTML 組み立て
    title = f"【{args.city}】レンタルできる貸し農園まとめ"
    content = render_article(args.city, farms, descriptions, gov_info)

    if args.dry_run:
        print("\n========== DRY RUN: 投稿せず本文を出力 ==========")
        print(f"title: {title}")
        print(f"slug:  {wp_slug}")
        print(f"tags:  シェア畑, 貸し農園, {args.city}")
        print(f"category: {CATEGORY_NAME}")
        print(f"status: {args.status}")
        print("---- content ----")
        print(content)
        return

    # 6. 投稿
    from wp_post import create_post

    cat_id = ensure_category_id(CATEGORY_NAME)
    tag_ids = [ensure_tag_id(t) for t in ("シェア畑", "貸し農園", args.city)]
    print(f"[main] 投稿実行: status={args.status}, slug={wp_slug}")
    create_post(
        title=title,
        content=content,
        status=args.status,
        category_ids=[cat_id],
        tag_ids=tag_ids,
        slug=wp_slug,
    )


if __name__ == "__main__":
    main()
