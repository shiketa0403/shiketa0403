#!/usr/bin/env python3
"""
Claude API（Haiku）を使ったジャンル判定・紹介文生成モジュール

環境変数:
  ANTHROPIC_API_KEY: Anthropic APIキー

使い方:
  from ai_generator import classify_genre, generate_description
"""

import json
import os
import sys
import time

try:
    import anthropic
except ImportError:
    print("anthropic パッケージが必要です: pip install anthropic", file=sys.stderr)
    sys.exit(1)

MODEL = "claude-haiku-4-5-20251001"


def _get_client():
    """Anthropicクライアントを取得"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY 環境変数が設定されていません。\n"
            "取得方法: https://console.anthropic.com/ でAPIキーを発行してください。"
        )
    return anthropic.Anthropic(api_key=api_key)


def classify_genre(row, client=None):
    """
    案件データからジャンル（物販 or 登録）をAIで判定する。

    Args:
        row: CSVの1行分のdict
        client: anthropic.Anthropic インスタンス（省略時は自動生成）

    Returns:
        "物販" or "登録"
    """
    if client is None:
        client = _get_client()

    program_name = row.get("プログラム名", "").strip()
    condition = row.get("注文発生対象・条件", "").strip()
    fixed_reward = row.get("定額報酬", "").strip()
    rate_reward = row.get("定率報酬", "").strip()
    program_content = row.get("プログラム内容", "").strip()

    prompt = f"""以下のアフィリエイト案件のジャンルを「物販」か「登録」のどちらかで判定してください。

- 物販: 商品の購入が成果条件となる案件（ECサイト、通販、定期購入など）
- 登録: 会員登録、資料請求、申込み、口座開設などが成果条件となる案件

【案件情報】
プログラム名: {program_name}
注文発生対象・条件: {condition}
定額報酬: {fixed_reward or "なし"}
定率報酬: {rate_reward or "なし"}
プログラム内容: {program_content[:300]}

「物販」か「登録」の一言だけで回答してください。"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    result = message.content[0].text.strip()

    # 「物販」「登録」以外が返った場合のフォールバック
    if "物販" in result:
        return "物販"
    elif "登録" in result:
        return "登録"
    else:
        # 定率報酬がある場合は物販寄り
        return "物販" if rate_reward else "登録"


def generate_description(row, client=None):
    """
    案件データからアフィリエイト紹介文をAIで生成する。

    Args:
        row: CSVの1行分のdict
        client: anthropic.Anthropic インスタンス（省略時は自動生成）

    Returns:
        生成された紹介文（HTML）
    """
    if client is None:
        client = _get_client()

    program_name = row.get("プログラム名", "").strip()
    company_name = row.get("会社名", "").strip()
    advertiser_name = row.get("広告主名", "").strip()
    condition = row.get("注文発生対象・条件", "").strip()
    approval = row.get("成果の承認基準", "").strip()
    program_content = row.get("プログラム内容", "").strip()

    cpc = row.get("CPC報酬", "").strip()
    fixed_reward = row.get("定額報酬", "").strip()
    rate_reward = row.get("定率報酬", "").strip()

    prompt = f"""あなたはアフィリエイトブログの記事ライターです。
以下の案件について、アフィリエイターがバリューコマース（ASP）に登録したくなるような紹介文を生成してください。

【案件情報】
プログラム名: {program_name}
運営会社: {company_name}
広告主名: {advertiser_name}
注文発生対象・条件: {condition}
成果の承認基準: {approval}
定額報酬: {fixed_reward or "なし"}
定率報酬: {rate_reward or "なし"}
CPC報酬: {cpc or "なし"}
プログラム内容: {program_content}

【要件】
- 以下の3つの観点で、それぞれ1〜2文ずつ書く:
  1. この案件（サービス/商品）の特徴・魅力（ユーザー目線）
  2. アフィリエイトとしてのおすすめポイント（報酬単価、成果条件のハードルの低さ、CVRの高さが期待できる理由など）
  3. おすすめの訴求方法・ターゲット層（どんな読者に刺さるか、どう紹介すると成果が出やすいか）
- 各観点の間は改行で区切る
- HTMLタグは使わず、プレーンテキストで
- 誇大表現は避け、事実ベースで書く
- 「バリューコマースで提携できます」という一文を最後に入れる

紹介文のみを出力してください。"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def process_rows(rows, progress=True):
    """
    複数の案件を一括処理する。

    Args:
        rows: CSVの行リスト
        progress: 進捗表示するか

    Returns:
        list of dict: 各行に "ai_genre" と "ai_description" を追加したリスト
    """
    client = _get_client()
    total = len(rows)

    for i, row in enumerate(rows):
        if progress:
            print(f"  AI処理中: {i + 1}/{total} - {row.get('プログラム名', '')[:30]}...",
                  file=sys.stderr, end="\r")

        row["ai_genre"] = classify_genre(row, client=client)
        row["ai_description"] = generate_description(row, client=client)

        # レートリミット対策（軽い待機）
        if i < total - 1:
            time.sleep(0.5)

    if progress:
        print(f"\n  AI処理完了: {total} 件", file=sys.stderr)

    return rows
