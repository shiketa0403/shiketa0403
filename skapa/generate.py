"""スカパー記事生成のメインワークフロー。

使用例:
    python3 -m skapa.generate エムオン --step 1
    python3 -m skapa.generate m-on --step 1 --force

現状は Step 1（ペルソナ分析）のみ実装。Step 2 以降は順次追加。
"""

from __future__ import annotations

import argparse
import sys

from . import config, prompt_runner, sheet_loader
from .sheet_loader import Channel


def build_step1_variables(ch: Channel) -> dict[str, str]:
    """プロンプト1（ペルソナ分析）に渡す変数を組み立てる。"""
    return {
        "TARGET_KEYWORD": ch.target_keyword,
        "MEDIA_INFO": config.MEDIA_INFO,
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

    if args.step == 1:
        output = run_step1(ch, force=args.force)
        print()
        print("=" * 60)
        print("Step 1 出力:")
        print("=" * 60)
        print(output)
    else:
        print(f"Step {args.step} はまだ未実装です。", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
