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
import sys


# --- まとめる/別記事にする広告主の定義 ---
# 別記事にする広告主（それ以外の複数プログラム広告主はまとめる）
SEPARATE_ADVERTISERS = {
    "ABLENET",
    "IIJmio",
    "ふるさと納税「ふるなび」",
    "タウンライフ土地活用",
}


def build_article_html(rows):
    """案件データ（1件 or 複数件）からHTML記事本文を生成"""
    sections = []
    asp_name = "バリューコマース"

    if len(rows) == 1:
        # 単一プログラム
        row = rows[0]
        program_name = row.get("プログラム名", "").strip()
        program_content = row.get("プログラム内容", "").strip()
        advertiser_name = row.get("広告主名", "").strip()
        company_name = row.get("会社名", "").strip()
        site_url = row.get("広告主サイトURL", "").strip()

        # 報酬情報
        cpc = row.get("CPC報酬", "").strip()
        fixed_reward = row.get("定額報酬", "").strip()
        rate_reward = row.get("定率報酬", "").strip()

        # 成果条件
        condition = row.get("注文発生対象・条件", "").strip()
        approval = row.get("成果の承認基準", "").strip()

        # 対応状況
        smartphone = row.get("スマホ対応", "").strip()
        itp = row.get("ITP対応済", "").strip()
        self_affiliate = row.get("自己アフィリエイト可能", "").strip()

        # プログラム概要
        if program_content:
            content_html = program_content.replace("\n", "<br>")
            sections.append(
                f'<h2>{program_name}とは</h2>\n<p>{content_html}</p>'
            )

        # ASP情報テーブル
        sections.append(
            f'<h2>{program_name}のアフィリエイトがあるASP</h2>\n'
            f'<table>\n<thead><tr><th>ASP</th><th>プログラム名</th><th>報酬</th><th>CVR</th><th>EPC</th></tr></thead>\n'
            f'<tbody>\n'
            f'<tr><td>{asp_name}</td><td>{program_name}</td><td>{_format_reward(cpc, fixed_reward, rate_reward)}</td><td></td><td></td></tr>\n'
            f'</tbody>\n</table>'
        )

        # 報酬・成果条件
        reward_rows = []
        if cpc:
            reward_rows.append(f"<tr><td>CPC報酬</td><td>{cpc}</td></tr>")
        if fixed_reward:
            reward_rows.append(f"<tr><td>定額報酬</td><td>{fixed_reward}</td></tr>")
        if rate_reward:
            reward_rows.append(f"<tr><td>定率報酬</td><td>{rate_reward}</td></tr>")
        if condition:
            reward_rows.append(f"<tr><td>成果条件</td><td>{condition}</td></tr>")
        if approval:
            reward_rows.append(f"<tr><td>承認基準</td><td>{approval}</td></tr>")

        if reward_rows:
            rows_html = "\n".join(reward_rows)
            sections.append(
                f'<h2>報酬・成果条件</h2>\n'
                f'<table>\n<thead><tr><th>項目</th><th>内容</th></tr></thead>\n'
                f'<tbody>\n{rows_html}\n</tbody>\n</table>'
            )

        # 基本情報テーブル
        info_rows = []
        if company_name:
            info_rows.append(f"<tr><td>運営会社</td><td>{company_name}</td></tr>")
        if site_url:
            info_rows.append(
                f'<tr><td>公式サイト</td><td><a href="{site_url}" target="_blank" rel="noopener">'
                f'{advertiser_name or site_url}</a></td></tr>'
            )
        if smartphone:
            info_rows.append(f"<tr><td>スマホ対応</td><td>{smartphone}</td></tr>")
        if itp:
            info_rows.append(f"<tr><td>ITP対応</td><td>{itp}</td></tr>")
        if self_affiliate:
            is_ok = "可能" if self_affiliate in ("可能", "○", "可") else "不可"
            info_rows.append(f"<tr><td>自己アフィリエイト</td><td>{is_ok}</td></tr>")

        if info_rows:
            rows_html = "\n".join(info_rows)
            sections.append(
                f'<h2>基本情報</h2>\n'
                f'<table>\n<thead><tr><th>項目</th><th>内容</th></tr></thead>\n'
                f'<tbody>\n{rows_html}\n</tbody>\n</table>'
            )

    else:
        # 複数プログラムをまとめる場合
        first = rows[0]
        advertiser_name = first.get("広告主名", "").strip()
        company_name = first.get("会社名", "").strip()
        site_url = first.get("広告主サイトURL", "").strip()

        # 概要（最初のプログラムの内容を使用）
        program_content = first.get("プログラム内容", "").strip()
        if program_content:
            content_html = program_content.replace("\n", "<br>")
            sections.append(
                f'<h2>{advertiser_name}とは</h2>\n<p>{content_html}</p>'
            )

        # ASP情報テーブル（全プログラムをまとめて表示）
        asp_rows = []
        for row in rows:
            pname = row.get("プログラム名", "").strip()
            cpc = row.get("CPC報酬", "").strip()
            fixed = row.get("定額報酬", "").strip()
            rate = row.get("定率報酬", "").strip()
            reward = _format_reward(cpc, fixed, rate)
            asp_rows.append(
                f'<tr><td>{asp_name}</td><td>{pname}</td><td>{reward}</td><td></td><td></td></tr>'
            )
        asp_rows_html = "\n".join(asp_rows)
        sections.append(
            f'<h2>{advertiser_name}のアフィリエイトがあるASP</h2>\n'
            f'<table>\n<thead><tr><th>ASP</th><th>プログラム名</th><th>報酬</th><th>CVR</th><th>EPC</th></tr></thead>\n'
            f'<tbody>\n{asp_rows_html}\n</tbody>\n</table>'
        )

        # 各プログラムの報酬・成果条件
        for row in rows:
            pname = row.get("プログラム名", "").strip()
            cpc = row.get("CPC報酬", "").strip()
            fixed = row.get("定額報酬", "").strip()
            rate = row.get("定率報酬", "").strip()
            condition = row.get("注文発生対象・条件", "").strip()
            approval = row.get("成果の承認基準", "").strip()

            reward_rows = []
            if cpc:
                reward_rows.append(f"<tr><td>CPC報酬</td><td>{cpc}</td></tr>")
            if fixed:
                reward_rows.append(f"<tr><td>定額報酬</td><td>{fixed}</td></tr>")
            if rate:
                reward_rows.append(f"<tr><td>定率報酬</td><td>{rate}</td></tr>")
            if condition:
                reward_rows.append(f"<tr><td>成果条件</td><td>{condition}</td></tr>")
            if approval:
                reward_rows.append(f"<tr><td>承認基準</td><td>{approval}</td></tr>")

            if reward_rows:
                rows_html = "\n".join(reward_rows)
                sections.append(
                    f'<h3>{pname}</h3>\n'
                    f'<table>\n<thead><tr><th>項目</th><th>内容</th></tr></thead>\n'
                    f'<tbody>\n{rows_html}\n</tbody>\n</table>'
                )

        # 基本情報（共通）
        smartphone = first.get("スマホ対応", "").strip()
        itp = first.get("ITP対応済", "").strip()
        self_affiliate = first.get("自己アフィリエイト可能", "").strip()

        info_rows = []
        if company_name:
            info_rows.append(f"<tr><td>運営会社</td><td>{company_name}</td></tr>")
        if site_url:
            info_rows.append(
                f'<tr><td>公式サイト</td><td><a href="{site_url}" target="_blank" rel="noopener">'
                f'{advertiser_name or site_url}</a></td></tr>'
            )
        if smartphone:
            info_rows.append(f"<tr><td>スマホ対応</td><td>{smartphone}</td></tr>")
        if itp:
            info_rows.append(f"<tr><td>ITP対応</td><td>{itp}</td></tr>")
        if self_affiliate:
            is_ok = "可能" if self_affiliate in ("可能", "○", "可") else "不可"
            info_rows.append(f"<tr><td>自己アフィリエイト</td><td>{is_ok}</td></tr>")

        if info_rows:
            rows_html = "\n".join(info_rows)
            sections.append(
                f'<h2>基本情報</h2>\n'
                f'<table>\n<thead><tr><th>項目</th><th>内容</th></tr></thead>\n'
                f'<tbody>\n{rows_html}\n</tbody>\n</table>'
            )

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
        program_name = rows[0].get("プログラム名", "").strip()
        return f"{program_name}のアフィリエイトはどこのASP？"
    else:
        advertiser_name = rows[0].get("広告主名", "").strip()
        return f"{advertiser_name}のアフィリエイトはどこのASP？"


