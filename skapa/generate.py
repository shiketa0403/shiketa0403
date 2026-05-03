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

from . import config, md_to_html, prompt_runner, sheet_loader
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


def build_step4_variables(ch: Channel, persona: str, audited_structure: str) -> dict[str, str]:
    """プロンプト4（本文作成）に渡す変数を組み立てる。

    audited_structure は Step 3 の「修正後の完成構成」セクションを抽出済みのもの。
    独自情報メモにはチャンネル事実 + 業界ナレッジを入れる。
    """
    search_intent = extract_section(persona, "検索意図") or ""
    ideal_state = extract_section(persona, "検索後の理想状態") or ""
    concerns = extract_section(persona, "不安・懸念") or ""
    article_goal = extract_section(persona, "記事のゴール") or ""

    original_info_parts = [
        "## チャンネル事実データ",
        build_channel_facts(ch),
    ]
    notes = load_industry_notes()
    if notes:
        original_info_parts.append("\n## 業界の最新情報（手動メンテ・確定情報として優先）\n")
        original_info_parts.append(notes)

    return {
        "TARGET_KEYWORD": ch.target_keyword,
        "SEARCH_INTENT": search_intent,
        "IDEAL_STATE": ideal_state,
        "CONCERNS": concerns,
        "ARTICLE_GOAL": article_goal,
        "STRUCTURE": audited_structure,
        "ORIGINAL_INFO": "\n".join(original_info_parts),
    }


def run_step4(ch: Channel, *, force: bool = False) -> str:
    """Step 4: 本文作成（Markdown）を実行。Step 1〜3 の結果が必要。"""
    cached = prompt_runner.load_step_output(ch.slug, 4)
    if cached and not force:
        print(f"[Step 4] キャッシュ利用: {config.channel_draft_dir(ch.slug) / config.STEP_FILENAMES[4]}")
        return cached

    persona = prompt_runner.load_step_output(ch.slug, 1)
    if not persona:
        persona = run_step1(ch, force=False)

    audit = prompt_runner.load_step_output(ch.slug, 3)
    if not audit:
        audit = run_step3(ch, force=False)

    audited_structure = extract_section(audit, "修正後") or audit
    if not audited_structure:
        print(f"[Step 4] 警告: 「修正後の完成構成」を抽出できなかったため、監査出力全文を渡します。", file=sys.stderr)
        audited_structure = audit

    variables = build_step4_variables(ch, persona, audited_structure)
    print(f"[Step 4] 本文作成中（時間がかかる可能性あり）...")

    output = prompt_runner.run_prompt(
        config.PROMPT_FILES[4],
        variables,
        enable_web_search=True,  # 数字や仕様の最新確認用
    )

    path = prompt_runner.save_step_output(ch.slug, 4, output)
    print(f"[Step 4] 完了 → {path}")
    return output


def _extract_html_artifact(text: str) -> str:
    """プロンプト5/6/7が出力するHTMLアーティファクト（textarea埋め込み）から
    本文だけを取り出す。<textarea>...</textarea>の中身を返す。
    見つからなければ全文返す。
    """
    m = re.search(r"<textarea[^>]*>(.*?)</textarea>", text, re.S)
    if m:
        # HTMLエンティティのデコード
        body = m.group(1)
        body = body.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        return body.strip()
    # textareaが無ければ、最初の<h2>から最後までを返す
    m = re.search(r"<h2[^>]*>.*", text, re.S)
    if m:
        return m.group(0).strip()
    return text.strip()


def run_step5_audit(ch: Channel, *, force: bool = False) -> str:
    """Step 5 Phase 1: 本文監査レポート生成。"""
    audit_path = config.channel_draft_dir(ch.slug) / "05_body_audit_report.md"
    history_path = config.channel_draft_dir(ch.slug) / "05_history.json"

    if audit_path.exists() and not force:
        print(f"[Step 5a] キャッシュ利用: {audit_path}")
        return audit_path.read_text(encoding="utf-8")

    body_md = prompt_runner.load_step_output(ch.slug, 4)
    if not body_md:
        body_md = run_step4(ch, force=False)

    # MD → HTML 変換
    body_html = md_to_html.md_to_html(body_md)
    html_path = config.channel_draft_dir(ch.slug) / "04_body.html"
    html_path.write_text(body_html, encoding="utf-8")
    print(f"[Step 5a] MD→HTML変換完了: {html_path}")

    # プロンプト5を system に置き、本文HTMLを user に渡してフェーズ1実行
    system_prompt = prompt_runner.load_prompt(config.PROMPT_FILES[5])
    print(f"[Step 5a] 本文監査レポートを生成中...")

    audit, messages = prompt_runner.call_claude(
        system_prompt=system_prompt,
        user_message=body_html,
        enable_web_search=False,
    )

    audit_path.write_text(audit, encoding="utf-8")
    prompt_runner.save_conversation(ch.slug, 5, messages)
    print(f"[Step 5a] 完了 → {audit_path}")
    print(f"[Step 5a] 履歴保存 → {history_path}")
    return audit


