#!/usr/bin/env python3
"""
バックオーダー候補ドメインの whois 一括チェック。

入力CSVの1列目のドメインに対して whois を実行し、登録者名が記載されている
（= まだ登録中）ドメインの行を CSV から削除する。
出力は Excel for Windows でも文字化けしないよう BOM 付き UTF-8 で保存。
"""

import argparse
import csv
import re
import subprocess
import sys
import time
from pathlib import Path

REGISTRANT_PATTERNS = [
    re.compile(r'\[登録者名\][ \t]+(\S.*)'),
    re.compile(r'\[Registrant\][ \t]+(\S.*)'),
    re.compile(r'^Registrant\s*Name[ \t]*:[ \t]*(\S.*)', re.MULTILINE),
    re.compile(r'^Registrant[ \t]*:[ \t]*(\S.*)', re.MULTILINE),
]

NO_MATCH_MARKERS = ('No match!!', 'No match for', 'NOT FOUND', 'no match')


def read_csv_auto(path):
    raw = Path(path).read_bytes()
    for enc in ('utf-8-sig', 'utf-8', 'cp932'):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f'エンコード判定失敗: {path}')


def fetch_whois(domain, timeout=30):
    try:
        result = subprocess.run(
            ['whois', domain],
            capture_output=True, timeout=timeout, check=False,
        )
        return result.stdout.decode('utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        print(f'  whois例外 ({domain}): {e}', file=sys.stderr)
        return None


def fetch_whois_with_retry(domain, max_retries, base_sleep):
    for attempt in range(max_retries):
        out = fetch_whois(domain)
        if out and out.strip():
            return out
        if attempt < max_retries - 1:
            wait = base_sleep * (2 ** attempt)
            print(f'  リトライ {attempt + 1}/{max_retries - 1} ({domain}) {wait}秒待機', file=sys.stderr)
            time.sleep(wait)
    return None


def has_registrant(whois_text):
    """登録者名フィールドに値があれば True（=削除対象）。
    取得失敗時は None を返す（= 保持して手動確認）。
    """
    if not whois_text:
        return None
    if any(m in whois_text for m in NO_MATCH_MARKERS):
        return False
    for pat in REGISTRANT_PATTERNS:
        m = pat.search(whois_text)
        if m and m.group(1).strip():
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default='csv/backorder.csv')
    ap.add_argument('--sleep', type=float, default=3.0)
    ap.add_argument('--retries', type=int, default=3)
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f'エラー: {csv_path} が見つかりません', file=sys.stderr)
        sys.exit(1)

    text, enc = read_csv_auto(csv_path)
    print(f'入力: {csv_path} (encoding={enc})')

    rows = list(csv.reader(text.splitlines()))
    if not rows:
        print('CSV が空です', file=sys.stderr)
        sys.exit(1)

    header = rows[0]
    data_rows = rows[1:]
    print(f'ヘッダ: {header}')
    print(f'データ行数: {len(data_rows)}')
    print(f'設定: sleep={args.sleep}秒, retries={args.retries}')
    print('=' * 60)

    kept = [header]
    removed = 0
    failed = []

    for i, row in enumerate(data_rows, start=1):
        if not row or not row[0].strip():
            continue
        domain = row[0].strip()

        whois_text = fetch_whois_with_retry(domain, args.retries, args.sleep)
        verdict = has_registrant(whois_text)

        if verdict is True:
            removed += 1
            status = '削除'
        elif verdict is False:
            kept.append(row)
            status = '保持'
        else:
            kept.append(row)
            failed.append(domain)
            status = '保持(失敗)'

        if i % 25 == 0 or i == len(data_rows):
            print(f'[{i}/{len(data_rows)}] {domain} → {status} | '
                  f'保持={len(kept) - 1} 削除={removed} 失敗={len(failed)}')

        time.sleep(args.sleep)

    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(kept)

    print('=' * 60)
    print('完了')
    print(f'  入力件数: {len(data_rows)}')
    print(f'  保持件数: {len(kept) - 1}')
    print(f'  削除件数: {removed}')
    print(f'  whois取得失敗: {len(failed)} (保持扱い)')
    if failed:
        sample = ', '.join(failed[:20])
        suffix = '...' if len(failed) > 20 else ''
        print(f'  失敗ドメイン: {sample}{suffix}')


if __name__ == '__main__':
    main()
