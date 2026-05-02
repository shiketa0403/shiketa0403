"""プロンプト4（Markdown）→ プロンプト5（HTML）形式への変換。

出力ルール（プロンプト5/6/7の入力仕様に合わせる）:
- h2/h3 は HTMLタグ
- 段落は空行区切り、<p>でも<br>でも囲まない
- リストは <ul><li>/<ol><li>
- 太字 **text** は <strong>text</strong>
- リンク [text](url) は <a href="url">text</a>
- Markdownテーブル（| --- |）は使わせない方針なので、出てきたら警告のみ（変換しない）
- セルフチェック以降のセクションは破棄する
- コードブロック ``` ... ``` は除去（プレーン化）
"""

from __future__ import annotations

import re

# プロンプト4は「セルフチェック」を末尾に付けるので落とす
SELFCHECK_RE = re.compile(r"(^|\n)#{1,3}\s*セルフチェック.*", re.S)
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
LIST_UL_RE = re.compile(r"^[-*]\s+(.+)$")
LIST_OL_RE = re.compile(r"^\d+\.\s+(.+)$")
CODE_FENCE_RE = re.compile(r"^```")


def _inline(text: str) -> str:
    text = BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = LINK_RE.sub(r'<a href="\2">\1</a>', text)
    return text


def md_to_html(md: str) -> str:
    """プロンプト4の出力Markdownをプロンプト5の入力HTMLに変換。"""
    # セルフチェック以降を切る
    m = SELFCHECK_RE.search(md)
    if m:
        md = md[: m.start()].rstrip()

    lines = md.splitlines()
    out: list[str] = []
    in_code = False
    list_stack: list[str] = []  # 'ul' or 'ol'
    paragraph_buf: list[str] = []

    def flush_paragraph():
        if paragraph_buf:
            text = " ".join(s.strip() for s in paragraph_buf).strip()
            if text:
                out.append(_inline(text))
            paragraph_buf.clear()

    def close_lists(target_depth: int = 0):
        while len(list_stack) > target_depth:
            tag = list_stack.pop()
            out.append(f"</{tag}>")

    for raw in lines:
        line = raw.rstrip()

        # コードブロックは内容をスキップ（除去）
        if CODE_FENCE_RE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue

        # 空行 → 段落区切り
        if not line.strip():
            flush_paragraph()
            close_lists(0)
            # 段落間は空行で区切る
            if out and out[-1] != "":
                out.append("")
            continue

        # 見出し
        h = HEADING_RE.match(line)
        if h:
            flush_paragraph()
            close_lists(0)
            level = len(h.group(1))
            text = _inline(h.group(2).strip())
            # 1, 4, 5, 6 は使わない方針。h1は捨てる、h4以降はh3扱い
            if level == 1:
                continue
            tag = "h2" if level == 2 else "h3"
            if out and out[-1] != "":
                out.append("")
            out.append(f"<{tag}>{text}</{tag}>")
            continue

        # リスト
        ul = LIST_UL_RE.match(line.lstrip())
        ol = LIST_OL_RE.match(line.lstrip())
        if ul or ol:
            flush_paragraph()
            want = "ul" if ul else "ol"
            if not list_stack or list_stack[-1] != want:
                close_lists(0)
                out.append(f"<{want}>")
                list_stack.append(want)
            content = (ul or ol).group(1)
            out.append(f"<li>{_inline(content)}</li>")
            continue

        # それ以外は段落
        paragraph_buf.append(line)

    flush_paragraph()
    close_lists(0)

    # 連続空行を1つにまとめる
    cleaned: list[str] = []
    blank_prev = False
    for line in out:
        if line == "":
            if blank_prev:
                continue
            blank_prev = True
        else:
            blank_prev = False
        cleaned.append(line)

    # 末尾の空行を落とす
    while cleaned and cleaned[-1] == "":
        cleaned.pop()

    return "\n".join(cleaned) + "\n"


if __name__ == "__main__":
    import sys

    src = sys.stdin.read() if not sys.argv[1:] else open(sys.argv[1]).read()
    print(md_to_html(src))