def run_step5_apply(ch: Channel, approval_message: str = "OK") -> str:
    """Step 5 Phase 2: 監査結果をユーザー承認後、修正版HTMLを取得。"""
    history = prompt_runner.load_conversation(ch.slug, 5)
    if not history:
        print(f"[Step 5b] エラー: Step 5 Phase 1 (監査)を先に実行してください。", file=sys.stderr)
        sys.exit(2)

    system_prompt = prompt_runner.load_prompt(config.PROMPT_FILES[5])
    print(f"[Step 5b] 承認応答「{approval_message}」を送信中...")

    raw, messages = prompt_runner.call_claude(
        system_prompt=system_prompt,
        user_message=approval_message,
        history=history,
        enable_web_search=False,
    )

    # textarea から本文を取り出す
    body_html = _extract_html_artifact(raw)

    out_path = config.channel_draft_dir(ch.slug) / config.STEP_FILENAMES[5]
    out_path.write_text(body_html, encoding="utf-8")
    prompt_runner.save_conversation(ch.slug, 5, messages)
    print(f"[Step 5b] 完了 → {out_path}")
    return body_html


def run_step6_plan(ch: Channel, *, force: bool = False) -> str:
    """Step 6 Phase 1: 装飾プランを生成。"""
    plan_path = config.channel_draft_dir(ch.slug) / "06_decoration_plan.md"
    if plan_path.exists() and not force:
        print(f"[Step 6a] キャッシュ利用: {plan_path}")
        return plan_path.read_text(encoding="utf-8")

    body_html = (config.channel_draft_dir(ch.slug) / config.STEP_FILENAMES[5]).read_text(encoding="utf-8")
    if not body_html.strip():
        print(f"[Step 6a] エラー: Step 5の出力（05_body_audit.html）がありません。", file=sys.stderr)
        sys.exit(2)

    system_prompt = prompt_runner.load_prompt(config.PROMPT_FILES[6])
    print(f"[Step 6a] 装飾プランを生成中...")

    plan, messages = prompt_runner.call_claude(
        system_prompt=system_prompt,
        user_message=body_html,
        enable_web_search=False,
    )

    plan_path.write_text(plan, encoding="utf-8")
    prompt_runner.save_conversation(ch.slug, 6, messages)
    print(f"[Step 6a] 完了 → {plan_path}")
    return plan


def run_step6_apply(ch: Channel, approval_message: str = "OK", *, max_sections: int = 15) -> str:
    """Step 6 Phase 2: 装飾済み本文をセクション単位で取得し、自動で続けて連投。"""
    history = prompt_runner.load_conversation(ch.slug, 6)
    if not history:
        print(f"[Step 6b] エラー: Step 6 Phase 1 (プラン)を先に実行してください。", file=sys.stderr)
        sys.exit(2)

    system_prompt = prompt_runner.load_prompt(config.PROMPT_FILES[6])
    sections: list[str] = []

    print(f"[Step 6b] 承認応答「{approval_message}」を送信中...")
    response, history = prompt_runner.call_claude(
        system_prompt=system_prompt,
        user_message=approval_message,
        history=history,
        enable_web_search=False,
    )
    sections.append(response)
    print(f"[Step 6b] セクション 1 取得")

    final_marker = "フェーズ3"  # プロンプト6の最終チェック開始マーカー
    for i in range(max_sections):
        if final_marker in response:
            print(f"[Step 6b] 全セクション出力完了（フェーズ3マーカー検出）")
            break

        print(f"[Step 6b] 「続けて」を送信中... ({i + 2}/{max_sections + 1})")
        response, history = prompt_runner.call_claude(
            system_prompt=system_prompt,
            user_message="続けて",
            history=history,
            enable_web_search=False,
        )
        sections.append(response)
    else:
        print(f"[Step 6b] 警告: 最大反復数 {max_sections} に達しました。", file=sys.stderr)

    # 各セクションの textarea から HTML を抽出して連結
    extracted: list[str] = []
    for sec in sections:
        # 各レスポンスに textarea が含まれていればその中身を抽出
        m = re.search(r"<textarea[^>]*>(.*?)</textarea>", sec, re.S)
        if m:
            body = m.group(1)
            body = body.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
            extracted.append(body.strip())
        else:
            # textareaが無い（Phase 3 など）はスキップ
            pass

    full_html = "\n\n".join(extracted)
    out_path = config.channel_draft_dir(ch.slug) / config.STEP_FILENAMES[6]
    out_path.write_text(full_html, encoding="utf-8")

    # Phase 3 の最終チェックレポートも別途保存
    final_check_path = config.channel_draft_dir(ch.slug) / "06_final_check.md"
    final_text = sections[-1] if sections else ""
    if final_marker in final_text:
        final_check_path.write_text(final_text, encoding="utf-8")

    prompt_runner.save_conversation(ch.slug, 6, history)
    print(f"[Step 6b] 完了 → {out_path} ({len(extracted)}セクション)")
    return full_html


