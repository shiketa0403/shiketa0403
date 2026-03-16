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

    prompt = f"""あなたはプロのアフィリエイトブロガーです。
以下の案件について、読者が「このサービスを使ってみたい」と思い、アフィリエイターが「この案件を扱いたい」と感じる高品質な紹介文を作成してください。

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

【構成と要件】
以下の3パートで構成してください。各パートは改行で区切ります。

■パート1: サービスの魅力（ユーザー目線）
- このサービス/商品が「どんな人の」「どんな悩みを」解決するかを具体的に書く
- 具体的な数字や特徴を盛り込み、説得力を持たせる

■パート2: アフィリエイトの魅力（アフィリエイター目線）
- 報酬単価、成果条件のハードル、CVRが期待できる理由を具体的に述べる

■パート3: 訴求のコツ
- どんなターゲット層に、どう訴求すると成果が出やすいかを書く
- 最後に「バリューコマースで提携できます」で締める

【装飾ルール】※必ず守ること
紹介文全体の中で、以下の2種類の装飾を使い分けてください。

1. 一番重要な箇所（全体で1箇所だけ）: <span class="st-mymarker-s">太字＋黄色下線のテキスト</span>
   → 読者に最も伝えたい核心的なメリットや特徴に使う

2. 次に大切な箇所（全体で1〜2箇所）: <span class="hutoaka">太赤字のテキスト</span>
   → 補足的に強調したいポイントに使う

装飾の使用例:
「このサービスは<span class="st-mymarker-s">年会費永年無料でポイント還元率が業界最高水準</span>です。さらに<span class="hutoaka">入会キャンペーンで最大5,000ポイント</span>がもらえます。」

【文体・品質ルール】
- 「です・ます」調で統一
- 1文は40〜60文字程度を目安に、読みやすくリズムのある文章にする
- 箇条書きは使わず、自然な文章で書く
- 誇大表現や「絶対」「必ず」などの断定は避け、事実ベースで書く
- タイトル行（「〇〇紹介文」等）は絶対に入れない。本文のみを出力する
- 上記の <span class="st-mymarker-s"> と <span class="hutoaka"> 以外のHTMLタグは使わない
- 全体で500文字程度に収める。必ず文章を最後まで書ききり、途中で切れないようにする

紹介文のみを出力してください。"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def generate_slug(title, client=None):
    """
    記事タイトルからSEO用スラッグを生成する。

    Args:
        title: 記事タイトル
        client: anthropic.Anthropic インスタンス（省略時は自動生成）

    Returns:
        英小文字+ハイフンのスラッグ（1〜3単語）
    """
    if client is None:
        client = _get_client()

    prompt = f"""以下の日本語タイトルから、WordPressのパーマリンク用スラッグを生成してください。

【ルール】
- タイトルに含まれるサービス名・商品名・ブランド名を英語表記で抽出する
- 英小文字とハイフンのみ使用
- 1〜3単語、ハイフン区切り
- 固有名詞がある場合はそれを最優先で使う
- 固有名詞がない場合は内容を表す英単語を使う

【例】
「DMMカード新規発行プログラムのアフィリエイトはどこのASP？」→ dmm-card
「ブーリスチェアオンラインストア-Master Neo&Master RexのアフィリエイトはどこのASP？」→ booris-chair
「楽天モバイルの口コミと評判まとめ」→ rakuten-mobile
「初心者向けおすすめクレジットカード比較」→ beginner-credit-card

【タイトル】
{title}

スラッグのみを出力してください。余計な説明は不要です。"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=30,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip().lower()

    # 余計な文字を除去し、ハイフン区切り3単語以内に制限
    import re
    slug = re.sub(r'[^a-z0-9-]', '', raw)
    slug = slug.strip('-')
    parts = [p for p in slug.split('-') if p]
    return '-'.join(parts[:3])


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
        # スラッグはタイトル確定後に build_title で生成するため、ここでは行単位では生成しない

        # レートリミット対策（軽い待機）
        if i < total - 1:
            time.sleep(0.5)

    if progress:
        print(f"\n  AI処理完了: {total} 件", file=sys.stderr)

    return rows
