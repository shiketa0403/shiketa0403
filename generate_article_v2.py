#!/usr/bin/env python3
"""
新構成の記事生成スクリプト（v2）

記事構成:
  1. 冒頭1文（提携可能ASPを列挙）
  2. ASP◯✕比較テーブル
  3. <h2>ASP一覧</h2> + 各ASPのH3セクション
  4. <h2>案件情報</h2> + スクショ + テーブル + 説明文10文
  5. [st_af id="2784"]

使い方:
  python generate_article_v2.py --name "LINEMO" --search
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

from asp_data import (
    ASP_LIST,
    ASP_ORDER,
    build_asp_comparison_table,
    build_asp_detail_section,
    build_case_info_table,
)


def find_case_in_csv(case_name, csv_path="csv/vc_raw_utf8.csv"):
    """vc_raw_utf8.csv から案件名に一致する行を取得（部分一致）"""
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # 完全一致 → 部分一致 → 広告主名一致 の優先順で検索
    for row in rows:
        program_name = row.get("プログラム名", "")
        if case_name == extract_case_name(program_name):
            return row
    for row in rows:
        program_name = row.get("プログラム名", "")
        advertiser = row.get("広告主名", "")
        if case_name in program_name or case_name in advertiser:
            return row
    for row in rows:
        program_name = row.get("プログラム名", "").lower()
        if case_name.lower() in program_name:
            return row
    return None


def extract_case_name(program_name):
    """プログラム名から案件名を抽出"""
    name = program_name.strip()
    m = re.search(r'【(.+?)】', name)
    if m:
        name = m.group(1)
    else:
        name = re.split(r'[｜|]', name)[0]
    for word in ["キャンペーン", "キャッシュバック", "WEB申込", "お申し込み", "プロモーション", "公式", "プログラム"]:
        name = name.replace(word, "")
    return name.strip().strip("　 ")


def search_asp_status(case_name):
    """
    Google検索風にASP掲載情報を推定する。
    実際はこの関数をClaude（チャット内）で手動実行する想定。
    デフォルトはバリューコマースのみ◯。
    """
    return {
        "a8": False,
        "valuecommerce": True,
        "accesstrade": False,
        "afb": False,
        "moshimo": False,
    }


def get_available_asp_names(asp_status):
    """◯のASP名リストを返す"""
    names = []
    for key in ASP_ORDER:
        if asp_status.get(key, False):
            names.append(ASP_LIST[key]["name"])
    return names


def generate_opening_sentence(case_name, asp_names):
    """冒頭1文を生成"""
    if len(asp_names) == 1:
        highlighted = f'<span class="st-mymarker-s">{asp_names[0]}</span>'
        return f"{case_name}は{highlighted}でアフィリエイトできます。"
    else:
        parts = []
        for i, name in enumerate(asp_names):
            if i == 0:
                parts.append(f'<span class="st-mymarker-s">{name}</span>')
            else:
                parts.append(name)
        joined = "・".join(parts)
        return f"{case_name}は{joined}でアフィリエイトできます。"


def generate_asp_descriptions(case_name, asp_status, case_info):
    """
    各ASPの説明文4文を生成する。
    Claude APIで生成するか、テンプレートで生成する。
    """
    descriptions = {}
    reward = case_info.get("reward", "")
    genre = case_info.get("genre", "")

    for key in ASP_ORDER:
        if not asp_status.get(key, False):
            continue
        asp = ASP_LIST[key]
        asp_name = asp["name"]

        if key == "valuecommerce":
            desc = (
                f"{asp_name}はLINEヤフーグループが運営する日本最古のASPです。\n\n"
                f"{case_name}の案件は{asp_name}で提携申請が可能で、報酬単価は{reward}です。\n\n"
                f"振込手数料が無料のため、発生した報酬を丸ごと受け取れます。\n\n"
                f"大手企業の独占案件が多く、{case_name}もその一つです。"
            )
        elif key == "a8":
            desc = (
                f"{asp_name}は国内最大級のアフィリエイトASPで、サイト審査なしで即日登録できます。\n\n"
                f"{case_name}は{asp_name}でも提携可能で、初心者でもすぐに始められます。\n\n"
                f"案件数が圧倒的に多く、{case_name}と相性の良い関連案件も見つかります。\n\n"
                f"セルフバック対応の案件も豊富なので、実体験レビュー記事を書きやすい環境です。"
            )
        elif key == "accesstrade":
            desc = (
                f"{asp_name}は金融・通信ジャンルに強いASPで、高単価案件が揃っています。\n\n"
                f"{case_name}は{asp_name}でも取り扱いがあり、{genre}ジャンルとの相性が抜群です。\n\n"
                f"振込手数料無料、最低支払額1,000円からと報酬を受け取りやすい条件が整っています。\n\n"
                f"担当者からの特別単価オファーが届くこともあるため、登録しておいて損はありません。"
            )
        elif key == "afb":
            desc = (
                f"{asp_name}は最低支払額777円・振込手数料無料と、業界でもっとも報酬を受け取りやすいASPです。\n\n"
                f"{case_name}は{asp_name}でも提携でき、報酬単価は{reward}です。\n\n"
                f"消費税分を上乗せして支払う「税込み報酬」制度があり、実質的な報酬額が高くなります。\n\n"
                f"管理画面が使いやすく、初心者でも成果確認やレポート分析がスムーズです。"
            )
        elif key == "moshimo":
            desc = (
                f"{asp_name}はW報酬制度で通常報酬に12%のボーナスが加算されるASPです。\n\n"
                f"{case_name}は{asp_name}でも取り扱いがあり、サイト審査なしで登録できます。\n\n"
                f"Amazon・楽天のアフィリエイトも同時に扱えるため、物販記事との組み合わせも可能です。\n\n"
                f"かんたんリンク機能で商品リンクが簡単に作れるので、記事作成の効率が上がります。"
            )
        else:
            desc = ""

        descriptions[key] = desc

    return descriptions


def generate_case_description(case_name, case_info, asp_names):
    """案件説明文（10文前後）を生成"""
    company = case_info.get("company", "")
    reward = case_info.get("reward", "")
    condition = case_info.get("condition", "")
    approval = case_info.get("approval", "")
    program_content = case_info.get("program_content", "")
    site_url = case_info.get("site_url", "")

    asp_text = "・".join(asp_names)

    desc = (
        f"{company}が運営する「{case_name}」の公式サービスです。\n\n"
        f'報酬単価は<span class="st-mymarker-s">{reward}</span>です。\n\n'
        f"成果条件は「{condition}」で、承認基準は「{approval}」です。\n\n"
        f'{case_name}は<span class="hutoaka">{asp_text}</span>で提携できます。\n\n'
    )

    if program_content:
        lines = program_content.replace("\r\n", "\n").split("\n")
        useful_lines = []
        for l in lines:
            l = l.strip()
            if not l or len(l) <= 5:
                continue
            if l.startswith("◆") or l.startswith("※"):
                continue
            if re.match(r'^【.*】\s*$', l):
                continue
            if "http" in l:
                continue
            useful_lines.append(l)
        for line in useful_lines[:3]:
            desc += f"{line}\n\n"

    desc += f"アフィリエイト初心者でも成果を出しやすい案件です。\n\n"
    desc += f"{case_name}は今すぐ提携申請が可能です。"

    return desc


def build_full_article(case_name, case_info, asp_status, asp_descriptions, case_description):
    """記事全体のHTMLを組み立てる"""
    asp_names = get_available_asp_names(asp_status)

    # 1. 冒頭1文
    opening = generate_opening_sentence(case_name, asp_names)

    # 2. ASP◯✕比較テーブル
    comparison_table = build_asp_comparison_table(asp_status)

    # 3. ASP一覧セクション
    asp_sections = []
    for key in ASP_ORDER:
        if asp_status.get(key, False) and key in asp_descriptions:
            section = build_asp_detail_section(key, asp_descriptions[key])
            asp_sections.append(section)

    asp_list_html = f"<h2>{case_name}を扱えるASP一覧</h2>\n" + "\n\n".join(asp_sections)

    # 4. 案件情報セクション
    info_table = build_case_info_table(
        case_name,
        case_info.get("company", ""),
        case_info.get("site_url", ""),
        case_info.get("site_display", ""),
        case_info.get("genre", ""),
        case_info.get("reward", ""),
        case_info.get("condition", ""),
        case_info.get("approval", ""),
    )
    case_section = f"<h2>{case_name}のアフィリエイト情報</h2>\n{info_table}\n{case_description}"

    # 5. 末尾ショートコード
    closing = '[st_af id="2784"]'

    # 結合
    content = f"{opening}\n{comparison_table}\n{asp_list_html}\n\n{case_section}\n\n{closing}"
    return content


def parse_case_info_from_csv_row(row):
    """CSV行から案件情報を抽出"""
    program_name = row.get("プログラム名", "")
    case_name = extract_case_name(program_name)

    fixed_reward = row.get("定額報酬", "").strip()
    rate_reward = row.get("定率報酬", "").strip()
    if fixed_reward:
        reward = f"{fixed_reward}円"
    elif rate_reward:
        reward = f"{rate_reward}%"
    else:
        reward = "要確認"

    condition = row.get("注文発生対象・条件", "").strip()
    approval = row.get("成果の承認基準", "").strip()
    approval_other = row.get("成果の承認基準（その他）", "").strip()
    if approval_other:
        approval = f"{approval}:{approval_other}" if approval else approval_other

    genre = "物販" if rate_reward else "登録"

    return {
        "case_name": case_name,
        "company": row.get("会社名", "").strip(),
        "site_url": row.get("広告主サイトURL", "").strip(),
        "site_display": row.get("広告主名", "").strip(),
        "genre": genre,
        "reward": reward,
        "condition": condition,
        "approval": approval,
        "program_content": row.get("プログラム内容", "").strip(),
    }


def generate_slug(case_name):
    """案件名から英語スラッグを生成（簡易版）"""
    slug = case_name.lower()
    # まず英数字部分だけ抽出を試みる
    ascii_parts = re.findall(r'[a-z0-9]+', slug)
    if ascii_parts:
        return "-".join(ascii_parts)[:50]
    # 全て日本語の場合はハッシュベース
    import hashlib
    return hashlib.md5(case_name.encode()).hexdigest()[:10]


def write_post_csv(title, content, slug, screenshot_url, csv_path="csv/post.csv"):
    """csv/post.csv をリセットして1記事分を書き込む"""
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(["title", "content", "status", "category", "tags", "slug", "screenshot_url"])
        writer.writerow([title, content, "draft", "", "", slug, screenshot_url])
    print(f"csv/post.csv に出力しました: {title}")


def main():
    parser = argparse.ArgumentParser(description="新構成の記事生成（v2）")
    parser.add_argument("--name", required=True, help="案件名")
    parser.add_argument("--csv", default="csv/vc_raw_utf8.csv", help="案件CSVパス")
    parser.add_argument("--asp-status", help='ASP状態JSON (例: {"a8":true,"valuecommerce":true,...})')
    parser.add_argument("--slug", help="スラッグを手動指定")
    parser.add_argument("--output", default="csv/post.csv", help="出力CSVパス")
    parser.add_argument("--dry-run", action="store_true", help="CSV出力せず内容表示のみ")

    args = parser.parse_args()

    # CSV から案件情報を取得
    row = find_case_in_csv(args.name, args.csv)
    if not row:
        print(f"エラー: '{args.name}' が CSV に見つかりません", file=sys.stderr)
        sys.exit(1)

    case_info = parse_case_info_from_csv_row(row)
    # --name で指定された名前を優先して使う（CSVの抽出結果より正確）
    case_name = args.name
    case_info["case_name"] = case_name
    print(f"案件: {case_name}")
    print(f"  会社: {case_info['company']}")
    print(f"  報酬: {case_info['reward']}")

    # ASP状態
    if args.asp_status:
        asp_status = json.loads(args.asp_status)
    else:
        asp_status = search_asp_status(case_name)

    asp_names = get_available_asp_names(asp_status)
    print(f"  提携可能ASP: {', '.join(asp_names)}")

    # ASP説明文生成
    asp_descriptions = generate_asp_descriptions(case_name, asp_status, case_info)

    # 案件説明文生成
    case_description = generate_case_description(case_name, case_info, asp_names)

    # 記事HTML生成
    content = build_full_article(case_name, case_info, asp_status, asp_descriptions, case_description)

    # タイトル・スラッグ
    title = f"{case_name}のアフィリエイトはどこのASP？"
    slug = args.slug if args.slug else generate_slug(case_name)

    if args.dry_run:
        print(f"\n=== タイトル ===\n{title}")
        print(f"\n=== スラッグ ===\n{slug}")
        print(f"\n=== 本文（先頭500文字） ===\n{content[:500]}")
        print(f"\n=== 本文長 ===\n{len(content)} 文字")
    else:
        write_post_csv(title, content, slug, case_info["site_url"], args.output)

    return {
        "title": title,
        "content": content,
        "slug": slug,
        "screenshot_url": case_info["site_url"],
    }


if __name__ == "__main__":
    main()