def run_step7_candidates(ch: Channel, *, force: bool = False) -> str:
    """Step 7 Phase 1: 外部発リンク候補を提示。"""
    candidates_path = config.channel_draft_dir(ch.slug) / "07_link_candidates.md"
    if candidates_path.exists() and not force:
        print(f"[Step 7a] キャッシュ利用: {candidates_path}")
        return candidates_path.read_text(encoding="utf-8")

    body_html = (config.channel_draft_dir(ch.slug) / config.STEP_FILENAMES[6]).read_text(encoding="utf-8")
    if not body_html.strip():
        print(f"[Step 7a] エラー: Step 6の出力（06_decoration.html）がありません。", file=sys.stderr)
        sys.exit(2)

    system_prompt = prompt_runner.load_prompt(config.PROMPT_FILES[7])
    print(f"[Step 7a] 発リンク候補を抽出中（WebSearch有効・時間がかかります）...")

    candidates, messages = prompt_runner.call_claude(
        system_prompt=system_prompt,
        user_message=body_html,
        enable_web_search=True,  # 公的機関URLの実在確認用
    )

    candidates_path.write_text(candidates, encoding="utf-8")
    prompt_runner.save_conversation(ch.slug, 7, messages)
    print(f"[Step 7a] 完了 → {candidates_path}")
    return candidates


def run_step7_apply(ch: Channel, approval_message: str = "OK") -> str:
    """Step 7 Phase 2: 承認後にリンク挿入済みHTMLを取得。"""
    history = prompt_runner.load_conversation(ch.slug, 7)
    if not history:
        print(f"[Step 7b] エラー: Step 7 Phase 1 (候補抽出)を先に実行してください。", file=sys.stderr)
        sys.exit(2)

    system_prompt = prompt_runner.load_prompt(config.PROMPT_FILES[7])
    print(f"[Step 7b] 承認応答「{approval_message}」を送信中...")

    raw, messages = prompt_runner.call_claude(
        system_prompt=system_prompt,
        user_message=approval_message,
        history=history,
        enable_web_search=False,
    )

    body_html = _extract_html_artifact(raw)

    out_path = config.channel_draft_dir(ch.slug) / config.STEP_FILENAMES[7]
    out_path.write_text(body_html, encoding="utf-8")
    prompt_runner.save_conversation(ch.slug, 7, messages)
    print(f"[Step 7b] 完了 → {out_path}")
    return body_html


def run_step8(ch: Channel, *, force: bool = False) -> str:
    """Step 8: 本文の冒頭に挿入するリード文 + ピックアップボックスを生成し、
    本文と結合して最終HTMLを保存する。"""
    cached = prompt_runner.load_step_output(ch.slug, 8)
    if cached and not force:
        print(f"[Step 8] キャッシュ利用: {config.channel_draft_dir(ch.slug) / config.STEP_FILENAMES[8]}")
        return cached

    body_path = config.channel_draft_dir(ch.slug) / config.STEP_FILENAMES[7]
    if not body_path.exists():
        print(f"[Step 8] エラー: Step 7の出力（07_links.html）がありません。", file=sys.stderr)
        sys.exit(2)
    body_html = body_path.read_text(encoding="utf-8")

    system_prompt = prompt_runner.load_prompt(config.PROMPT_FILES[8])
    print(f"[Step 8] リード文を生成中...")

    lead, _ = prompt_runner.call_claude(
        system_prompt=system_prompt,
        user_message=body_html,
        enable_web_search=False,
    )

    # リード保存（参考用）
    lead_path = config.channel_draft_dir(ch.slug) / "08_lead.html"
    lead_path.write_text(lead, encoding="utf-8")

    # 最終HTML = リード + 本文
    final_html = lead.strip() + "\n\n" + body_html.strip() + "\n"
    final_path = config.channel_draft_dir(ch.slug) / config.STEP_FILENAMES[8]
    final_path.write_text(final_html, encoding="utf-8")
    print(f"[Step 8] 完了 → {final_path}")
    return final_html


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
    parser.add_argument(
        "--apply",
        nargs="?",
        const="OK",
        default=None,
        help="ユーザー確認フェーズで承認応答を送信して次の出力を取得（Step 5/6/7用）。"
             "値を指定しない場合は 'OK' が送られる。例: --apply 'OK' / --apply '1番除外'",
    )
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

    if args.step == 5:
        if args.apply is not None:
            output = run_step5_apply(ch, approval_message=args.apply)
        else:
            output = run_step5_audit(ch, force=args.force)
    elif args.step == 6:
        if args.apply is not None:
            output = run_step6_apply(ch, approval_message=args.apply)
        else:
            output = run_step6_plan(ch, force=args.force)
    elif args.step == 7:
        if args.apply is not None:
            output = run_step7_apply(ch, approval_message=args.apply)
        else:
            output = run_step7_candidates(ch, force=args.force)
    elif args.step in {1, 2, 3, 4, 8}:
        runners = {1: run_step1, 2: run_step2, 3: run_step3, 4: run_step4, 8: run_step8}
        output = runners[args.step](ch, force=args.force)
    else:
        print(f"Step {args.step} はまだ未実装です。", file=sys.stderr)
        return 2

    print()
    print("=" * 60)
    print(f"Step {args.step} 出力:")
    print("=" * 60)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
