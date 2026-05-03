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


# ブロック扱いするタグ（行頭がこれらで始まる行は段落分割しない）
_BLOCK_TAG_PREFIX_RE = re.compile(
    r"^</?(?:h[1-6]|ul|ol|li|table|thead|tbody|tr|th|td|div|blockquote|cite|p|pre|code|hr|br|figure|figcaption)\b",
    re.I,
)


def normalize_paragraph_breaks(html: str) -> str:
    """1行に複数の「。」がある平文段落を、1文1段落に分割する。

    ルール:
    - 行頭がブロック要素タグ（h2/ul/li/table 等）、ショートコード `[`、
      テーブル区切り `|`、引用 `>` で始まる行は触らない
    - 行頭が `<a>` `<strong>` などインラインHTMLの場合は平文行として扱い、
      行内の「。」直後で分割する
    - 「。」直後にインラインの閉じタグ（</strong>, </span>, </a> 等）が
      連続する場合は、それらをまとめて 「。」 と同じ側に含める
      （タグの跨ぎ分割で空段落が生じ WP に &nbsp; を挿入される問題を防ぐ）
    - 連続する空行は1つにまとめる
    """
    out: list[str] = []
    for line in html.splitlines():
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        # ショートコード・テーブル・引用は素通し
        if stripped[0] in "[|>":
            out.append(line)
            continue
        # ブロック要素タグで始まる行は素通し（インラインタグは対象に含める）
        if stripped.startswith("<") and _BLOCK_TAG_PREFIX_RE.match(stripped):
            out.append(line)
            continue
        # 「。」 + 連続する閉じインラインタグを区切りに分割
        parts = _split_after_period(line)
        if len(parts) <= 1:
            out.append(line)
            continue
        for i, part in enumerate(parts):
            if i > 0:
                out.append("")
            out.append(part.strip())

    # 連続空行を1つに圧縮
    cleaned: list[str] = []
    prev_blank = False
    for line in out:
        is_blank = not line.strip()
        if is_blank and prev_blank:
            continue
        cleaned.append(line)
        prev_blank = is_blank

    return "\n".join(cleaned)


_INLINE_CLOSE_TAG_RE = re.compile(r"</(?:strong|em|span|a|b|i|small|sub|sup|mark|u|s)>", re.I)


def _split_after_period(line: str) -> list[str]:
    """「。」直後（および直後に連続する閉じインラインタグ含む）で文字列を分割する。"""
    parts: list[str] = []
    pos = 0
    n = len(line)
    while pos < n:
        idx = line.find("。", pos)
        if idx == -1:
            parts.append(line[pos:])
            break
        end = idx + 1
        # 「。」直後に続く閉じインラインタグを取り込む
        while end < n:
            m = _INLINE_CLOSE_TAG_RE.match(line, end)
            if m:
                end = m.end()
                continue
            # 空白も取り込む（次の文との境界を整えるため）
            if line[end] == " ":
                end += 1
                continue
            break
        parts.append(line[pos:end])
        pos = end
    return [p for p in parts if p.strip()]


if __name__ == "__main__":
    import sys

    src = sys.stdin.read() if not sys.argv[1:] else open(sys.argv[1]).read()
    print(md_to_html(src))