def build_tags(rows):
    """タグを生成"""
    tags = set()
    for row in rows:
        if row.get("CPC報酬", "").strip():
            tags.add("CPC")
        if row.get("定額報酬", "").strip():
            tags.add("定額報酬")
        if row.get("定率報酬", "").strip():
            tags.add("定率報酬")
    return ",".join(sorted(tags))


def group_programs(rows):
    """広告主ごとにグループ化し、まとめ/別記事のルールを適用して記事単位のリストを返す"""
    # 広告主名でグループ化（出現順を保持）
    advertiser_groups = collections.OrderedDict()
    for row in rows:
        adv = row.get("広告主名", "").strip()
        if adv not in advertiser_groups:
            advertiser_groups[adv] = []
        # 重複プログラム名を除外
        prog = row.get("プログラム名", "").strip()
        existing_progs = [r.get("プログラム名", "").strip() for r in advertiser_groups[adv]]
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


def convert_vc_csv(input_path, output_path):
    """バリューコマースCSVをWordPress投稿用CSVに変換"""
    with open(input_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"入力: {len(rows)} 件の案件を読み込みました")

    # グループ化
    article_groups = group_programs(rows)
    print(f"記事数: {len(article_groups)} 件")

    output_rows = []
    for group in article_groups:
        title = build_title(group)
        content = build_article_html(group)
        tags = build_tags(group)

        output_rows.append({
            "title": title,
            "content": content,
            "status": "draft",
            "category": "アフィリエイト案件",
            "tags": tags,
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

    args = parser.parse_args()

    output_path = args.output or "csv/vc_posts.csv"
    result_path = convert_vc_csv(args.input_csv, output_path)

    if args.post:
        from wp_bulk_post import bulk_post_from_csv
        bulk_post_from_csv(result_path, args.status, delay=2, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
