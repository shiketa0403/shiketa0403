"""スカパーCSチャンネル一覧の読み取り。

ローカルCSVがあればそれを優先。なければ公開URLから取得（要ネット接続）。
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Iterable

from . import config


@dataclass
class Channel:
    no: int
    name: str            # チャンネル名
    formal_name: str     # 正式名称
    genre: str           # ジャンル
    monthly_fee: int     # 月額視聴料（税込・円）
    in_basic: bool       # 基本プラン対応
    in_select: bool      # セレクト5/10対応
    main_kw: str         # メインKW
    sub_kw: str          # サブKW
    slug: str            # URLスラッグ
    priority: str        # 優先度
    status: str          # ステータス
    note: str            # 備考

    @property
    def target_keyword(self) -> str:
        """プロンプト1の TARGET_KEYWORD（メインKW + サブKW）。"""
        return f"{self.main_kw} / {self.sub_kw}"


def _parse_row(row: dict) -> Channel:
    def _bool(v: str) -> bool:
        return v.strip() in ("○", "〇", "o", "O", "yes", "true", "True")

    def _int(v: str) -> int:
        v = (v or "").strip().replace(",", "")
        return int(v) if v.isdigit() else 0

    return Channel(
        no=_int(row.get("No", "0")),
        name=row.get("チャンネル名", "").strip(),
        formal_name=row.get("正式名称", "").strip(),
        genre=row.get("ジャンル", "").strip(),
        monthly_fee=_int(row.get("月額視聴料（税込）", "")),
        in_basic=_bool(row.get("基本プラン", "")),
        in_select=_bool(row.get("セレクト5/10対応", "")),
        main_kw=row.get("メインKW", "").strip(),
        sub_kw=row.get("サブKW", "").strip(),
        slug=row.get("URLスラッグ案", "").strip(),
        priority=row.get("優先度", "").strip(),
        status=row.get("ステータス", "").strip(),
        note=row.get("備考", "").strip(),
    )


def load_local() -> list[Channel]:
    """ローカルCSVを読む。"""
    with open(config.CHANNELS_CSV, encoding="utf-8") as f:
        return [_parse_row(r) for r in csv.DictReader(f)]


def load_remote() -> list[Channel]:
    """公開CSV URLから取得する（要 requests）。"""
    import requests  # 遅延import

    resp = requests.get(config.SHEET_PUBLISHED_CSV_URL, timeout=30)
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig")  # BOM対策
    return [_parse_row(r) for r in csv.DictReader(io.StringIO(text))]


def load(prefer_remote: bool = False) -> list[Channel]:
    """通常はローカル優先。prefer_remote=Trueで公開URLを取りに行く。"""
    if prefer_remote:
        try:
            return load_remote()
        except Exception:
            pass
    return load_local()


def find(channels: Iterable[Channel], query: str) -> Channel | None:
    """チャンネル名・正式名称・スラッグ・No のいずれかに一致するチャンネルを返す。"""
    q = query.strip().lower()
    for ch in channels:
        if q in (str(ch.no), ch.slug.lower(), ch.name.lower(), ch.formal_name.lower()):
            return ch
        # 部分一致（名前）
    for ch in channels:
        if q in ch.name.lower() or q in ch.formal_name.lower():
            return ch
    return None
