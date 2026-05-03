"""スカパー記事生成のメインワークフロー。

使用例:
    python3 -m skapa.generate エムオン --step 1
    python3 -m skapa.generate m-on --step 1 --force

現状は Step 1（ペルソナ分析）のみ実装。Step 2 以降は順次追加。
"""

from __future__ import annotations

import argparse
import re
import sys

from . import config, prompt_runner, sheet_loader
from .sheet_loader import Channel


_SECTION_RE = re.compile(r"^#{2,4}\s+(.+?)\s*$", re.M)


def extract_section(text: str, heading_keyword: str) -> str:
    """ペルソナ出力から指定見出しのセクション本文を抽出する。

    例: extract_section(persona, "検索意図") → 「検索意図（1文）」セクションの本文
    見出しに heading_keyword を含むセクションの、次の同階層以上の見出しまでを返す。
    """
    matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        if heading_keyword in m.group(1):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[start:end].strip()
    return ""


def load_industry_notes() -> str:
    """業界共通の最新情報メモを読む。なければ空文字。"""
    if config.INDUSTRY_NOTES_PATH.exists():
        return config.INDUSTRY_NOTES_PATH.read_text(encoding="utf-8").strip()
    return ""


def build_channel_facts(ch: Channel) -> str:
    """チャンネル個別の事実データを Markdown 文字列で組み立てる。"""
    lines = [
        f"- チャンネル名: {ch.name}",
        f"- 正式名称: {ch.formal_name}",
        f"- ジャンル: {ch.genre}",
        f"- 月額視聴料（税込）: {ch.monthly_fee}円",
        f"- スカパー基本プラン対応: {'あり' if ch.in_basic else 'なし（個別契約のみ）'}",
        f"- セレクト5/10対応: {'あり' if ch.in_select else 'なし'}",
        f"- スカパー基本料: 月額429円（税込）が別途必要",
    ]
    if ch.note:
        lines.append(f"- 備考: {ch.note}")
    return "\n".join(lines)


def build_step1_variables(ch: Channel) -> dict[str, str]:
    """プロンプト1（ペルソナ分析）に渡す変数を組み立てる。"""
    return {
        "TARGET_KEYWORD": ch.target_keyword,
        "MEDIA_INFO": config.MEDIA_INFO,
        "CHANNEL_FACTS": build_channel_facts(ch),
        "INDUSTRY_NOTES": load_industry_notes(),
    }


def run_step1(ch: Channel, *, force: bool = False) -> str:
    """Step 1: ペルソナ分析を実行。"""
    cached = prompt_runner.load_step_output(ch.slug, 1)
    if cached and not force:
        print(f"[Step 1] キャッシュ利用: {config.channel_draft_dir(ch.slug) / config.STEP_FILENAMES[1]}")
        return cached

    variables = build_step1_variables(ch)
    print(f"[Step 1] ペルソナ分析を実行... (TARGET_KW: {variables['TARGET_KEYWORD']})")
    print(f"[Step 1] WebSearch を有効にして Claude API 呼び出し中（数十秒〜数分）...")

    output = prompt_runner.run_prompt(
        config.PROMPT_FILES[1],
        variables,
        enable_web_search=True,
    )

    path = prompt_runner.save_step_output(ch.slug, 1, output)
    print(f"[Step 1] 完了 → {path}")
    return output


def build_step2_variables(ch: Channel, persona_result: str) -> dict[str, str]:
    """プロンプト2（見出し構成）に渡す変数を組み立てる。"""
    context_parts = [
        "## チャンネル事実データ",
        build_channel_facts(ch),
    ]
    notes = load_industry_notes()
    if notes:
        context_parts.append("\n## 業界の最新情報（手動メンテ・確定情報として優先）\n")
        context_parts.append(notes)
    return {
        "TARGET_KEYWORD": ch.target_keyword,
        "PERSONA_RESULT": persona_result,
        "CONTEXT": "\n".join(context_parts),
    }


