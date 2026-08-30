"""Playwright起動の共通ヘルパー。

通常は playwright 標準のChromiumを使う。標準ブラウザが未ダウンロードの環境
（クラウドコンテナ等）では、既知のパスや CHROMIUM_PATH 環境変数から
実行ファイルを探して executable_path 起動にフォールバックする。
"""

from __future__ import annotations

import os
from pathlib import Path

FALLBACK_PATHS = [
    os.environ.get("CHROMIUM_PATH", ""),
    "/opt/pw-browsers/chromium",
]


def launch_chromium(p, **kwargs):
    """p: sync_playwright() のインスタンス。失敗時はフォールバックパスで再試行。"""
    try:
        return p.chromium.launch(headless=True, **kwargs)
    except Exception as first_error:
        for path in FALLBACK_PATHS:
            if path and Path(path).exists():
                return p.chromium.launch(headless=True, executable_path=path, **kwargs)
        raise RuntimeError(
            "Chromiumが見つかりません。次を実行してください:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        ) from first_error
