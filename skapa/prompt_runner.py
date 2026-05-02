"""Claude API呼び出しのラッパー。

prompts/*.md を読み込んで {{VAR}} を差し替え、Claude に送信する。
WebSearch ツールを必要に応じて有効化できる。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import config


VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def load_prompt(prompt_filename: str) -> str:
    return (config.PROMPTS_DIR / prompt_filename).read_text(encoding="utf-8")


def render_prompt(template: str, variables: dict[str, str]) -> str:
    """{{KEY}} を変数辞書で置換。未定義のキーは空文字。"""
    def _sub(m: re.Match) -> str:
        return variables.get(m.group(1), "")

    return VAR_RE.sub(_sub, template)


def call_claude(
    system_prompt: str,
    user_message: str,
    *,
    enable_web_search: bool = False,
    model: str | None = None,
    max_tokens: int | None = None,
    history: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    """Claude APIを呼び出してテキスト応答と更新済み履歴を返す。

    history を渡すとマルチターン会話を継続できる（プロンプト6の「続けて」自動投入用）。
    """
    import anthropic  # 遅延import

    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY が設定されていません。.env や環境変数で渡してください。"
        )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    messages = list(history) if history else []
    messages.append({"role": "user", "content": user_message})

    kwargs = {
        "model": model or config.CLAUDE_MODEL,
        "max_tokens": max_tokens or config.MAX_TOKENS,
        "system": system_prompt,
        "messages": messages,
    }

    if enable_web_search:
        kwargs["tools"] = [
            {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}
        ]

    resp = client.messages.create(**kwargs)

    # 応答の text ブロックだけ抽出
    text_parts: list[str] = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)
    answer = "\n".join(text_parts).strip()

    messages.append({"role": "assistant", "content": resp.content})
    return answer, messages


def run_prompt(
    prompt_filename: str,
    variables: dict[str, str],
    *,
    user_message: str | None = None,
    enable_web_search: bool = False,
) -> str:
    """1ターンだけプロンプトを実行して応答テキストを返す簡易ヘルパー。

    プロンプトファイル全体を system に置く方式。Input Data 部分は variables で
    {{KEY}} を埋めるか、user_message で別途渡す。
    """
    template = load_prompt(prompt_filename)
    system_prompt = render_prompt(template, variables)
    msg = user_message or "上記のルールに従って実行してください。"
    answer, _ = call_claude(
        system_prompt=system_prompt,
        user_message=msg,
        enable_web_search=enable_web_search,
    )
    return answer


def save_step_output(slug: str, step: int, content: str) -> Path:
    """工程の出力を skapa/drafts/{slug}/ に保存してパスを返す。"""
    out_dir = config.channel_draft_dir(slug)
    fname = config.STEP_FILENAMES[step]
    path = out_dir / fname
    path.write_text(content, encoding="utf-8")
    return path


def load_step_output(slug: str, step: int) -> str | None:
    """以前保存した工程の出力を読み出す（なければ None）。"""
    path = config.channel_draft_dir(slug) / config.STEP_FILENAMES[step]
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None
