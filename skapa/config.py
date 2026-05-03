"""skyperfectv.heteml.net 向け記事生成の固定設定。"""

from __future__ import annotations

import os
from pathlib import Path

# プロジェクトルート
ROOT_DIR = Path(__file__).resolve().parent.parent

# .env があれば読み込む（python-dotenv が無くても動くようフォールバック実装）
_ENV_PATH = ROOT_DIR / ".env"
if _ENV_PATH.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(_ENV_PATH)
    except ImportError:
        # dotenv未インストール時は手動でパース
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)

# プロンプト・データソース
PROMPTS_DIR = ROOT_DIR / "prompts"
CHANNELS_CSV = ROOT_DIR / "csv" / "skapa_channels.csv"
DRAFTS_DIR = ROOT_DIR / "skapa" / "drafts"
KNOWLEDGE_DIR = ROOT_DIR / "skapa" / "knowledge"
INDUSTRY_NOTES_PATH = KNOWLEDGE_DIR / "industry_notes.md"

# スプレッドシート公開CSV URL（GitHub Actionsからはこちらを使う）
SHEET_PUBLISHED_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRS4TVNF-oGRSu48OAGnNH9y4eg46uD2Z9DX9PKYpeynFMOcNMUHj42nQVL52GPiMnKXEStPdu3f6h1"
    "/pub?gid=1652119618&single=true&output=csv"
)

# プロンプト1で渡すメディア情報（固定）
MEDIA_INFO = "スカパーCSチャンネルを紹介するアフィリエイトメディア"

# Claude API
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-opus-4-7"
MAX_TOKENS = 16000  # 本文生成の長文出力に対応

# WordPress 投稿先
WP_SITE_URL = "https://skyperfectv.heteml.net"
WP_API_ENDPOINT = f"{WP_SITE_URL}/wp-json/wp/v2"
WP_USERNAME = os.environ.get("SKYPERFECT_WP_USERNAME", "")
WP_APP_PASSWORD = os.environ.get("SKYPERFECT_WP_APP_PASSWORD", "")
WP_POST_STATUS = "draft"  # 下書きで停止

# 工程ファイル名
STEP_FILENAMES = {
    1: "01_persona.md",
    2: "02_structure.md",
    3: "03_structure_audit.md",
    4: "04_body.md",
    5: "05_body_audit.html",
    6: "06_decoration.html",
    7: "07_links.html",
    8: "08_final.html",
}

PROMPT_FILES = {
    1: "01_persona.md",
    2: "02_structure.md",
    3: "03_structure_audit.md",
    4: "04_body.md",
    5: "05_body_audit.md",
    6: "06_decoration.md",
    7: "07_links.md",
    8: "08_lead.md",
}


def channel_draft_dir(slug: str) -> Path:
    """指定スラッグの工程キャッシュディレクトリを返す（存在しなければ作成）。"""
    d = DRAFTS_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    return d
