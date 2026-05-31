#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dropcatch_jp.py — Value Domain API 経由で .jp ドメインをドロップキャッチする。

【重要】このスクリプトは「あなたのローカルPC / 常時起動のVPS」で実行してください。
Claude Code の実行環境（クラウドサンドボックス）は egress プロキシで
api.value-domain.com をブロックしているため、そこからは登録できません。

仕組み:
  1. 指定時刻まで待機（任意）
  2. whois.jprs.jp を定期照会してドメインが「空き」になったか監視（ログ用）
  3. Value Domain の登録API (POST /v1/domains) を短間隔でリトライ送信
     - まだ取得されている間は registry がエラーを返す → 即リトライ
     - 空いた瞬間に成功すれば登録確定（課金発生）→ 終了
  4. 締切時刻 or 成功で停止

設定はすべて環境変数で渡す（下の CONFIG 参照）。

事前テスト（必ず 0:00 前にやる）:
  python3 dropcatch_jp.py --preflight
    → APIキーの疎通確認（GET /v1/domains で自分の保有ドメイン一覧を取得）
       と設定内容の表示のみ。登録はしない。

本番:
  python3 dropcatch_jp.py
"""

import os
import sys
import json
import time
import socket
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
API_BASE = "https://api.value-domain.com/v1"
WHOIS_HOST = "whois.jprs.jp"


# ---------------------------------------------------------------------------
# 設定（環境変数）
# ---------------------------------------------------------------------------
def load_config():
    def req(name):
        v = os.environ.get(name, "").strip()
        if not v:
            sys.exit(f"[FATAL] 環境変数 {name} が未設定です。")
        return v

    api_key = req("VD_API_KEY")  # Value Domain の API キー（Bearer）

    domain = req("VD_DOMAIN").lower().strip(".")  # 例: example.jp
    if "." not in domain:
        sys.exit("[FATAL] VD_DOMAIN は example.jp の形式で指定してください。")
    sld, tld = domain.split(".", 1)

    # 取得年数
    years = int(os.environ.get("VD_YEARS", "1"))

    # ネームサーバ（カンマ区切り。未指定ならValue Domain標準）
    ns_env = os.environ.get("VD_NS", "").strip()
    if ns_env:
        ns = [n.strip() for n in ns_env.split(",") if n.strip()]
    else:
        ns = [
            "ns1.value-domain.com",
            "ns2.value-domain.com",
            "ns3.value-domain.com",
            "ns4.value-domain.com",
            "ns5.value-domain.com",
        ]

    # .jp はレジストリが要求するのは registrant のみ。
    registrant = {
        "firstname": req("VD_FIRSTNAME"),
        "lastname": req("VD_LASTNAME"),
        "organization": os.environ.get("VD_ORG", "personal"),
        "country": os.environ.get("VD_COUNTRY", "JP"),
        "postalcode": req("VD_POSTALCODE"),   # 例: 530-0011
        "state": req("VD_STATE"),             # 例: Osaka / Tokyo
        "city": req("VD_CITY"),               # 例: Osaka-shi Kita-ku
        "address1": req("VD_ADDRESS1"),
        "address2": os.environ.get("VD_ADDRESS2", ""),
        "email": req("VD_EMAIL"),
        "phone": req("VD_PHONE"),             # 例: +81.676342727
        "fax": os.environ.get("VD_FAX", req("VD_PHONE")),
    }

    payload = {
        "registrar": os.environ.get("VD_REGISTRAR", "GMO"),
        "sld": sld,
        "tld": tld,
        "years": years,
        "ns": ns,
        "whois_proxy": int(os.environ.get("VD_WHOIS_PROXY", "1")),  # 1=Whois代理公開
        "contact": {
            "registrant": registrant,
            "admin": registrant,
            "tech": registrant,
        },
    }

    cfg = {
        "api_key": api_key,
        "domain": domain,
        "payload": payload,
        # タイミング
        "start_at": os.environ.get("VD_START_AT", "").strip(),  # JST ISO 例:2026-06-01T00:00:00
        "deadline_sec": int(os.environ.get("VD_DEADLINE_SEC", "1800")),  # 開始後この秒数で諦める
        "reg_interval": float(os.environ.get("VD_REG_INTERVAL", "2.0")),  # 登録リトライ間隔
        "whois_every": int(os.environ.get("VD_WHOIS_EVERY", "5")),  # 何回に1回whoisログ
    }
    return cfg


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------
def now_jst():
    return datetime.now(JST)


def log(msg):
    print(f"[{now_jst().strftime('%H:%M:%S.%f')[:-3]} JST] {msg}", flush=True)


def whois_jp(domain, timeout=8):
    """whois.jprs.jp に問い合わせ。'AVAILABLE' / 'REGISTERED' / 'UNKNOWN' を返す。"""
    try:
        with socket.create_connection((WHOIS_HOST, 43), timeout=timeout) as s:
            s.sendall((domain + "/e\r\n").encode("ascii", "ignore"))
            chunks = []
            s.settimeout(timeout)
            while True:
                try:
                    data = s.recv(4096)
                except socket.timeout:
                    break
                if not data:
                    break
                chunks.append(data)
        text = b"".join(chunks).decode("utf-8", "ignore")
    except Exception as e:
        return "UNKNOWN", f"whois error: {e}"

    low = text.lower()
    if "no match" in low or "not found" in low:
        return "AVAILABLE", text.strip()[:200]
    if "[status]" in low or "[domain name]" in low or "[登録年月日]" in text:
        return "REGISTERED", None
    return "UNKNOWN", text.strip()[:200]


def vd_request(method, path, api_key, body=None, timeout=20):
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")
    except Exception as e:
        return None, f"request error: {e}"


# ---------------------------------------------------------------------------
# プリフライト
# ---------------------------------------------------------------------------
def preflight(cfg):
    log("=== PREFLIGHT（登録はしません）===")
    log(f"対象ドメイン: {cfg['domain']}")
    safe = json.loads(json.dumps(cfg["payload"]))
    log("送信予定ペイロード:\n" + json.dumps(safe, ensure_ascii=False, indent=2))

    log("APIキー疎通確認 GET /domains ...")
    status, text = vd_request("GET", "/domains?limit=1", cfg["api_key"])
    if status == 200:
        log("OK: APIキーは有効です。")
    elif status == 401:
        log("NG: 401 認証失敗。APIキーを確認してください。")
    else:
        log(f"応答: HTTP {status}: {text[:300]}")

    state, info = whois_jp(cfg["domain"])
    log(f"現在のwhois状態: {state}" + (f"  ({info})" if info else ""))
    log("=== PREFLIGHT 完了 ===")


# ---------------------------------------------------------------------------
# 本番
# ---------------------------------------------------------------------------
def wait_until_start(cfg):
    s = cfg["start_at"]
    if not s:
        return
    try:
        target = datetime.fromisoformat(s).replace(tzinfo=JST)
    except ValueError:
        sys.exit(f"[FATAL] VD_START_AT の形式が不正: {s} (例: 2026-06-01T00:00:00)")
    log(f"開始予定時刻まで待機: {target.isoformat()}")
    while now_jst() < target:
        remain = (target - now_jst()).total_seconds()
        if remain > 5:
            time.sleep(min(remain - 2, 30))
        else:
            time.sleep(0.2)
    log("開始時刻に到達。")


def run(cfg):
    wait_until_start(cfg)
    deadline = now_jst() + timedelta(seconds=cfg["deadline_sec"])
    log(f"ドロップキャッチ開始。締切: {deadline.strftime('%H:%M:%S')} JST")
    log("登録APIを短間隔で再試行します（空いた瞬間に成功 → 終了）。")

    attempt = 0
    while now_jst() < deadline:
        attempt += 1

        if attempt % cfg["whois_every"] == 1:
            state, info = whois_jp(cfg["domain"])
            log(f"[#{attempt}] whois={state}")

        status, text = vd_request("POST", "/domains", cfg["api_key"], cfg["payload"])

        if status in (200, 201):
            log("🎉 取得成功！ レスポンス:")
            log(text)
            log(f"=== {cfg['domain']} を取得しました。Value Domainの管理画面で確認してください。 ===")
            return 0

        # まだ取れない（取得済み等）→ 簡潔にログして即リトライ
        snippet = (text or "").replace("\n", " ")[:160]
        log(f"[#{attempt}] HTTP {status}: {snippet}")

        if status == 401:
            log("認証失敗(401)。APIキーが無効です。中止します。")
            return 2

        time.sleep(cfg["reg_interval"])

    log("締切に到達。取得できませんでした。")
    return 1


def main():
    ap = argparse.ArgumentParser(description=".jp ドロップキャッチ (Value Domain API)")
    ap.add_argument("--preflight", action="store_true", help="疎通確認と設定表示のみ（登録しない）")
    args = ap.parse_args()

    cfg = load_config()
    if args.preflight:
        preflight(cfg)
        return 0
    return run(cfg)


if __name__ == "__main__":
    sys.exit(main())
