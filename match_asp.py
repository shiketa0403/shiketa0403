#!/usr/bin/env python3
"""
VC案件 × 他ASP案件のマッチングスクリプト（2段階判定）

判定ロジック:
  ◎ 案件名一致 ... VCのブランド名がA8の案件名に含まれる（同一サービスの確度が高い）
  ○ 会社名一致 ... 会社名は一致するがブランド名は不一致（同社の別サービスの可能性あり＝要確認）
  （空）       ... A8に該当なし

ブランド名は VCの広告主名 / プログラム名【】内 から抽出する。

使い方:
  python match_asp.py --a8 csv/a8_programs.csv
出力:
  csv/asp_match.csv
"""

import argparse
import csv
import os
import re


def normalize_company(name):
    """会社名を正規化（法人格・記号・空白を除去）"""
    if not name:
        return ""
    s = _zen2han(name).upper()
    for kw in ["株式会社", "有限会社", "合同会社", "合資会社", "一般社団法人",
               "一般財団法人", "特定非営利活動法人", "CO.,LTD.", "CO.,LTD",
               "CO., LTD.", "INC.", "INC", "LTD.", "LTD", "(株)", "（株）"]:
        s = s.replace(kw, "")
    s = re.sub(r"[\s　、，・,.\-‐―ー（）()【】\[\]「」『』/／&＆'’\"”!！?？]", "", s)
    return s


def _zen2han(s):
    return s.strip().translate(str.maketrans(
        "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
        "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"))


def normalize_text(s):
    """案件名照合用の正規化（記号・空白除去、大文字化）"""
    if not s:
        return ""
    s = _zen2han(s).upper()
    s = re.sub(r"[\s　、，・,.\-‐―ー（）()【】\[\]「」『』/／&＆'’\"”!！?？～~|｜★☆/]", "", s)
    return s


def extract_brand(program_name, advertiser_name):
    """VC案件からブランド名候補を抽出する"""
    cands = []
    # 1) プログラム名【】内
    for m in re.findall(r"[【\[]([^】\]]+)[】\]]", program_name):
        cands.append(m)
    # 2) 「」内
    for m in re.findall(r"[「『]([^」』]+)[」』]", program_name):
        cands.append(m)
    # 3) 広告主名（公式/サイト/オンラインショップ等の語尾を除去）
    adv = advertiser_name
    for kw in ["公式サイト", "公式", "オンラインショップ", "オンラインストア",
               "ONLINE SHOP", "ONLINE STORE", "通販", "サイト"]:
        adv = adv.replace(kw, "")
    adv = adv.strip()
    if adv:
        cands.append(adv)
    # 短すぎる候補（2文字未満）は除外、正規化
    norms = []
    for c in cands:
        n = normalize_text(c)
        if len(n) >= 2:
            norms.append(n)
    return norms


def load_a8(path):
    rows = []
    by_company = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            r["_name_norm"] = normalize_text(r.get("program_name", ""))
            key = normalize_company(r.get("company_name", ""))
            r["_company_norm"] = key
            if key:
                by_company.setdefault(key, []).append(r)
    return rows, by_company


def load_asp(path, has_company=True):
    """ASPのCSVを読み込み、正規化済みの行リストと会社名インデックスを返す"""
    rows = []
    by_company = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            r["_name_norm"] = normalize_text(r.get("program_name", ""))
            key = normalize_company(r.get("company_name", "")) if has_company else ""
            r["_company_norm"] = key
            if key:
                by_company.setdefault(key, []).append(r)
    return rows, by_company


def match_one(brands, ckey, rows, by_company, has_company=True):
    """1つのASPに対するVC案件のマッチ判定。
    戻り値: (mark, matched_name)
      ◎ ... 案件名（ブランド名）一致
      ○ ... 会社名のみ一致（会社名ありASPのみ）
      '' ... 該当なし
    """
    company_hits = by_company.get(ckey, []) if (has_company and ckey) else []

    # 会社一致集合の中でブランド名一致（最も確度が高い）
    brand_hit = None
    for hit in company_hits:
        for b in brands:
            if b and (b in hit["_name_norm"] or hit["_name_norm"] in b):
                brand_hit = hit
                break
        if brand_hit:
            break

    # 全案件からブランド名一致（会社名なしASP・表記揺れ対策）
    if not brand_hit and brands:
        for hit in rows:
            for b in brands:
                if len(b) >= 4 and b in hit["_name_norm"]:
                    brand_hit = hit
                    break
            if brand_hit:
                break

    if brand_hit:
        return "◎", brand_hit.get("program_name", "")
    if company_hits:
        return "○", company_hits[0].get("program_name", "")
    return "", ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--a8", default="csv/a8_programs.csv")
    parser.add_argument("--accesstrade", default="csv/accesstrade_programs.csv")
    parser.add_argument("--afb", default="csv/afb_programs.csv")
    parser.add_argument("--moshimo", default="csv/moshimo_programs.csv")
    parser.add_argument("--vc", default="csv/vc_raw_utf8.csv")
    parser.add_argument("--out", default="csv/asp_match.csv")
    args = parser.parse_args()

    with open(args.vc, encoding="utf-8") as f:
        vc_rows = list(csv.DictReader(f))

    # ASP定義: (キー, ファイルパス, 会社名の有無)
    asp_defs = [
        ("a8", args.a8, True),
        ("accesstrade", args.accesstrade, False),
        ("afb", args.afb, True),
        ("moshimo", args.moshimo, True),
    ]

    # 存在するASPのみ読み込む
    asp_data = {}
    for key, path, has_company in asp_defs:
        if os.path.exists(path):
            rows, by_company = load_asp(path, has_company=has_company)
            asp_data[key] = (rows, by_company, has_company)
            print(f"  {key}: {len(rows)}件 読み込み")

    fieldnames = ["プログラム名", "会社名", "広告主名"]
    for key in asp_data:
        fieldnames += [key, f"{key}_該当案件名"]

    out_rows = []
    counts = {key: {"◎": 0, "○": 0} for key in asp_data}
    for r in vc_rows:
        program = r.get("プログラム名", "").strip()
        company = r.get("会社名", "").strip()
        advertiser = r.get("広告主名", "").strip()
        ckey = normalize_company(company)
        brands = extract_brand(program, advertiser)

        row_out = {"プログラム名": program, "会社名": company, "広告主名": advertiser}
        for key, (rows, by_company, has_company) in asp_data.items():
            mark, matched = match_one(brands, ckey, rows, by_company, has_company)
            row_out[key] = mark
            row_out[f"{key}_該当案件名"] = matched
            if mark in counts[key]:
                counts[key][mark] += 1
        out_rows.append(row_out)

    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\nVC案件: {len(vc_rows)}件")
    for key in asp_data:
        c = counts[key]
        print(f"  {key}: ◎案件名一致 {c['◎']}件 / ○会社名のみ {c['○']}件 "
              f"（候補計 {c['◎'] + c['○']}件）")
    print(f"出力: {args.out}")


if __name__ == "__main__":
    main()
