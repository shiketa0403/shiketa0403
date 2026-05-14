#!/usr/bin/env python3
"""
Claude API ラッパー：
  - 農園説明文（200文字、生データを材料に生成）
  - 自治体のレンタル畑情報（Web Search で公式情報を確認、200文字要約 or None）

環境変数:
  ANTHROPIC_API_KEY: Claude API キー

装飾ルール:
  最重要箇所 → <span class="hutoaka">…</span>   （太赤字）
  重要箇所   → <span class="st-mymarker-s">…</span>  （太字+黄色下線）

出力は HTML 断片（<p>...</p> を含む）。
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

MODEL = "claude-sonnet-4-5"  # 2025/05時点で web search 利用可能

DECO_RULES = (
    "装飾ルール:\n"
    "- 最重要箇所は <span class=\"hutoaka\">テキスト</span>（1箇所のみ）\n"
    "- 重要箇所は <span class=\"st-mymarker-s\">テキスト</span>（1〜2箇所）\n"
    "- 上記以外のHTMLタグは使わない（<p> 等の段落タグも不要）\n"
)


def _client():
    try:
        import anthropic
    except ImportError as e:
        raise SystemExit("anthropic SDK が未インストールです（pip install anthropic）") from e
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY が未設定です")
    return anthropic.Anthropic(api_key=api_key)


def generate_farm_description(farm: dict) -> str:
    """農園1件の生データを渡し、200文字程度の説明HTMLを返す。"""
    client = _client()

    materials = (
        f"農園名: {farm.get('name', '')}\n"
        f"住所: {farm.get('address', '')}\n"
        f"最寄駅・アクセス: {farm.get('access', '')}\n"
        f"利用料金: {farm.get('fee', '')}\n"
        f"入会金: {farm.get('entry_fee', '')}\n"
        f"料金に含まれるもの: {farm.get('included_services', '')}\n"
        f"設備: {farm.get('facilities', '')}\n"
        f"特徴タグ: {', '.join(farm.get('status_tags', []))}\n"
        f"シェア畑gardenブランド: {'はい' if farm.get('is_garden') else 'いいえ'}\n"
        f"キャッチコピー: {farm.get('catch_phrase', '')}\n"
    )

    prompt = (
        "次の貸し農園の情報をもとに、ユーザーが利用シーンを想像しやすい説明文を"
        "200文字前後（180〜220字）で書いてください。"
        "事実は与えられた情報の範囲で書き、推測や誇張は避けてください。"
        "「です・ます」調、箇条書きは使わず1段落（200文字前後）でまとめてください。\n\n"
        f"{DECO_RULES}\n"
        "出力は本文HTML（装飾はspanのみ）のみ。前置きや囲み記号は不要。\n\n"
        f"=== 農園情報 ===\n{materials}"
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip() if resp.content else ""
    return text


def generate_local_gov_info(city_name: str) -> Optional[str]:
    """自治体（区/市）公式のレンタル畑情報を Web search で確認し、
    あれば200文字要約HTMLを返す。無ければ None を返す。
    """
    client = _client()

    prompt = (
        f"{city_name} が運営する区民農園・市民農園・貸し農園など、自治体公式の"
        "レンタル畑制度について、公式サイトを確認して内容を200文字前後（180〜220字）で"
        "要約してください。\n\n"
        "ルール:\n"
        f"- 公式情報源（{city_name}公式サイト）に該当する内容が見つからない場合、"
        "  本文を NONE という1単語だけにしてください。\n"
        "- 見つかった場合は、利用方法・料金目安・申込窓口・特徴を中心に要約。\n"
        "- 「です・ます」調、1段落、200文字前後。事実ベースで誇張は避ける。\n"
        f"{DECO_RULES}\n"
        "出力は本文HTML（装飾はspanのみ）のみ。前置きや囲み記号は不要。"
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=800,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}],
        messages=[{"role": "user", "content": prompt}],
    )

    # tool_use のサイクル後、最終 content から text を取り出す
    text_parts = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)
    text = ("\n".join(text_parts)).strip()
    if not text or text.upper().startswith("NONE"):
        return None
    return text


if __name__ == "__main__":
    # 動作確認: python sharebatake_ai.py [city_name]
    if len(sys.argv) < 2:
        sample = {
            "name": "シェア畑 雪が谷大塚駅前",
            "address": "東京都大田区南雪谷2-2-4",
            "access": "東急池上線 雪が谷大塚駅 徒歩2分",
            "fee": "2ウネ区画 14,000円 / 3ウネ区画 16,500円",
            "entry_fee": "11,000円",
            "included_services": "農具資材、種苗・肥料、アドバイザーサポート",
            "facilities": "水場 / トイレ / 休憩スペース / 駐車場 / BBQ",
            "status_tags": ["アクセス良好", "駅から近い", "人気エリア"],
            "is_garden": False,
            "catch_phrase": "東急池上線の雪が谷大塚駅目の前！",
        }
        print(generate_farm_description(sample))
    else:
        info = generate_local_gov_info(sys.argv[1])
        print(info or "(該当無し)")
