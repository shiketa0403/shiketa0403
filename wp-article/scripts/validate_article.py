#!/usr/bin/env python3
"""記事の機械監査スクリプト。

prompts/04〜07 の品質ルールをコードで検証する。
AIの自己申告に頼らず、違反箇所を機械的に列挙する。

使い方:
  python wp-article/scripts/validate_article.py wp-article/out/<slug> --stage text
  python wp-article/scripts/validate_article.py wp-article/out/<slug> --stage final

--stage text : sections/*.html（装飾前の本文）を検証
--stage final: final.html（装飾・画像込みの完成品）を検証

出力: 人間可読レポート(stdout) + <dir>/validate_report.json
exit code: P0/P1エラーがあれば 1、警告のみ/問題なしは 0
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Windows環境でstdoutがcp932になり日本語・記号の出力で落ちるのを防ぐ
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------------------------------------------------------- ルール定義

# P0: 致命的（必ず修正）
BAN_NEUTRALITY = ["絶対おすすめ", "必ず儲かる", "確実に稼げる", "必見", "急いで申し込"]
BAN_ASSERT = ["絶対", "確実に"]  # 「必ず」は説明文脈があるため単体では P1
DATE_PATTERNS = [
    r"[0-9０-９]{4}年[0-9０-９]{1,2}月(時点|現在|確認)",
    r"[0-9０-９]{1,2}月(時点|現在|確認)",
    r"[0-9０-９]{4}年(時点|現在)",
    r"執筆(時点|現在)",
    r"調査(時点)",
]
DA_DEARU = [r"だ。", r"である。", r"だろう。"]

# P1: 重要
REDUNDANT = [
    "になります", "となっています", "となります", "と言えるでしょう",
    "したほうがよいでしょう", "という仕組みです", "という形です",
    "することができます", "と考えられます", "と言ってもよいでしょう",
    "する必要があります", "ではないでしょうか", "参考になれば幸いです",
    "について見ていきましょう", "本記事では",
]
AI_SMELL = ["様々な", "さまざまな", "非常に", "——"]
JARGON = ["ランディングページ", "公式LP", "LPを", "LPで", "LPに", "LPの"]

# P2: 改善
SOFT_WORDS = ["など", "多くの"]

SENT_LEN_WARN = 51
SENT_LEN_ERR = 66
H2_LEN_WARN, H2_LEN_ERR = 26, 31
H3_LEN_WARN, H3_LEN_ERR = 21, 26
PARA_KUTEN_WARN, PARA_KUTEN_ERR = 4, 5
MIN_DIAGRAMS = 4
MIN_TOTAL_CHARS = 8000   # 本文合計（タグ・ショートコード除く）の下限
TARGET_TOTAL_CHARS = 9000
SUMMARY_TARGET_CHARS = 400  # まとめH2セクションの目安（箇条書き含む）
SUMMARY_MAX_CHARS = 500     # これを超えたらP1エラー

SHORTCODE_RE = re.compile(r"\[/?st-[a-z0-9_-]+[^\]]*\]|\[/?st_af[^\]]*\]")
TAG_RE = re.compile(r"<[^>]+>")
NUM_RE = re.compile(r"[0-9０-９][0-9０-９,，.．〜~×%％]*\s*(?:万円|億円|円|%|％|日間|日|週間|ヶ月|カ月|か月|年間|分|時間|件|社|店舗|拠点|人|名|cm|kg|px)")


class Finding:
    def __init__(self, level: str, rule: str, where: str, text: str, hint: str = ""):
        self.level, self.rule, self.where, self.text, self.hint = level, rule, where, text, hint

    def to_dict(self):
        return {"level": self.level, "rule": self.rule, "where": self.where,
                "text": self.text, "hint": self.hint}


def strip_markup(html: str) -> str:
    """タグ・ショートコード・画像プレースホルダを除いた本文テキスト。"""
    text = SHORTCODE_RE.sub("", html)
    text = TAG_RE.sub("", text)
    text = re.sub(r"\{\{IMG:[^}]+\}\}", "", text)
    return text


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=。)", text)
    return [p.strip() for p in parts if p.strip()]


def iter_h_sections(html: str, tag: str) -> list[tuple[str, str]]:
    """(見出しテキスト, セクション本文HTML) のリスト。"""
    pattern = re.compile(rf"<{tag}[^>]*>(.*?)</{tag}>", re.S)
    heads = [(m.start(), m.end(), strip_markup(m.group(1)).strip()) for m in pattern.finditer(html)]
    out = []
    for i, (s, e, title) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(html)
        out.append((title, html[e:end]))
    return out


# ---------------------------------------------------------------- チェック群

def check_text_rules(name: str, html: str, findings: list[Finding]):
    """語尾・禁止語・文長・段落・日付など、装飾前後共通の文章ルール。"""
    text = strip_markup(html)

    # P0: 見出しのMarkdown / pタグ / brタグ
    if re.search(r"^#{2,3}\s", html, re.M):
        findings.append(Finding("P0", "P0-6 Markdown見出し禁止", name, "## / ### が混入"))
    for bad in ("<p>", "<p ", "<br"):
        if bad in html:
            findings.append(Finding("P0", "P0 p/brタグ禁止", name, f"{bad!r} が混入"))

    # P0: だ・である調
    for pat in DA_DEARU:
        for m in re.finditer(pat, text):
            ctx = text[max(0, m.start() - 25):m.end()]
            findings.append(Finding("P0", "P0-1 語尾です・ます統一", name, ctx))

    # P0: 日付表記
    for pat in DATE_PATTERNS:
        for m in re.finditer(pat, text):
            findings.append(Finding("P0", "日付表記禁止", name, m.group(0),
                                    "「時点」「現在」「確認」等の年月表記を削除する"))

    # P0: 中立性
    for w in BAN_NEUTRALITY:
        if w in text:
            findings.append(Finding("P0", "P0-2 中立性(煽り表現)", name, w))
    for w in BAN_ASSERT:
        for m in re.finditer(w, text):
            ctx = text[max(0, m.start() - 15):m.end() + 15]
            # 「絶対に避けたい」等の読者心理描写は許容 → 文脈付きでP1警告に落とす
            findings.append(Finding("P1", "断定語の確認", name, ctx,
                                    "読者心理の描写なら可。サービス推奨の断定なら削除"))

    # P1: 冗長表現・AI臭
    for w in REDUNDANT:
        for _ in re.finditer(re.escape(w), text):
            findings.append(Finding("P1", "P1-6 冗長表現", name, w))
    for w in AI_SMELL:
        if w in text:
            findings.append(Finding("P1", "P1-6 AI臭", name, w))
    for w in JARGON:
        if w in text:
            findings.append(Finding("P1", "P1-11 LP用語禁止", name, w, "「公式サイト」に統一"))

    # P2
    for w in SOFT_WORDS:
        count = len(re.findall(w, text))
        if count >= 3:
            findings.append(Finding("P2", "曖昧語の多用", name, f"「{w}」×{count}回"))

    # P1: 文長（見出し・テーブル・リスト・装飾ボックスを除いた地の文のみ対象。
    # 表のセルやli項目は句点を持たず連結されて誤検知するため）
    prose = strip_markup(strip_paragraph_source(html))
    for sent in split_sentences(prose):
        n = len(sent)
        if n >= SENT_LEN_ERR:
            findings.append(Finding("P1", "P1-1 文長超過", name, sent[:40] + f"…({n}字)"))
        elif n >= SENT_LEN_WARN and not re.search(r"[A-Za-z0-9]", sent):
            findings.append(Finding("P2", "P1-1 文長注意", name, sent[:40] + f"…({n}字)",
                                    "固有名詞・数値を含む文は60字まで許容"))

    # P1: 段落の句点数と空行
    for para in re.split(r"\n\s*\n", strip_paragraph_source(html)):
        p_text = strip_markup(para).strip()
        if not p_text or p_text.startswith(("・", "-")):
            continue
        kuten = p_text.count("。")
        if kuten >= PARA_KUTEN_ERR:
            findings.append(Finding("P1", "P1-2 1段落句点3つまで", name, p_text[:40] + f"…(句点{kuten})"))
        elif kuten == PARA_KUTEN_WARN:
            findings.append(Finding("P2", "P1-2 段落句点数注意", name, p_text[:40] + f"…(句点{kuten})",
                                    "Reasonパートの因果継続なら4つまで許容"))

    # P1: 語尾3連続
    sents = split_sentences(text)
    for i in range(len(sents) - 2):
        tails = [s[-3:] for s in sents[i:i + 3]]
        if len(set(tails)) == 1 and tails[0].endswith("。"):
            findings.append(Finding("P2", "P1-8 語尾連続", name, " / ".join(s[:15] for s in sents[i:i + 3])))
            break


def strip_paragraph_source(html: str) -> str:
    """段落チェック用: 見出し・リスト・テーブル・ショートコード中身を除去。"""
    html = re.sub(r"<h[23][^>]*>.*?</h[23]>", "\n\n", html, flags=re.S)
    html = re.sub(r"<(table|ul|ol|blockquote)[^>]*>.*?</\1>", "\n\n", html, flags=re.S)
    html = re.sub(r"\[st-(mybox|cmemo|kaiwa1|timeline|minihukidashi|mcbutton)[^\]]*\].*?\[/st-\1\]",
                  "\n\n", html, flags=re.S)
    return html


def check_headings(html: str, findings: list[Finding]):
    for m in re.finditer(r"<h2[^>]*>(.*?)</h2>", html, re.S):
        t = strip_markup(m.group(1)).strip()
        if len(t) >= H2_LEN_ERR:
            findings.append(Finding("P1", "H2文字数(30字上限)", "見出し", t))
        elif len(t) >= H2_LEN_WARN:
            findings.append(Finding("P2", "H2文字数(25字推奨)", "見出し", t))
    for m in re.finditer(r"<h3[^>]*>(.*?)</h3>", html, re.S):
        t = strip_markup(m.group(1)).strip()
        if len(t) >= H3_LEN_ERR:
            findings.append(Finding("P1", "H3文字数(25字上限)", "見出し", t))
        elif len(t) >= H3_LEN_WARN:
            findings.append(Finding("P2", "H3文字数(20字推奨)", "見出し", t))


def check_decoration(html: str, findings: list[Finding]):
    """prompts/07 の装飾ルール検証（finalステージ用）。"""
    for h2_title, body in iter_h_sections(html, "h2"):
        where = f"H2「{h2_title[:20]}」"

        # ふきだし: H2あたり2回まで・60字以内・連続禁止
        kaiwa = re.findall(r"\[st-kaiwa1[^\]]*\](.*?)\[/st-kaiwa1\]", body, re.S)
        if len(kaiwa) > 2:
            findings.append(Finding("P1", "ふきだしはH2あたり2回まで", where, f"{len(kaiwa)}回"))
        for k in kaiwa:
            if len(strip_markup(k).strip()) > 60:
                findings.append(Finding("P1", "ふきだし60字以内", where, strip_markup(k)[:40] + "…"))
        if re.search(r"\[/st-kaiwa1\]\s*\[st-kaiwa1", body):
            findings.append(Finding("P1", "ふきだし連続使用禁止", where, "間に段落を挟む"))

        # 同種装飾3連
        for kind in ("st-cmemo", "st-mybox"):
            if len(re.findall(rf"\[{kind}", body)) >= 3:
                findings.append(Finding("P2", f"同種装飾({kind})がH2内に3つ以上", where, ""))

        # H3ごとの色装飾数
        for h3_title, h3body in iter_h_sections(body, "h3"):
            marker = len(re.findall(r'class="st-mymarker-s"', h3body))
            aka = len(re.findall(r'class="hutoaka"', h3body))
            if marker + aka > 3:
                findings.append(Finding("P1", "H3の色装飾は最大2(超過)",
                                        f"H3「{h3_title[:18]}」", f"黄{marker}+赤{aka}"))
            elif marker + aka == 3:
                findings.append(Finding("P2", "H3の色装飾は最大2(要確認)",
                                        f"H3「{h3_title[:18]}」", f"黄{marker}+赤{aka}"))

    # アフィリエイト明示ブロック
    if "アフィリエイトリンクが含まれています" not in html:
        findings.append(Finding("P2", "アフィリエイト明示ブロック", "全体",
                                "リード直後の明示ブロックが見当たらない（アフィリンク無し記事でも掲載推奨）"))

    # アンカー「こちら」
    for m in re.finditer(r"<a [^>]*>(.*?)</a>", html, re.S):
        if strip_markup(m.group(1)).strip() in ("こちら", "詳しくはこちら"):
            findings.append(Finding("P2", "P2-1 アンカー「こちら」禁止", "リンク", m.group(0)[:60]))


def check_numbers_grounding(html: str, facts_path: Path, findings: list[Finding]):
    """本文中の数値が facts.json に存在するか。"""
    if not facts_path.exists():
        findings.append(Finding("P1", "facts.json不在", "全体", "事実シートが見つからない"))
        return
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    corpus = json.dumps(facts, ensure_ascii=False)
    corpus_norm = normalize_digits(corpus)
    text = normalize_digits(strip_markup(html))
    seen = set()
    for m in NUM_RE.finditer(text):
        token = m.group(0).replace(",", "").replace("，", "").strip()
        num_part = re.match(r"[0-9.〜~×%]+", token)
        key = token
        if key in seen:
            continue
        seen.add(key)
        if num_part and num_part.group(0) not in corpus_norm.replace(",", ""):
            findings.append(Finding("P2", "数値の出典未確認", "本文", token,
                                    "facts.jsonに出典付きで存在しない数値。要確認"))


def normalize_digits(s: str) -> str:
    return s.translate(str.maketrans("０１２３４５６７８９％", "0123456789%"))


def check_images(dirpath: Path, html: str, findings: list[Finding]):
    """final: 図解枚数・alt・プレースホルダ整合。"""
    diagrams_path = dirpath / "diagrams.json"
    n_diagrams = 0
    if diagrams_path.exists():
        spec = json.loads(diagrams_path.read_text(encoding="utf-8"))
        n_diagrams = len(spec.get("diagrams", []))
        if n_diagrams < MIN_DIAGRAMS:
            findings.append(Finding("P1", f"図解は最低{MIN_DIAGRAMS}枚", "diagrams.json", f"{n_diagrams}枚"))
        if not spec.get("eyecatch"):
            findings.append(Finding("P1", "アイキャッチ未定義", "diagrams.json", ""))
    else:
        findings.append(Finding("P1", "diagrams.json不在", "全体", ""))

    placeholders = re.findall(r"\{\{IMG:([^}]+)\}\}", html)
    images_json = dirpath / "images.json"
    manifest = {}
    if images_json.exists():
        manifest = {i["file"]: i for i in json.loads(images_json.read_text(encoding="utf-8")).get("images", [])}
        for ph in placeholders:
            if ph not in manifest:
                findings.append(Finding("P0", "画像マニフェスト不整合", "final.html",
                                        f"{{{{IMG:{ph}}}}} が images.json に無い"))
        for f, item in manifest.items():
            alt = item.get("alt", "")
            if not alt or alt in ("画像", "図解", "スクリーンショット"):
                findings.append(Finding("P1", "altテキスト不備", f, alt or "(空)"))
            if not (dirpath / "images" / f).exists():
                findings.append(Finding("P0", "画像ファイル不在", f, "images/ に実ファイルが無い"))
    elif placeholders:
        findings.append(Finding("P0", "images.json不在", "全体", "プレースホルダがあるのにマニフェストが無い"))


def check_lead_structure(html: str, findings: list[Finding]):
    """冒頭ブロックの必須要素（WORKFLOW Phase 7）とH2前CTA（Phase 10）。"""
    if "[st-minihukidashi" not in html or "この記事のまとめ" not in html:
        findings.append(Finding("P1", "まとめボックス不在", "冒頭",
                                "prompts/09の[st-minihukidashi]「この記事のまとめ」形式で出力する。"
                                "独自デザインの「この記事でわかること」等は不可"))
    if 'class="graybox"' not in html:
        findings.append(Finding("P1", "ピックアップボックス不在", "冒頭",
                                "prompts/10のgrayboxテンプレで必ず出力（アフィリンク無しでも公式リンクで）"))

    # まとめH2の特則: H3・図解を置かない
    for title, body in iter_h_sections(html, "h2"):
        if title.strip().endswith("まとめ"):
            if "<h3" in body:
                findings.append(Finding("P2", "まとめH2にH3禁止", f"H2「{title[:18]}」",
                                        "まとめはフラットな本文のみにする"))
            if "{{IMG:" in body or "<img" in body:
                findings.append(Finding("P2", "まとめH2に図解禁止", f"H2「{title[:18]}」",
                                        "まとめセクションには画像を配置しない"))
            n = len(re.sub(r"\s", "", strip_markup(body)))
            if n > SUMMARY_MAX_CHARS:
                findings.append(Finding("P1", f"まとめが長すぎる(最大{SUMMARY_MAX_CHARS}字)",
                                        f"H2「{title[:18]}」", f"{n}字",
                                        "結論1〜2文→箇条書き5項目以内→行動の一押し→CTAに圧縮。"
                                        "箇条書きの内容を本文で繰り返さない"))
            elif n > SUMMARY_TARGET_CHARS:
                findings.append(Finding("P2", f"まとめ長め(目安{SUMMARY_TARGET_CHARS}字)",
                                        f"H2「{title[:18]}」", f"{n}字"))

    # 各H2の直前にCTAボタン（st_af または st-mcbutton）があるか。
    # 最初のH2は冒頭ブロック（ピックアップ内CTA）が直前にあるため免除
    h2s = list(re.finditer(r"<h2[^>]*>(.*?)</h2>", html, re.S))
    prev_end = 0
    for i, m in enumerate(h2s):
        segment = html[prev_end:m.start()]
        prev_end = m.end()
        if i == 0:
            continue
        if "[st_af" not in segment and "st-mcbutton" not in segment:
            title = strip_markup(m.group(1)).strip()
            findings.append(Finding("P1", "H2直前のCTAボタン不在",
                                    f"H2「{title[:18]}」", "各H2の直前にCTAボタンを配置する"))

    # 記事末尾（最後のH2＝まとめセクションの文末）にもCTAボタン必須
    if h2s:
        tail = html[h2s[-1].end():]
        if "[st_af" not in tail and "st-mcbutton" not in tail:
            title = strip_markup(h2s[-1].group(1)).strip()
            findings.append(Finding("P1", "記事末尾のCTAボタン不在",
                                    f"H2「{title[:18]}」の文末",
                                    "最後のH2セクションの文末にCTAボタンを配置する"))


def check_image_spacing(html: str, findings: list[Finding]):
    """画像プレースホルダの直後に空行があるか（WORKFLOW Phase 10）。"""
    lines = html.split("\n")
    for i, line in enumerate(lines):
        if "{{IMG:" not in line:
            continue
        if i + 1 < len(lines) and lines[i + 1].strip():
            m = re.search(r"\{\{IMG:([^}]+)\}\}", line)
            fname = m.group(1) if m else "?"
            findings.append(Finding("P2", "画像直下に空行なし", fname,
                                    lines[i + 1].strip()[:24],
                                    "{{IMG:...}} の直後に空行を1行入れる"))


def check_total_length(html: str, findings: list[Finding]):
    """本文合計の文字数（タグ・ショートコード・空白除く）。"""
    text = re.sub(r"\s", "", strip_markup(html))
    n = len(text)
    if n < MIN_TOTAL_CHARS:
        findings.append(Finding("P1", f"本文量不足(最低{MIN_TOTAL_CHARS}字)", "全体",
                                f"{n}字", f"目標{TARGET_TOTAL_CHARS}〜12,000字。H2を追加して拡充する"))
    elif n < TARGET_TOTAL_CHARS:
        findings.append(Finding("P2", f"本文量注意(目標{TARGET_TOTAL_CHARS}字)", "全体", f"{n}字"))
    else:
        print(f"[情報] 本文文字数: {n}字")


# ---------------------------------------------------------------- main

def run(dirpath: Path, stage: str) -> int:
    findings: list[Finding] = []

    if stage == "text":
        sections = sorted((dirpath / "sections").glob("h2-*.html"))
        if not sections:
            print(f"ERROR: {dirpath}/sections/ に h2-*.html がありません", file=sys.stderr)
            return 1
        for sec in sections:
            html = sec.read_text(encoding="utf-8")
            check_text_rules(sec.name, html, findings)
            check_headings(html, findings)
        joined = "\n\n".join(s.read_text(encoding="utf-8") for s in sections)
        check_numbers_grounding(joined, dirpath / "facts.json", findings)
        check_total_length(joined, findings)
    else:  # final
        final = dirpath / "final.html"
        if not final.exists():
            print(f"ERROR: {final} がありません", file=sys.stderr)
            return 1
        html = final.read_text(encoding="utf-8")
        check_text_rules("final.html", html, findings)
        check_headings(html, findings)
        check_decoration(html, findings)
        check_numbers_grounding(html, dirpath / "facts.json", findings)
        check_images(dirpath, html, findings)
        check_image_spacing(html, findings)
        check_total_length(html, findings)
        check_lead_structure(html, findings)

    # レポート
    order = {"P0": 0, "P1": 1, "P2": 2}
    findings.sort(key=lambda f: order[f.level])
    counts = {"P0": 0, "P1": 0, "P2": 0}
    for f in findings:
        counts[f.level] += 1

    print(f"=== 機械監査レポート ({stage}) ===")
    print(f"P0(致命的): {counts['P0']} / P1(重要): {counts['P1']} / P2(改善): {counts['P2']}")
    for f in findings:
        hint = f" → {f.hint}" if f.hint else ""
        print(f"[{f.level}] {f.rule} @{f.where}: {f.text}{hint}")

    report = {"stage": stage, "counts": counts, "findings": [f.to_dict() for f in findings]}
    (dirpath / "validate_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return 1 if counts["P0"] or counts["P1"] else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", help="out/<slug> ディレクトリ")
    ap.add_argument("--stage", choices=["text", "final"], default="text")
    args = ap.parse_args()
    sys.exit(run(Path(args.dir), args.stage))


if __name__ == "__main__":
    main()
