#!/usr/bin/env python3
"""
バリューコマースCSV → WordPress投稿用CSV 変換スクリプト

使い方:
  # 変換（出力: csv/vc_posts.csv）
  python convert_vc_csv.py /tmp/vc_data.csv

  # 出力先を指定
  python convert_vc_csv.py /tmp/vc_data.csv -o csv/vc_posts.csv

  # そのまま投稿（下書き）
  python convert_vc_csv.py /tmp/vc_data.csv --post

  # そのまま投稿（ドライラン）
  python convert_vc_csv.py /tmp/vc_data.csv --post --dry-run
"""

import argparse
import collections
import csv
import os
import sys


# --- まとめる/別記事にする広告主の定義 ---
# 別記事にする広告主（それ以外の複数プログラム広告主はまとめる）
SEPARATE_ADVERTISERS = {
    "ABLENET",
    "IIJmio",
    "ふるさと納税「ふるなび」",
    "タウンライフ土地活用",
}


def _asp_comparison_table():
    """5社ASP比較テーブル（バリューコマースのみ◯、他は✕）を返す"""
    TH_STYLE = 'style="width: 50%; background-color: #301ef7;"'
    TD_CENTER = 'style="width: 50%; text-align: center; vertical-align: middle;"'
    IMG_BASE = "https://www.civichat.jp/wp-content/uploads/2026/03"

    asp_list = [
        {
            "name": "A8net",
            "img": f"{IMG_BASE}/a8.png",
            "link": "https://px.a8.net/svt/ejp?a8mat=3BG026+FXXVXU+0K+10A5LT",
            "display_url": "https://www.a8.net/",
            "mark": '<span style="font-size: 7em;">✕</span>',
            "img_rel": "nofollow noopener",
        },
        {
            "name": "バリューコマース",
            "img": f"{IMG_BASE}/vc.png",
            "link": "//ck.jp.ap.valuecommerce.com/servlet/referral?sid=3548721&amp;amp;pid=892566121",
            "text_link": "//ck.jp.ap.valuecommerce.com/servlet/referral?sid=3548721&amp;pid=892566121",
            "display_url": "https://www.valuecommerce.ne.jp/",
            "mark": '<span class="hutoaka"><span style="font-size: 7em;">◯</span></span>',
            "beacon": '<img src="//ad.jp.ap.valuecommerce.com/servlet/gifbanner?sid=3548721&amp;pid=892566121" width="1" height="1" border="0" />',
        },
        {
            "name": "アクセストレード",
            "img": f"{IMG_BASE}/acces.png",
            "link": "https://h.accesstrade.net/sp/cc?rk=0100nldw00kolw",
            "display_url": "https://www.accesstrade.ne.jp/",
            "mark": '<span style="font-size: 7em;">✕</span>',
        },
        {
            "name": "afb",
            "img": f"{IMG_BASE}/afb.png",
            "link": "https://www.afi-b.com/",
            "display_url": "https://www.afi-b.com/",
            "mark": '<span style="font-size: 7em;">✕</span>',
        },
        {
            "name": "もしもアフィリエイト",
            "img": f"{IMG_BASE}/moshimo.png",
            "link": "//af.moshimo.com/af/c/click?a_id=4207547&amp;p_id=1&amp;pc_id=1&amp;pl_id=82635",
            "display_url": "https://af.moshimo.com/",
            "mark": '<span style="font-size: 7em;">✕</span>',
        },
    ]

    rows_html = []
    for asp in asp_list:
        beacon = asp.get("beacon", "")
        img_rel = asp.get("img_rel", "nofollow")
        text_link = asp.get("text_link", asp["link"])
        rows_html.append(
            f'<tr>\n'
            f'<td {TD_CENTER}>'
            f'<a href="{asp["link"]}" rel="{img_rel}">'
            f'<img class="alignnone size-full" src="{asp["img"]}" alt="{asp["name"]}" width="500" height="200" /></a>\n'
            f'<a href="{text_link}" rel="nofollow">{beacon}{asp["display_url"]}</a></td>\n'
            f'<td {TD_CENTER}>{asp["mark"]}</td>\n'
            f'</tr>'
        )

    return (
        f'<table style="border-collapse: collapse; width: 100%;">\n'
        f'<tbody>\n'
        f'<tr>\n<th {TH_STYLE}></th>\n'
        f'<th {TH_STYLE}><strong><span style="color: #ffffff;">広告掲載状況</span></strong></th>\n</tr>\n'
        + "\n".join(rows_html)
        + "\n</tbody>\n</table>"
    )


