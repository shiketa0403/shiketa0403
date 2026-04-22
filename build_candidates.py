#!/usr/bin/env python3
"""
Step 3: Step 2 の jsonl を集計して、ドメインごとに link_count / first_seen /
last_seen / sample_anchor / sample_source_url を算出し、DNS 生死判定の上
候補 CSV を出力する。

- 入力 : ./links_data/links_*.jsonl
- 出力 : ./candidates.csv
- 列   : domain, link_count, first_seen, last_seen,
         sample_anchor, sample_source_url, is_alive
- ソート: is_alive=False 優先 & link_count 降順
"""

from __future__ import annotations

import argparse
import csv
import json
import socket
import sys
from collections import defaultdict
from pathlib import Path


# DNS 解決用タイムアウト (秒)
DNS_TIMEOUT = 5.0


def aggregate(links_dir: Path) -> dict[str, dict]:
    """jsonl を読み込み、ドメインごとに集計。"""
    agg: dict[str, dict] = defaultdict(lambda: {
        "link_count": 0,
        "first_seen": "",
        "last_seen": "",
        "sample_anchor": "",
        "sample_source_url": "",
        "years_set": set(),  # 登場した年の集合
        "anchor_candidates": [],  # あとで一番長いものを sample に
    })

    files = sorted(links_dir.glob("links_*.jsonl"))
    if not files:
        print(f"警告: {links_dir} に links_*.jsonl がありません", file=sys.stderr)
        return {}

    total_lines = 0
    for fp in files:
        print(f"  読込: {fp}")
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                domain = rec.get("external_domain", "").strip().lower()
                if not domain:
                    continue

                ts = rec.get("timestamp", "")
                anchor = (rec.get("anchor_text") or "").strip()
                src = rec.get("source_url", "")

                entry = agg[domain]
                entry["link_count"] += 1

                if not entry["first_seen"] or ts < entry["first_seen"]:
                    entry["first_seen"] = ts
                if not entry["last_seen"] or ts > entry["last_seen"]:
                    entry["last_seen"] = ts

                # timestamp の先頭4桁が年
                if len(ts) >= 4 and ts[:4].isdigit():
                    entry["years_set"].add(ts[:4])

                # 代表アンカー (空でないもの、かつ情報量があるもの)
                if anchor and len(anchor) > len(entry["sample_anchor"]):
                    if len(anchor) < 120:  # 長すぎるのは避ける
                        entry["sample_anchor"] = anchor

                if not entry["sample_source_url"]:
                    entry["sample_source_url"] = src

                total_lines += 1

    # years_set を years_seen 文字列に変換
    for info in agg.values():
        info["years_seen"] = ",".join(sorted(info.pop("years_set")))

    print(f"  総リンク数: {total_lines}, ユニークドメイン: {len(agg)}")
    return dict(agg)


def check_alive(domain: str) -> bool:
    """DNS で名前解決できれば True、引けなければ False。"""
    try:
        socket.setdefaulttimeout(DNS_TIMEOUT)
        socket.gethostbyname(domain)
        return True
    except Exception:
        return False
    finally:
        socket.setdefaulttimeout(None)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Step 3: ドメイン集計 + 生死判定 + CSV出力")
    p.add_argument("--source-domain", default=None,
                   help="ソースドメイン (results/{domain}/ を探す)")
    p.add_argument("--results-dir", type=Path, default=Path("./results"))
    p.add_argument("--links-dir", type=Path, default=None,
                   help="links_data ディレクトリ (未指定なら results-dir/{domain}/links_data)")
    p.add_argument("--output", type=Path, default=None,
                   help="candidates.csv 出力先 (未指定なら results-dir/{domain}/candidates.csv)")
    p.add_argument("--skip-dns", action="store_true", help="DNS チェックをスキップ (is_alive は全て空)")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.source_domain:
        import re as _re
        domain = _re.sub(r"^https?://", "", args.source_domain.strip()).rstrip("/")
        links_dir = args.links_dir or (args.results_dir / domain / "links_data")
        output = args.output or (args.results_dir / domain / "candidates.csv")
    else:
        if not args.links_dir or not args.output:
            print("エラー: --source-domain か --links-dir + --output を指定してください", file=sys.stderr)
            return 2
        links_dir = args.links_dir
        output = args.output

    # 以降の args 参照箇所のため上書きしておく
    args.links_dir = links_dir
    args.output = output

    print("=" * 60)
    print(f"入力ディレクトリ: {args.links_dir}")
    print(f"出力            : {args.output}")
    print(f"DNS チェック    : {'skip' if args.skip_dns else '実行'}")
    print("=" * 60)

    print("\n[1/3] jsonl を集計中...")
    agg = aggregate(args.links_dir)
    if not agg:
        print("集計対象がありませんでした")
        return 1

    print(f"\n[2/3] DNS 生死判定中 ({len(agg)} ドメイン)...")
    rows = []
    for i, (domain, info) in enumerate(sorted(agg.items()), start=1):
        if args.skip_dns:
            alive = ""
        else:
            alive = check_alive(domain)
            mark = "○" if alive else "×"
            if i % 20 == 0 or i == len(agg):
                print(f"  [{i}/{len(agg)}] {mark} {domain}")
        rows.append({
            "domain": domain,
            "link_count": info["link_count"],
            "years_seen": info.get("years_seen", ""),
            "first_seen": info["first_seen"],
            "last_seen": info["last_seen"],
            "sample_anchor": info["sample_anchor"],
            "sample_source_url": info["sample_source_url"],
            "is_alive": alive,
            "genre": "",  # 後から手動記入用 (空で出力)
            "memo": "",   # 自由記入欄
        })

    # ソート: is_alive=False を上、次に link_count 降順
    def sort_key(r):
        alive = r["is_alive"]
        # False(= 死亡=中古候補) を最優先
        alive_rank = 0 if alive is False else (1 if alive is True else 2)
        return (alive_rank, -r["link_count"], r["domain"])

    rows.sort(key=sort_key)

    print(f"\n[3/3] CSV 書き出し: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # 既存ファイルから genre / memo を引き継ぐ (手動記入を保持)
    existing_meta: dict[str, dict[str, str]] = {}
    if args.output.exists():
        try:
            with open(args.output, "r", encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    existing_meta[row.get("domain", "")] = {
                        "genre": row.get("genre", ""),
                        "memo": row.get("memo", ""),
                    }
        except Exception:
            pass

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "domain", "link_count", "years_seen", "first_seen", "last_seen",
            "sample_anchor", "sample_source_url", "is_alive", "genre", "memo",
        ])
        for r in rows:
            meta = existing_meta.get(r["domain"], {})
            genre = meta.get("genre") or r["genre"]
            memo = meta.get("memo") or r["memo"]
            writer.writerow([
                r["domain"], r["link_count"], r["years_seen"],
                r["first_seen"], r["last_seen"],
                r["sample_anchor"], r["sample_source_url"], r["is_alive"],
                genre, memo,
            ])

    dead = sum(1 for r in rows if r["is_alive"] is False)
    alive = sum(1 for r in rows if r["is_alive"] is True)

    print("\n" + "=" * 60)
    print("Step 3 完了")
    print(f"  総ドメイン  : {len(rows)}")
    if not args.skip_dns:
        print(f"  消滅(候補)  : {dead}")
        print(f"  生存        : {alive}")
    print(f"  出力        : {args.output}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