def run_step2(ch: Channel, *, force: bool = False) -> str:
    """Step 2: 見出し構成を実行。Step 1 の結果が必要。"""
    cached = prompt_runner.load_step_output(ch.slug, 2)
    if cached and not force:
        print(f"[Step 2] キャッシュ利用: {config.channel_draft_dir(ch.slug) / config.STEP_FILENAMES[2]}")
        return cached

    persona = prompt_runner.load_step_output(ch.slug, 1)
    if not persona:
        print(f"[Step 2] Step 1の出力がありません。先に Step 1 を実行します。")
        persona = run_step1(ch, force=False)

    variables = build_step2_variables(ch, persona)
    print(f"[Step 2] 見出し構成を生成中...")

    output = prompt_runner.run_prompt(
        config.PROMPT_FILES[2],
        variables,
        enable_web_search=False,
    )

    path = prompt_runner.save_step_output(ch.slug, 2, output)
    print(f"[Step 2] 完了 → {path}")
    return output


def build_step3_variables(ch: Channel, persona: str, structure: str) -> dict[str, str]:
    """プロンプト3（構成監査）に渡す変数を組み立てる。

    ペルソナ出力から検索意図・記事のゴール・質問リストを抽出する。
    抽出できなかった場合はペルソナ全文を渡してフォールバック。
    """
    search_intent = extract_section(persona, "検索意図") or persona
    article_goal = extract_section(persona, "記事のゴール") or persona
    questions = extract_section(persona, "答えるべき質問") or persona

    return {
        "TARGET_KEYWORD": ch.target_keyword,
        "SEARCH_INTENT": search_intent,
        "ARTICLE_GOAL": article_goal,
        "QUESTIONS": questions,
        "STRUCTURE": structure,
    }


def run_step3(ch: Channel, *, force: bool = False) -> str:
    """Step 3: 構成監査を実行。Step 1, 2 の結果が必要。"""
    cached = prompt_runner.load_step_output(ch.slug, 3)
    if cached and not force:
        print(f"[Step 3] キャッシュ利用: {config.channel_draft_dir(ch.slug) / config.STEP_FILENAMES[3]}")
        return cached

    persona = prompt_runner.load_step_output(ch.slug, 1)
    if not persona:
        persona = run_step1(ch, force=False)

    structure = prompt_runner.load_step_output(ch.slug, 2)
    if not structure:
        structure = run_step2(ch, force=False)

    variables = build_step3_variables(ch, persona, structure)
    print(f"[Step 3] 構成監査を実行中...")

    output = prompt_runner.run_prompt(
        config.PROMPT_FILES[3],
        variables,
        enable_web_search=False,
    )

    path = prompt_runner.save_step_output(ch.slug, 3, output)
    print(f"[Step 3] 完了 → {path}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="スカパー記事生成")
    parser.add_argument("channel", help="チャンネル名 / 正式名称 / スラッグ / No")
    parser.add_argument("--step", type=int, default=1, help="実行する工程番号（1〜8）")
    parser.add_argument("--force", action="store_true", help="キャッシュを無視して再実行")
    args = parser.parse_args()

    channels = sheet_loader.load_local()
    ch = sheet_loader.find(channels, args.channel)
    if not ch:
        print(f"エラー: チャンネルが見つかりません: {args.channel}", file=sys.stderr)
        print("利用可能（先頭5件）:", file=sys.stderr)
        for c in channels[:5]:
            print(f"  No.{c.no}: {c.name} (slug={c.slug})", file=sys.stderr)
        return 1

    print(f"対象: No.{ch.no} {ch.name}（{ch.formal_name}）")
    print(f"  slug: {ch.slug}")
    print(f"  月額: {ch.monthly_fee}円")
    print(f"  メインKW: {ch.main_kw}")
    print(f"  サブKW: {ch.sub_kw}")
    print()

    runners = {
        1: run_step1,
        2: run_step2,
        3: run_step3,
    }
    if args.step not in runners:
        print(f"Step {args.step} はまだ未実装です。", file=sys.stderr)
        return 2

    output = runners[args.step](ch, force=args.force)
    print()
    print("=" * 60)
    print(f"Step {args.step} 出力:")
    print("=" * 60)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