def _vc_detail_section():
    """バリューコマースの詳細紹介セクション（静的）を返す"""
    IMG_BASE = "https://www.civichat.jp/wp-content/uploads/2026/03"
    TH_STYLE = 'style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"'
    TD_STYLE = 'style="width: 50%; text-align: center; vertical-align: middle;"'

    vc_info = [
        ("サービス開始年", "1999年（日本初のASP）"),
        ("運営会社", "バリューコマース株式会社（LINEヤフーグループ）"),
        ("サイト審査", "あり（記事数目安：7〜10記事程度）"),
        ("SNS・サイトなしで登録", "✕（サイト必要）"),
        ("初心者向けサポート", "◯"),
        ("案件総数", "大規模（累計広告主6,500社以上）"),
        ("得意ジャンル", "Yahoo!ショッピング・大手EC・金融・旅行"),
        ("Amazon・楽天案件", "〇"),
        ("独自案件の豊富さ", "◎（大手企業の独占案件多数）"),
        ("最低支払額", "500円"),
        ("振込手数料", "無料"),
        ("特別報酬制度", "会員ランク制度（ゴールド・シルバー・ブロンズ・一般）"),
        ("高単価案件", "〇"),
        ("管理画面の使いやすさ", "◎"),
        ("専任担当者", "〇"),
        ("薬機法チェック機能", "×"),
        ("おまかせ広告機能", "◎（コンテンツに合わせ自動で最適広告を配信）"),
        ("会員数", "85万サイト以上登録"),
        ("満足度実績", "日本最古のASPとしての老舗ブランド力"),
    ]

    table_rows = "\n".join(
        f'<tr>\n<th {TH_STYLE}><span style="color: #ffffff;">{label}</span></th>\n'
        f'<td {TD_STYLE}>{value}</td>\n</tr>'
        for label, value in vc_info
    )

    return (
        f'<h3>バリューコマース</h3>\n'
        f'<img class="alignnone size-full" src="{IMG_BASE}/スクリーンショット-2026-03-15-182118.png" '
        f'alt="バリューコマース" width="951" height="535" />\n'
        f'<table style="border-collapse: collapse; width: 100%;">\n<tbody>\n'
        f'{table_rows}\n'
        f'</tbody>\n</table>\n'
        f'[st-minihukidashi webicon="" fontsize="" fontweight="" bgcolor="#FFB74D" color="#fff" '
        f'margin="0 0 20px 0" radius="" position="" myclass="" add_boxstyle=""]おすすめな人\n'
        f'<div class="st-square-checkbox st-square-checkbox-nobox">\n'
        f'<ul>\n'
        f' \t<li>Yahoo!ショッピングのアフィリエイトを扱いたい人</li>\n'
        f' \t<li>大手企業・有名ブランドの信頼性の高い案件を紹介したい人</li>\n'
        f' \t<li>広告の貼り替えの手間を省いて効率よく運用したい人</li>\n'
        f'</ul>\n'
        f'</div>\n'
        f'[/st-minihukidashi]\n'
        f'日本初のASPとして1999年に誕生した、<span class="hutoaka">信頼と実績のあるサービス</span>です。\n\n'
        f'Yahoo!ショッピングのアフィリエイトを扱えるのはバリューコマースだけ。\n\n'
        f'大手企業・有名ECサイトの案件が充実しているので、「信頼できるブランドの商品を紹介したい」という方に特に向いています。\n\n'
        f'コンテンツに合わせて広告を自動表示してくれる<span class="st-mymarker-s">「おまかせ広告」機能も便利</span>です。\n\n'
        f'また、会員ランク制度があり、成果を積み上げるほど特典や報酬条件が有利になっていく仕組みも魅力のひとつです。'
    )


