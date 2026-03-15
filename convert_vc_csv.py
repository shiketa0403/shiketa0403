#!/usr/bin/env python3
"""
バリューコマースCSV → WordPress投稿用CSV 変換スクリプト

使い方:
  # 変換（出力: csv/vc_posts.csv）
  python convert_vc_csv.py csv/vc_raw.csv

  # 出力先を指定
  python convert_vc_csv.py csv/vc_raw.csv -o csv/vc_posts.csv

  # そのまま投稿（下書き）
  python convert_vc_csv.py csv/vc_raw.csv --post

  # そのまま投稿（ドライラン）
  python convert_vc_csv.py csv/vc_raw.csv --post --dry-run
"""

import argparse
import csv
import sys


def build_article_html(row):
    """案件データからHTML記事本文を生成"""
    program_name = row.get("プログラム名", "").strip()
    program_content = row.get("プログラム内容", "").strip()
    advertiser_name = row.get("広告主名", "").strip()
    company_name = row.get("会社名", "").strip()
    site_url = row.get("広告主サイトURL", "").strip()
    comment = row.get("コメント・注意事項（プログラム）", "").strip()

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

    sections = []

    # プログラム概要
    if program_content:
        # 改行をHTMLに変換
        content_html = program_content.replace("\n", "<br>")
        sections.append(
            f'<h2>プログラム概要</h2>\n<p>{content_html}</p>'
        )

    # コメント・注意事項
    if comment:
        comment_html = comment.replace("\n", "<br>")
        sections.append(
            f'<h2>おすすめポイント</h2>\n<p>{comment_html}</p>'
        )

    # 報酬情報テーブル
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

    return "\n\n".join(sections)


def build_title(row):
    """記事タイトルを生成"""
    program_name = row.get("プログラム名", "").strip()
    advertiser_name = row.get("広告主名", "").strip()
    name = program_name or advertiser_name
    return f"{name}の特徴・報酬まとめ【アフィリエイト案件紹介】"


def build_tags(row):
    """タグを生成"""
    tags = []
    # 成果条件からタグ生成
    condition = row.get("注文発生対象・条件", "").strip()
    if condition:
        tags.append(condition)

    # 報酬タイプ
    if row.get("CPC報酬", "").strip():
        tags.append("CPC")
    if row.get("定額報酬", "").strip():
        tags.append("定額報酬")
    if row.get("定率報酬", "").strip():
        tags.append("定率報酬")

    return ",".join(tags)


def convert_vc_csv(input_path, output_path):
    """バリューコマースCSVをWordPress投稿用CSVに変換"""
    with open(input_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"入力: {len(rows)} 件の案件を読み込みました")

    output_rows = []
    for row in rows:
        title = build_title(row)
        content = build_article_html(row)
        tags = build_tags(row)

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
