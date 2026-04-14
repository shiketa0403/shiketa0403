#!/usr/bin/env python3
"""
Step 4: ドメイン取得可否を whois で一括チェックする。

入力: candidates.csv (デフォルト) もしくは --input で指定したドメインリスト
      is_alive=False (= DNS 引けない) のドメインのみを対象にする。

出力: availability.csv
      列: domain, link_count, availability, registrar, expiry, whois_excerpt,
         sample_anchor, sample_source_url

availability の値:
  - available  : 取得できそう (whois に登録情報なし)
  - taken      : 登録済み
  - unknown    : 判定不能 (whois エラー/タイムアウト等)
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import time
from pathlib import Path


SLEEP_BETWEEN_QUERIES = 3.0  # 秒 (.jp 系は whois レート制限が厳しい)
WHOIS_TIMEOUT = 30

# 取得可能を示すパターン (小文字比較)
AVAILABLE_PATTERNS = [
    "no match",
    "not found",
    "no data found",
    "no entries found",
    "no object found",
    "status: free",
    "status: available",
    "domain not found",
    "no matching record",
    "nothing found",
    "object does not exist",
    "% no entries",
    "% nothing",
    # JPRS (.jp)
    "no match!!",
    "上記ドメイン名は登録されていません",
]

# 登録済みを示す明示的パターン
REGISTERED_PATTERNS = [
    "registrar:",
    "registered:",
    "creation date:",
    "[登録年月日]",
    "[有効期限]",
    "a. [ドメイン名]",
    "domain name:",
]


def run_whois(domain: str) -> tuple[str, str]:
    """whois コマンドを実行。(stdout+stderr, error_note) を返す。"""
    try:
        p = subprocess.run(
            ["whois", domain],
            capture_output=True, text=True, timeout=WHOIS_TIMEOUT,
        )
        return (p.stdout or "") + "\n" + (p.stderr or ""), ""
    except subprocess.TimeoutExpired:
        return "", "timeout"
    except FileNotFoundError:
        return "", "whois コマンドが見つかりません"
    except Exception as e:
        return "", f"error: {e}"


def parse_whois(output: str) -> dict:
    """whois 出力をパースして取得可否を判定"""
    if not output.strip():
        return {"availability": "unknown", "registrar": "", "expiry": "", "excerpt": ""}

    lower = output.lower()

    # 取得可能パターン
    for p in AVAILABLE_PATTERNS:
        if p in lower:
            return {
                "availability": "available",
                "registrar": "",
                "expiry": "",
                "excerpt": _first_nonempty_line(output, "available"),
            }

    # 登録済みパターンがあるか
    is_registered = any(p in lower for p in REGISTERED_PATTERNS)

    registrar = _extract_field(output, [
        r"Registrar:\s*(.+)",
        r"Sponsoring Registrar:\s*(.+)",
        r"\[登録者名\]\s*(.+)",
        r"\[Registrant\]\s*(.+)",
    ])
    expiry = _extract_field(output, [
        r"Registry Expiry Date:\s*(\S+)",
        r"Registrar Registration Expiration Date:\s*(\S+)",
        r"Expiration Date:\s*(\S+)",
        r"Expir[a-z ]*Date:\s*(\S+)",
        r"paid-till:\s*(\S+)",
        r"\[有効期限\]\s*(\S+)",
        r"\[状態\]\s*(.+)",
    ])

    if is_registered or registrar or expiry:
        return {
            "availability": "taken",
            "registrar": registrar,
            "expiry": expiry,
            "excerpt": _first_nonempty_line(output, "registered"),
        }

    # どちらにも該当しない
    return {
        "availability": "unknown",
        "registrar": "",
        "expiry": "",
        "excerpt": _first_nonempty_line(output, "")[:200],
    }


def _extract_field(text: str, patterns: list[str]) -> str:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:100]
    return ""


def _first_nonempty_line(text: str, label: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("%") and not s.startswith("#"):
            return s[:200]
    return label


def load_candidates(csv_path: Path, only_dead: bool) -> list[dict]:
    rows = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if only_dead and row.get("is_alive", "").strip().lower() != "false":
                continue
            rows.append(row)
    return rows


def load_domain_list(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        rows.append({"domain": s, "link_count": "", "sample_anchor": "", "sample_source_url": ""})
    return rows


def is_valid_domain(d: str) -> bool:
    """明らかに無効なもの(IP, サブドメインっぽいもの等)を除外"""
    if not d:
        return False
    # IPv4
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", d):
        return False
    # ドメインらしさ
    if "." not in d:
        return False
    # 4つ以上のドット = サブドメインの可能性高い (www.foo.co.jp は3つ)
    if d.count(".") >= 4:
        return False
    return True


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ドメイン取得可否チェック")
    p.add_argument("--input", type=Path, default=Path("./candidates.csv"),
                   help="入力 CSV (candidates.csv) もしくは ドメインリスト .txt")
    p.add_argument("--output", type=Path, default=Path("./availability.csv"))
    p.add_argument("--include-alive", action="store_true",
                   help="is_alive=True のドメインもチェックする (デフォルト: Falseのみ)")
    p.add_argument("--include-subdomains", action="store_true",
                   help="サブドメインぽいもの/IPも含めてチェック")
    p.add_argument("--limit", type=int, default=0, help="処理上限 (0=無制限)")
    p.add_argument("--sleep", type=float, default=SLEEP_BETWEEN_QUERIES)
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if not args.input.exists():
        print(f"エラー: 入力ファイルが見つかりません: {args.input}", file=sys.stderr)
        return 2

    if args.input.suffix.lower() == ".csv":
        rows = load_candidates(args.input, only_dead=not args.include_alive)
    else:
        rows = load_domain_list(args.input)

    # ドメインの妥当性フィルタ
    if not args.include_subdomains:
        before = len(rows)
        rows = [r for r in rows if is_valid_domain(r.get("domain", ""))]
        print(f"サブドメイン/IP 除外: {before} → {len(rows)}")

    if args.limit > 0:
        rows = rows[: args.limit]

    print("=" * 60)
    print(f"入力        : {args.input}")
    print(f"出力        : {args.output}")
    print(f"対象        : {len(rows)} ドメイン")
    print(f"sleep       : {args.sleep}秒/回")
    print("=" * 60)

    # whois 動作確認
    check = subprocess.run(["which", "whois"], capture_output=True, text=True)
    if check.returncode != 0:
        print("エラー: whois コマンドがインストールされていません", file=sys.stderr)
        print("       Ubuntu なら: sudo apt-get install -y whois", file=sys.stderr)
        return 3

    fieldnames = [
        "domain", "availability", "registrar", "expiry",
        "link_count", "sample_anchor", "sample_source_url", "whois_excerpt",
    ]

    results: list[dict] = []
    counts = {"available": 0, "taken": 0, "unknown": 0}

    for i, row in enumerate(rows, start=1):
        domain = row["domain"].strip().lower()
        print(f"[{i}/{len(rows)}] {domain}", end=" ")

        output, err = run_whois(domain)
        if err:
            parsed = {"availability": "unknown", "registrar": "", "expiry": "", "excerpt": err}
        else:
            parsed = parse_whois(output)

        counts[parsed["availability"]] = counts.get(parsed["availability"], 0) + 1
        mark = {"available": "⭕ 取得可", "taken": "❌ 登録済", "unknown": "❓ 不明"}[parsed["availability"]]
        print(f"→ {mark}")

        results.append({
            "domain": domain,
            "availability": parsed["availability"],
            "registrar": parsed["registrar"],
            "expiry": parsed["expiry"],
            "link_count": row.get("link_count", ""),
            "sample_anchor": row.get("sample_anchor", ""),
            "sample_source_url": row.get("sample_source_url", ""),
            "whois_excerpt": parsed["excerpt"],
        })

        # 途中保存
        if i % 10 == 0 or i == len(rows):
            _write_csv(results, args.output, fieldnames)

        if i < len(rows):
            time.sleep(args.sleep)

    # ソート: available を上、link_count 降順
    def sort_key(r):
        a_rank = {"available": 0, "unknown": 1, "taken": 2}.get(r["availability"], 3)
        try:
            lc = -int(r.get("link_count") or 0)
        except ValueError:
            lc = 0
        return (a_rank, lc, r["domain"])

    results.sort(key=sort_key)
    _write_csv(results, args.output, fieldnames)

    print("\n" + "=" * 60)
    print(f"完了: {len(results)} ドメイン")
    print(f"  ⭕ 取得可能 : {counts.get('available', 0)}")
    print(f"  ❌ 登録済み : {counts.get('taken', 0)}")
    print(f"  ❓ 判定不能 : {counts.get('unknown', 0)}")
    print(f"  出力        : {args.output}")
    print("=" * 60)
    return 0


def _write_csv(rows: list[dict], path: Path, fieldnames: list[str]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


if __name__ == "__main__":
    sys.exit(main())