def _vc_cta_button():
    """バリューコマースCTAボタン（静的）を返す"""
    return '[st_af id="2784"]'


def _g(row, key):
    """CSVフィールドを安全に取得（None対策）"""
    v = row.get(key, "")
    return v.strip() if v else ""


def _build_affiliate_info_table(row):
    """案件のアフィリエイト情報テーブル1行分を生成"""
    TD_TH = 'style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"'
    TD_STYLE = 'style="width: 50%; text-align: center; vertical-align: middle;"'

    program_name = _g(row, "プログラム名")
    company_name = _g(row, "会社名")
    advertiser_name = _g(row, "広告主名")
    site_url = _g(row, "広告主サイトURL")
    condition = _g(row, "注文発生対象・条件")
    approval = _g(row, "成果の承認基準")

    cpc = _g(row, "CPC報酬")
    fixed_reward = _g(row, "定額報酬")
    rate_reward = _g(row, "定率報酬")
    reward_text = _format_reward(cpc, fixed_reward, rate_reward)

    site_link = (
        f'<a href="{site_url}" target="_blank" rel="noopener">{advertiser_name or site_url}</a>'
        if site_url else "-"
    )

    info_items = [
        ("案件名", program_name or "-"),
        ("運営会社", company_name or "-"),
        ("公式サイト", site_link),
        ("ジャンル", row.get("ai_genre", "物販")),
        ("報酬単価", reward_text),
        ("成果条件", condition or "-"),
        ("確定率", "不明"),
        ("CVR", "不明"),
        ("EPC", "不明"),
        ("承認基準", approval or "-"),
    ]

    rows_html = "\n".join(
        f'<tr>\n<td {TD_TH}><strong><span style="color: #ffffff;">{label}</span></strong></td>\n'
        f'<td {TD_STYLE}>{value}</td>\n</tr>'
        for label, value in info_items
    )

    return (
        f'<table style="border-collapse: collapse; width: 100%;">\n'
        f'<tbody>\n{rows_html}\n</tbody>\n</table>'
    )


def _add_line_breaks(text):
    """句読点（。）の後に空行を挿入"""
    import re
    return re.sub(r'。', '。\n\n', text)


def _build_program_description(row):
    """案件の紹介文を生成（AI生成があればそちらを優先）"""
    ai_desc = _g(row, "ai_description")
    if ai_desc:
        return _add_line_breaks(ai_desc)
    program_content = _g(row, "プログラム内容")
    if not program_content:
        return ""
    return _add_line_breaks(program_content)


def build_article_html(rows):
    """案件データ（1件 or 複数件）からHTML記事本文を生成"""
    sections = []

    if len(rows) == 1:
        row = rows[0]
        program_name = _g(rows[0], "プログラム名")
    else:
        program_name = _g(rows[0], "広告主名")

    # 1) 冒頭文 + ASP5社比較テーブル
    sections.append(
        f'{program_name}は<span class="st-mymarker-s">バリューコマース</span>でアフィリエイトできます。\n'
        + _asp_comparison_table()
    )

    # 2) H2: アフィリエイトできるASP → H3: バリューコマース詳細 + CTA
    sections.append(
        f'<h2>{program_name}をアフィリエイトできるASP</h2>\n'
        + _vc_detail_section() + "\n"
        + _vc_cta_button()
    )

    # 3) H2: アフィリエイト情報テーブル + 紹介文 + CTA
    if len(rows) == 1:
        row = rows[0]
        sections.append(
            f'<h2>{program_name}のアフィリエイト情報</h2>\n'
            + _build_affiliate_info_table(row) + "\n"
            + _build_program_description(row) + "\n"
            + _vc_cta_button()
        )
    else:
        # 複数プログラムをまとめる場合
        parts = [f'<h2>{program_name}のアフィリエイト情報</h2>']
        for row in rows:
            pname = _g(row, "プログラム名")
            parts.append(f'<h3>{pname}</h3>')
            parts.append(_build_affiliate_info_table(row))
            desc = _build_program_description(row)
            if desc:
                parts.append(desc)
        parts.append(_vc_cta_button())
        sections.append("\n".join(parts))

    return "\n\n".join(sections)


