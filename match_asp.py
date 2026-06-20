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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--a8", default="csv/a8_programs.csv")
    parser.add_argument("--vc", default="csv/vc_raw_utf8.csv")
    parser.add_argument("--out", default="csv/asp_match.csv")
    args = parser.parse_args()

    with open(args.vc, encoding="utf-8") as f:
        vc_rows = list(csv.DictReader(f))

    a8_rows, a8_by_company = load_a8(args.a8)

    out_rows = []
    n_brand = 0
    n_company = 0
    for r in vc_rows:
        program = r.get("プログラム名", "").strip()
        company = r.get("会社名", "").strip()
        advertiser = r.get("広告主名", "").strip()
        ckey = normalize_company(company)
        brands = extract_brand(program, advertiser)

        a8_mark = ""
        a8_matched_name = ""

        company_hits = a8_by_company.get(ckey, []) if ckey else []

        # まず会社一致集合の中でブランド名一致を探す（最も確度が高い）
        brand_hit = None
        for hit in company_hits:
            for b in brands:
                if b and (b in hit["_name_norm"] or hit["_name_norm"] in b):
                    brand_hit = hit
                    break
            if brand_hit:
                break

        # 会社一致がなくても、全A8案件からブランド名一致を探す（会社名表記揺れ対策）
        if not brand_hit and brands:
            for hit in a8_rows:
                for b in brands:
                    if len(b) >= 4 and b in hit["_name_norm"]:
                        brand_hit = hit
                        break
                if brand_hit:
                    break

        if brand_hit:
            a8_mark = "◎"
            a8_matched_name = brand_hit.get("program_name", "")
            n_brand += 1
        elif company_hits:
            a8_mark = "○"
            a8_matched_name = company_hits[0].get("program_name", "")
            n_company += 1

        out_rows.append({
            "プログラム名": program,
            "会社名": company,
            "広告主名": advertiser,
            "a8": a8_mark,
            "a8_該当案件名": a8_matched_name,
        })

    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["プログラム名", "会社名", "広告主名", "a8", "a8_該当案件名"])
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"VC案件: {len(vc_rows)}件 / A8案件: {len(a8_rows)}件")
    print(f"◎ 案件名一致（確度高）: {n_brand}件")
    print(f"○ 会社名のみ一致（要確認）: {n_company}件")
    print(f"合計 A8取り扱い候補: {n_brand + n_company}件")
    print(f"出力: {args.out}")


if __name__ == "__main__":
    main()
