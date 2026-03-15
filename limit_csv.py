#!/usr/bin/env python3
"""VC CSVから指定件数だけ抽出するユーティリティ"""
import csv
import sys

src = sys.argv[1]
limit = int(sys.argv[2])
out = sys.argv[3]

with open(src, encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

limited = rows[:limit]
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(limited)

print(f"制限: {len(limited)}/{len(rows)} 件を抽出")
