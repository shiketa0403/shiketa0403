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
import re
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
        "「です・ます」調、箇条書きは使わない。\n\n"
        "段落・改行ルール:\n"
        "- 1文（句点「。」で区切る単位）ごとに段落を分け、段落の間に空行を1行入れる。\n"
        "- <p> や <br> などのタグは使わない（空行で段落分けを表現）。\n"
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
        f"あなたのタスクは、{city_name} が運営する区民農園・市民農園・体験農園など、"
        "自治体公式のレンタル畑制度を **Web 検索で必ず見つけて** 200 文字前後"
        "（180〜220字）で要約することです。\n\n"
        "## 検索戦略（必ずこの順に試す）\n"
        f"1. 検索クエリ: 「{city_name} 区民農園」「{city_name} 市民農園」"
        f"「{city_name} 体験農園」「{city_name} 農園 利用」を順に試す。\n"
        f"2. 上記で見つからなければ、{city_name} の公式サイト（city.〇〇.tokyo.jp / city.〇〇.lg.jp 等）"
        "を直接当てにいく。例: `site:city.ota.tokyo.jp 農園`、`site:city.setagaya.lg.jp 区民農園` のような検索。\n"
        "3. 公式サイトの該当ページ本文を取得して内容を読む（一次情報優先）。\n"
        "4. 公式に該当ページが存在しない場合に限り、観光協会・JA・市民向け情報サイト等を補助的に参照する。\n\n"
        "## 要約内容（優先順位）\n"
        "- 制度の概要（区民農園/体験農園 等の呼称）\n"
        "- 利用料金（不明な場合は「料金は要問い合わせ」等で明記）\n"
        "- 申込窓口・連絡先（部署名や問い合わせ先）\n"
        "- 利用期間・募集時期・抽選有無 など特徴\n\n"
        "## 判定ルール\n"
        f"- {city_name} の **公式の制度が存在するなら**、料金や一部詳細が不明でも、見つかった範囲で要約してください。"
        "全部揃っていなくても OK。不明部分は「要問い合わせ」「公式サイトでご確認ください」などと書く。\n"
        f"- {city_name} に **そもそも自治体運営のレンタル畑制度が存在しない** と判断される場合のみ、"
        "最終回答を **NONE** という1単語だけにしてください。\n"
        "- 「です・ます」調、1段落、200文字前後。事実ベース、誇張なし。\n"
        "- 検索した事実や情報源の有無に言及しない。読者に直接語りかける文体で書く。\n"
        "- 段落分けや改行はせず、1段落で書く。\n"
        f"{DECO_RULES}\n"
        "\n"
        "## 出力フォーマット（最重要）\n"
        "あなたは検索の合間に「次にこう調べる」「料金が分からないので別を調べる」のような\n"
        "思考メモを自由に書いて構いません。ただし、**最終回答は必ず以下の形式で囲んで**\n"
        "出力してください。記事には `<final>` と `</final>` の **間の本文だけ** を採用します。\n"
        "\n"
        "<final>\n"
        "（ここに 200 文字前後の本文 HTML。装飾は span のみ。前置き禁止。改行・空行禁止。）\n"
        "</final>\n"
        "\n"
        "タグの外で何を書いてもOKです。記事には反映されません。\n"
        "制度が存在しない場合は <final>NONE</final> としてください。"
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
        messages=[{"role": "user", "content": prompt}],
    )

    # 全 text ブロックを連結して、その中から <final>...</final> を抽出する
    text_blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    full_text = "\n".join(text_blocks).strip()

    # デバッグ: 生の AI 出力をログに（行頭・末尾各 600 字）
    if full_text:
        preview = full_text if len(full_text) <= 1200 else (full_text[:600] + "\n…\n" + full_text[-600:])
        print(f"[gov_ai] 生出力 ({len(full_text)}字):\n{preview}", flush=True)

    # <final>...</final> を優先採用
    m = re.search(r"<final>\s*(.*?)\s*</final>", full_text, re.DOTALL | re.IGNORECASE)
    if m:
        text = m.group(1).strip()
    else:
        # タグなしの場合は最後の text ブロック → メタ前置き除去にフォールバック
        text = (text_blocks[-1].strip() if text_blocks else "")
        text = _strip_meta_preface(text)
        if text:
            print("[gov_ai] <final> タグなし。フォールバック処理を適用", flush=True)

    if not text:
        return None
    # NONE 判定
    if re.search(r"\bNONE\b", text, re.IGNORECASE):
        return None
    # 万一中に <p>/<br> が混ざってたら剥がす（記事 render 側で再整形される）
    text = re.sub(r"</?p[^>]*>", "", text)
    text = re.sub(r"<br\s*/?>", "", text, flags=re.IGNORECASE)
    return text.strip()


_META_PREFACE_PATTERNS = [
    # サイト確認系
    r"公式サイト(で|から)?(.{0,15})?確認できました",
    r"公式サイト(で|から)?(.{0,30})?明記され(て)?(い)?ません",
    # 検索プロセス言及
    r"Web ?検索(結果)?(から|で)",
    r"追加で検索(します|してみます)",
    r"(もう一度|別の角度|改めて)(.{0,5})?検索(します|してみます|してみる)",
    r"PDF(の|チラシ)(.{0,30})?(確認|チェック)(する|します|必要)",
    # 要約宣言・前置き
    r"これまでの情報(を|に)?(もとに|基に|元に)?(要約します|まとめます)",
    r"(見つかった|得られた)情報(を|に)?(もとに|基に|元に)(要約|まとめ)",
    r"以下に(要約|まとめ)(します)?",
    r"(調査|リサーチ)(の結果|によると)",
    r"まとめると",
    r"これらを(まとめる|要約する)と",
    r"以上(の|から)(情報|内容)",
    # 文脈推定・存在判断
    r"制度(自体)?は存在(します|する)(ので|ため)",
    r"情報は見つかりましたが",
    r"(料金|詳細|内容)が(.{0,30})?(明記|記載)されて(い)?ません",
    r"有料であることは確実",
]


def _strip_meta_preface(text: str) -> str:
    """先頭〜本論前までに混じった『AI の作業説明』段落を除去する。

    各段落（空行区切り）を見て、メタ発言パターンを含む段落を最大8つまで先頭から落とす。
    本論（自治体制度の説明）に入った段落は残す。
    """
    # 段落（空行区切り）に分割。HTML 段落タグも考慮（<p>...</p>）
    chunks = re.split(r"\n\s*\n", text)
    chunks = [c.strip() for c in chunks if c.strip()]
    drop_count = 0
    while chunks and drop_count < 8:
        first = chunks[0]
        # HTML タグを除去した素テキストで判定
        plain = re.sub(r"<[^>]+>", "", first)
        is_meta = any(re.search(p, plain) for p in _META_PREFACE_PATTERNS)
        if not is_meta:
            break
        chunks.pop(0)
        drop_count += 1
    return "\n\n".join(chunks)


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