def _format_reward(cpc, fixed, rate):
    """報酬情報を1行テキストにまとめる"""
    parts = []
    if fixed:
        parts.append(fixed)
    if rate:
        parts.append(rate)
    if cpc:
        parts.append(f"CPC: {cpc}")
    return " / ".join(parts) if parts else "-"


def build_title(rows):
    """記事タイトルを生成"""
    if len(rows) == 1:
        program_name = _g(rows[0], "プログラム名")
        return f"{program_name}のアフィリエイトはどこのASP？"
    else:
        advertiser_name = _g(rows[0], "広告主名")
        return f"{advertiser_name}のアフィリエイトはどこのASP？"


def build_tags(rows):
    """タグを生成"""
    tags = set()
    for row in rows:
        if _g(row, "CPC報酬"):
            tags.add("CPC")
        if _g(row, "定額報酬"):
            tags.add("定額報酬")
        if _g(row, "定率報酬"):
            tags.add("定率報酬")
    return ",".join(sorted(tags))


def group_programs(rows):
    """広告主ごとにグループ化し、まとめ/別記事のルールを適用して記事単位のリストを返す"""
    # 広告主名でグループ化（出現順を保持）
    advertiser_groups = collections.OrderedDict()
    for row in rows:
        adv = _g(row, "広告主名")
        if adv not in advertiser_groups:
            advertiser_groups[adv] = []
        # 重複プログラム名を除外
        prog = _g(row, "プログラム名")
        existing_progs = [_g(r, "プログラム名") for r in advertiser_groups[adv]]
        if prog not in existing_progs:
            advertiser_groups[adv].append(row)

    # 記事単位に分割
    article_groups = []
    for adv_name, programs in advertiser_groups.items():
        if len(programs) == 1:
            # 単一プログラム → そのまま1記事
            article_groups.append(programs)
        elif adv_name in SEPARATE_ADVERTISERS:
            # 別記事にする → プログラムごとに1記事
            for prog in programs:
                article_groups.append([prog])
        else:
            # まとめる → 全プログラムで1記事
            article_groups.append(programs)

    return article_groups


def convert_vc_csv(input_path, output_path, use_ai=False):
    """バリューコマースCSVをWordPress投稿用CSVに変換"""
    with open(input_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"入力: {len(rows)} 件の案件を読み込みました")

    # AI処理（ジャンル判定 + 紹介文生成）
    if use_ai:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("警告: ANTHROPIC_API_KEY が未設定のためAI処理をスキップします", file=sys.stderr)
        else:
            from ai_generator import process_rows
            print("Claude API でジャンル判定・紹介文生成を実行します...")
            rows = process_rows(rows)

    # グループ化
    article_groups = group_programs(rows)
    print(f"記事数: {len(article_groups)} 件")

    output_rows = []
    for group in article_groups:
        title = build_title(group)
        content = build_article_html(group)

        output_rows.append({
            "title": title,
            "content": content,
            "status": "draft",
            "category": "",
            "tags": "",
        })

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "content", "status", "category", "tags"])
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"出力: {output_path} に {len(output_rows)} 件書き出しました")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="バリューコマースCSV → WordPress投稿用CSV変換")
    parser.add_argument("input_csv", help="バリューコマースからエクスポートしたCSVファイル")
    parser.add_argument("-o", "--output", default=None, help="出力先CSVパス（デフォルト: csv/vc_posts.csv）")
    parser.add_argument("--post", action="store_true", help="変換後にそのまま投稿する")
    parser.add_argument("--dry-run", action="store_true", help="投稿のドライラン")
    parser.add_argument("--status", default="draft", choices=["draft", "publish"])
    parser.add_argument("--ai", action="store_true",
                        help="Claude APIでジャンル判定・紹介文を自動生成する")

    args = parser.parse_args()

    output_path = args.output or "csv/vc_posts.csv"
    result_path = convert_vc_csv(args.input_csv, output_path, use_ai=args.ai)

    if args.post:
        from wp_bulk_post import bulk_post_from_csv
        bulk_post_from_csv(result_path, args.status, delay=2, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
