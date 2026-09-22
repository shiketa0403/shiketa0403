#!/usr/bin/env python3
"""
地域×現金化 業者発見スクリプト（発見フェーズ）

地域名を渡すと、Claude API の Web Search ツールで
「{地域} クレジットカード現金化 店舗」等を検索し、実在確認できた
業者候補を local-genkinka/master_{slug}.csv に書き出す。

このあと local_genkinka_verify.py --merge を回すと、Places APIの
裏取り結果がマスタに自動反映される（genkinka_area.yml が一括実行）。

使い方:
  ANTHROPIC_API_KEY=xxx python local_genkinka_discover.py --area-ja 新宿 --slug shinjuku

ルール:
- 検索で確認できた業者のみ記録（創作禁止）。閉業疑い等のネガ情報もメモに残す
- 既存マスタがある場合は --force なしでは上書きしない
"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

MODEL = "claude-sonnet-5"

FIELDNAMES = ["エリア", "業者名", "区分", "住所", "アクセスメモ", "営業時間",
              "公式サイト", "掲示・特徴", "状態", "要確認事項"]


def build_prompt(area_ja):
    return f"""あなたは日本の「クレジットカード現金化 × 地域」データベースのリサーチャーです。
対象地域: {area_ja}

web_searchツールで次の観点の検索を実行し、実在する業者・店舗を洗い出してください。
- 「{area_ja} クレジットカード現金化 店舗」
- 「{area_ja} 現金化 店頭 買取」
- 「{area_ja} 金券ショップ クレジットカード」
- 「{area_ja} アマゾンギフト券 買取 店舗」
- 有力候補には「(業者名) {area_ja} 住所 営業時間」の追加検索で公式サイト・住所を確認する

対象とする区分:
(a) 店舗型(現金化専門) … {area_ja}に実店舗があると記載される現金化専門業者
(b) 間接現金化(金券ショップ) … {area_ja}の金券ショップ・ギフト券買取店(チェーンは店舗単位)
(c) エリア対応型 … 近隣拠点だが{area_ja}対応をうたう業者

厳守ルール:
- 検索結果で確認できた業者のみ。推測や創作は絶対にしない
- 「閉業の可能性」「電話不通」などのネガティブ情報も見つけたらメモに記録する
- 公式サイトURLは検索結果で確認できたものだけを書く(推測URL禁止)
- 住所は判明した粒度まで(番地不明なら「駅東口付近(媒体記載)」のように出典を添える)

出力は以下のJSONのみ。前置き・解説は一切不要:
{{"candidates": [{{"業者名": "", "区分": "店舗型(現金化専門)", "住所手がかり": "", "公式サイト": "", "営業時間手がかり": "", "メモ": "出典の要旨・閉業疑い等"}}]}}"""


def extract_json(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("JSONが見つかりません")
    return json.loads(m.group(0))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--area-ja", required=True, help="地域名(日本語・例: 新宿)")
    parser.add_argument("--slug", required=True, help="ローマ字スラッグ(例: shinjuku)")
    parser.add_argument("--force", action="store_true", help="既存マスタを上書き")
    parser.add_argument("--max-searches", type=int, default=10)
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("エラー: 環境変数 ANTHROPIC_API_KEY が未設定です", file=sys.stderr)
        sys.exit(1)

    base = Path("local-genkinka")
    base.mkdir(exist_ok=True)
    master_path = base / f"master_{args.slug}.csv"
    if master_path.exists() and not args.force:
        print(f"{master_path} は既に存在します(上書きは --force)。発見フェーズをスキップします")
        return

    import anthropic
    client = anthropic.Anthropic()

    print(f"発見フェーズ開始: {args.area_ja} (web_search 最大{args.max_searches}回)")
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": args.max_searches,
        }],
        messages=[{"role": "user", "content": build_prompt(args.area_ja)}],
    )

    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    data = extract_json(text)
    candidates = data.get("candidates", [])
    if not candidates:
        print("候補が0件でした。プロンプト・地域名を確認してください", file=sys.stderr)
        sys.exit(1)

    rows = []
    for c in candidates:
        rows.append({
            "エリア": args.area_ja,
            "業者名": c.get("業者名", "").strip(),
            "区分": c.get("区分", "要確認"),
            "住所": c.get("住所手がかり", "") or "要確認",
            "アクセスメモ": c.get("メモ", ""),
            "営業時間": c.get("営業時間手がかり", "") or "要確認",
            "公式サイト": c.get("公式サイト", "") or "要確認",
            "掲示・特徴": c.get("メモ", ""),
            "状態": "未検証(発見フェーズのみ)",
            "要確認事項": "Places裏取り待ち",
        })

    with open(master_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"マスタ書き出し: {master_path} ({len(rows)}件)")
    print(f"検索使用状況: {getattr(resp.usage, 'server_tool_use', '')}")


if __name__ == "__main__":
    main()
