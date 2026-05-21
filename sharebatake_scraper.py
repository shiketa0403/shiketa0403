#!/usr/bin/env python3
"""
シェア畑（sharebatake.com）スクレイパー（区/市単位）

区/市名を受け取り、対応する一覧ページから農園URLを集め、
各農園詳細ページを Playwright で取得して構造化データに変換する。

呼び出し例:
  from sharebatake_scraper import scrape_area
  farms = scrape_area("大田区", out_dir=Path("out"))
  farms = scrape_area("横浜市", out_dir=Path("out"))

入力: 区/市名（例: 大田区、横浜市）
出力: Farm dataclass のリスト + ローカルに保存した各農園のフルスクショ画像
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin, urlparse

BASE_URL = "https://www.sharebatake.com/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# 区/市名 → (都道府県slug, シェア畑側slug, WP slug, 住所フィルタ)
# 住所フィルタが None の場合はページ内の全農園を対象
# 住所フィルタがある場合はその文字列を住所に含む農園のみ対象
AREA_MAP = {
    # ==== 東京都 ====
    # 23区（シェア畑に農園があるもの）
    "大田区":   ("tokyo", "oota",       "ota",        None),
    "世田谷区": ("tokyo", "setagaya",   "setagaya",   None),
    "杉並区":   ("tokyo", "suginami",   "suginami",   None),
    "渋谷区":   ("tokyo", "shibuya",    "shibuya",    None),
    "練馬区":   ("tokyo", "nerima",     "nerima",     None),
    "目黒区":   ("tokyo", "meguro",     "meguro",     None),
    "江東区":   ("tokyo", "koto",       "koto",       None),
    "葛飾区":   ("tokyo", "katsushika", "katsushika", None),
    "板橋区":   ("tokyo", "itabashi",   "itabashi",   None),
    "江戸川区": ("tokyo", "edogawa",    "edogawa",    None),
    "足立区":   ("tokyo", "adachi",     "adachi",     None),
    # 調布市・狛江市は同じページから住所で分離
    "調布市":   ("tokyo", "chofu",      "chofu",      "調布市"),
    "狛江市":   ("tokyo", "chofu",      "komae",      "狛江市"),
    # その他の東京市部（tokyo_else ページから住所で分離）
    "八王子市":   ("tokyo", "tokyo_else", "hachioji",        "八王子市"),
    "町田市":     ("tokyo", "tokyo_else", "machida",         "町田市"),
    "三鷹市":     ("tokyo", "tokyo_else", "mitaka",          "三鷹市"),
    "武蔵野市":   ("tokyo", "tokyo_else", "musashino",       "武蔵野市"),
    "立川市":     ("tokyo", "tokyo_else", "tachikawa",       "立川市"),
    "府中市":     ("tokyo", "tokyo_else", "fuchu",           "府中市"),
    "国分寺市":   ("tokyo", "tokyo_else", "kokubunji",       "国分寺市"),
    "小金井市":   ("tokyo", "tokyo_else", "koganei",         "小金井市"),
    "小平市":     ("tokyo", "tokyo_else", "kodaira",         "小平市"),
    "東村山市":   ("tokyo", "tokyo_else", "higashimurayama", "東村山市"),
    "国立市":     ("tokyo", "tokyo_else", "kunitachi",       "国立市"),
    "西東京市":   ("tokyo", "tokyo_else", "nishitokyo",      "西東京市"),
    "東久留米市": ("tokyo", "tokyo_else", "higashikurume",   "東久留米市"),

    # ==== 神奈川県 ====
    # 各市は専用ページがあると仮定（dry_run で要確認。0件ならフォールバック調整）
    "横浜市":   ("kanagawa", "yokohama", "yokohama", None),
    "川崎市":   ("kanagawa", "kawasaki", "kawasaki", None),
    "藤沢市":   ("kanagawa", "fujisawa", "fujisawa", None),

    # ==== 千葉県 ====
    # 千葉市は政令指定都市（6区）。市全体で1ページにまとまっている想定。
    "千葉市":   ("chiba", "chiba", "chiba", None),

    # ==== 埼玉県 ====
    # さいたま市は政令指定都市（10区）。市全体で1ページにまとまっている。
    "さいたま市": ("saitama", "saitama", "saitama", None),
    # その他の埼玉市部（saitama_else ページから住所で分離）
    "川口市":     ("saitama", "saitama_else", "kawaguchi", "川口市"),
    "朝霞市":     ("saitama", "saitama_else", "asaka",     "朝霞市"),

    # ==== 大阪府 ====
    # 大阪は /farms/osaka 単一ページに全農園が並ぶ構造（sb_slug は空文字）。
    # 市単位で記事化する場合は住所フィルタで分離する。
    "吹田市":   ("osaka", "", "suita", "吹田市"),
    # 大阪市の住吉区。「住吉区」だと「東住吉区」も巻き込むので「大阪市住吉区」で厳密化
    "住吉区":   ("osaka", "", "sumiyoshi", "大阪市住吉区"),
    "箕面市":   ("osaka", "", "minoh", "箕面市"),

    # ==== 兵庫県 ====
    # 大阪と同じく /farms/hyogo 単一ページ構造（sb_slug は空文字）。
    "尼崎市":   ("hyogo", "", "amagasaki", "尼崎市"),
    "西宮市":   ("hyogo", "", "nishinomiya", "西宮市"),
}

# 旧APIとの後方互換（外部から参照されているため残す）
TOKYO_AREA_MAP = {
    k: (sb, wp, addr)
    for k, (pref, sb, wp, addr) in AREA_MAP.items()
    if pref == "tokyo"
}

# 都道府県slug → WPカテゴリ名（agriwarriors.jp 側に同名カテゴリが必要）
PREFECTURE_CATEGORY = {
    "tokyo":    "東京",
    "kanagawa": "神奈川",
    "chiba":    "千葉",
    "saitama":  "埼玉",
    "osaka":    "大阪",
    "hyogo":    "兵庫",
}

# 状態タグ（アイコンファイル名 → 表示名）
STATUS_ICONS = {
    "farm_ac": "アクセス良好",
    "farm_st": "駅から近い",
    "farm_ar": "人気エリア",
    "farm_big": "大型農園",
    "farm_parking": "駐車場あり",
}


@dataclass
class Farm:
    name: str
    detail_url: str
    address: str = ""
    access: str = ""
    fee: str = ""
    entry_fee: str = ""
    included_services: str = ""
    facilities: str = ""
    status_tags: List[str] = field(default_factory=list)
    is_garden: bool = False
    catch_phrase: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    screenshot_path: str = ""
    screenshot_wp_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def lookup_area(city_name: str):
    """区/市名 → (pref_slug, sharebatake_slug, wp_slug, addr_filter)"""
    if city_name not in AREA_MAP:
        raise ValueError(
            f"未対応の市区町村: {city_name}\n"
            f"対応している区/市: {', '.join(AREA_MAP.keys())}"
        )
    return AREA_MAP[city_name]


def build_area_url(pref_slug: str, sb_slug: str) -> str:
    # sb_slug が空文字の場合は都道府県トップページ（例: /farms/osaka）。
    # 大阪のように都道府県内の市区分割が無いケースで使う。
    if sb_slug:
        return urljoin(BASE_URL, f"/farms/{pref_slug}/{sb_slug}")
    return urljoin(BASE_URL, f"/farms/{pref_slug}")


def _fetch(page, url: str, wait_ms: int = 2500) -> str:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass
    page.wait_for_timeout(wait_ms)
    # 遅延読み込み対策
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(800)
    except Exception:
        pass
    return page.content()


def _parse_list_page(html: str, area_url: str, addr_filter: Optional[str]):
    """一覧ページから (農園詳細URL, 一覧上の補助情報) のタプル列を返す。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results = []

    for item in soup.select(".farmlist_item"):
        # 詳細URL:
        #   - 現行構造: item 自体が <a class="farmlist_item" href="...">
        #   - 旧構造:   item は <div> で、内側に <a class="...detailbutton..." or a[href*='/farms/']>
        href = ""
        if item.name == "a" and item.get("href"):
            href = item.get("href", "")
        else:
            detail_btn = item.select_one(".farmlist_item_header_detailbutton a, a[href*='/farms/']")
            if detail_btn:
                href = detail_btn.get("href", "")
        if not href:
            continue
        detail_url = urljoin(area_url, href)
        # 同一階層の /farms/ かつ末尾に農園slugがあるものに限定
        path = urlparse(detail_url).path
        if not re.match(r"^/farms/[^/]+/[^/]+/[^/]+/?$", path):
            continue

        # 一覧の住所（フィルタ用）
        addr_el = item.find(string=re.compile(r"住所")) or None
        list_address = ""
        for tr in item.find_all("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if th and td and "住所" in th.get_text(strip=True):
                list_address = td.get_text(" ", strip=True)
                break
        # 別構造 (div ベース) の場合
        if not list_address:
            for td_label, td_value in zip(
                item.select(".tdL, .farmlist_item_address_label"),
                item.select(".tdR, .farmlist_item_address_value"),
            ):
                if "住所" in td_label.get_text(" ", strip=True):
                    list_address = td_value.get_text(" ", strip=True)
                    break

        # 住所フィルタで絞り込み
        if addr_filter and addr_filter not in list_address:
            continue

        # 補助情報
        name_el = item.select_one(".farmlist_item_farmname, h2")
        name_hint = name_el.get_text(" ", strip=True) if name_el else ""
        is_garden = bool(item.find(string=re.compile(r"シェア畑 ?garden", re.IGNORECASE)))
        catch = ""
        # キャッチコピーらしき短文（テーブルの外、農園名の近く）
        for p in item.find_all(["p", "div"]):
            t = p.get_text(" ", strip=True)
            if 6 <= len(t) <= 60 and "詳細" not in t and "住所" not in t and "アクセス" not in t:
                if t != name_hint:
                    catch = t
                    break

        # 状態タグ（アイコンの src から判別）
        tags = []
        for img in item.find_all("img"):
            src = img.get("src", "")
            for key, label in STATUS_ICONS.items():
                if key in src and label not in tags:
                    tags.append(label)

        results.append({
            "detail_url": detail_url,
            "name_hint": name_hint,
            "is_garden": is_garden,
            "catch_phrase": catch,
            "status_tags": tags,
            "list_address": list_address,
        })
    return results


def _parse_detail_page(html: str, url: str, hint: dict) -> Farm:
    """詳細ページから構造化情報を抽出して Farm を返す。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # 名前は h1 か hint
    name = hint.get("name_hint") or ""
    if not name:
        h1 = soup.find("h1")
        if h1:
            t = h1.get_text(" ", strip=True)
            # 「シェア畑 ◯◯ | …」のような形を切る
            name = re.split(r"[\|｜]", t)[0].strip()
    # 名前の余計な接頭辞を整える（"シェア畑 garden " → 既にバッジ管理しているので残してOK）

    farm = Farm(
        name=name,
        detail_url=url,
        is_garden=hint.get("is_garden", False),
        catch_phrase=hint.get("catch_phrase", ""),
        status_tags=list(hint.get("status_tags", [])),
    )

    # .tdL / .tdR の対応で属性抽出
    tdls = soup.select(".tdL")
    tdrs = soup.select(".tdR")
    for label_el, value_el in zip(tdls, tdrs):
        label = label_el.get_text(" ", strip=True)
        value = value_el.get_text(" ", strip=True)
        if "広さ" in label and "料金" in label:
            farm.fee = value
            # 入会金を分離
            m = re.search(r"入会金\s*([0-9,]+円(?:[（(]税込[)）])?)", value)
            if m:
                farm.entry_fee = m.group(1)
                farm.fee = re.sub(r"別途入会金.*?(?=※|$)", "", value).strip()
        elif "含まれるもの" in label or label.startswith("料金に含"):
            farm.included_services = value
        elif "施設" in label:
            farm.facilities = value
        elif "住所" in label:
            farm.address = value
        elif "アクセス" in label:
            farm.access = value

    # アドレスがまだ無ければ一覧側を流用
    if not farm.address and hint.get("list_address"):
        farm.address = hint["list_address"]

    # lat/lng （複数の埋め込みパターンに対応）
    latlng_patterns = [
        r'lat="([\-0-9.]+)"\s*lng="([\-0-9.]+)"',
        r'data-lat="([\-0-9.]+)"\s*data-lng="([\-0-9.]+)"',
        r'data-latitude="([\-0-9.]+)"\s*data-longitude="([\-0-9.]+)"',
        r'"lat"\s*:\s*([\-0-9.]+)\s*,\s*"lng"\s*:\s*([\-0-9.]+)',
        r'"latitude"\s*:\s*([\-0-9.]+)\s*,\s*"longitude"\s*:\s*([\-0-9.]+)',
        # data-* 順序逆 / その他フォールバック
        r'data-lng="([\-0-9.]+)"\s*data-lat="([\-0-9.]+)"',
    ]
    for pat in latlng_patterns:
        m = re.search(pat, html)
        if not m:
            continue
        try:
            # 最後のパターンだけ lng/lat の順
            if pat.startswith(r'data-lng'):
                farm.lng = float(m.group(1))
                farm.lat = float(m.group(2))
            else:
                farm.lat = float(m.group(1))
                farm.lng = float(m.group(2))
            break
        except ValueError:
            continue

    # 緯度経度が取れなかった場合、デバッグ用に検出を試みる
    if farm.lat is None or farm.lng is None:
        # ピンポイント検出: ".000" や "35.xxxx" を含む短いスニペット
        snippets = re.findall(r"(?:lat|lng|latitude|longitude)[^,\n]{0,80}", html, re.IGNORECASE)
        if snippets:
            print(
                f"[scrape]   ! lat/lng 抽出失敗。HTML 内サンプル: {snippets[:3]}",
                file=sys.stderr,
            )

    return farm


def scrape_area(city_name: str, out_dir: Path, max_farms: int = 0) -> List[Farm]:
    """区/市名を受け取って、対象農園を集める（詳細データ＋スクショ）。"""
    pref_slug, sb_slug, wp_slug, addr_filter = lookup_area(city_name)
    area_url = build_area_url(pref_slug, sb_slug)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[scrape] area={city_name} pref={pref_slug} sb_slug={sb_slug} url={area_url}", flush=True)
    if addr_filter:
        print(f"[scrape] 住所フィルタ: {addr_filter}", flush=True)

    from playwright.sync_api import sync_playwright

    farms: List[Farm] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 1200},
            locale="ja-JP",
            user_agent=USER_AGENT,
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => false });"
        )
        page = context.new_page()

        # 1) 一覧ページ
        list_html = _fetch(page, area_url)

        # デバッグ: ページ取得状況を可視化
        from bs4 import BeautifulSoup
        _dbg_soup = BeautifulSoup(list_html, "html.parser")
        _dbg_title = _dbg_soup.title.get_text(strip=True) if _dbg_soup.title else "(no title)"
        _farmlist_count = len(_dbg_soup.select(".farmlist_item"))
        _farm_anchors = len(_dbg_soup.select("a[href*='/farms/']"))
        _has_cf_challenge = ("Just a moment" in list_html) or ("cf-browser-verification" in list_html)
        print(
            f"[debug] html_len={len(list_html)} title={_dbg_title!r} "
            f".farmlist_item={_farmlist_count} farm_anchors={_farm_anchors} "
            f"cf_challenge={_has_cf_challenge}",
            flush=True,
        )
        # HTMLを artifact 保存（先頭3000字をログにも出す）
        try:
            (out_dir / "list_page.html").write_text(list_html, encoding="utf-8")
        except Exception:
            pass
        print("[debug] ----- list_page.html head -----", flush=True)
        print(list_html[:3000], flush=True)
        print("[debug] ----- end head -----", flush=True)

        items = _parse_list_page(list_html, area_url, addr_filter)
        if not items:
            print(f"[scrape] {city_name} に該当する農園が見つかりませんでした", flush=True)
            browser.close()
            return []

        if max_farms:
            items = items[:max_farms]

        # 2) 各農園詳細
        for i, hint in enumerate(items, 1):
            url = hint["detail_url"]
            print(f"[scrape] ({i}/{len(items)}) {url}", flush=True)
            detail_html = _fetch(page, url)
            farm = _parse_detail_page(detail_html, url, hint)

            # 上部のみのスクショ（タイトル＋画像ギャラリー＋申込ボタンまで）
            safe = re.sub(r"[^a-zA-Z0-9]+", "_", url.rstrip("/").split("/")[-1])
            shot_path = out_dir / f"farm_{i:02d}_{safe}.png"
            try:
                page.screenshot(
                    path=str(shot_path),
                    clip={"x": 0, "y": 0, "width": 1280, "height": 1100},
                )
                farm.screenshot_path = str(shot_path)
                print(f"[scrape]   -> {farm.name} (img: {shot_path.name})", flush=True)
            except Exception as e:
                print(f"[scrape]   ! スクショ失敗: {e}", file=sys.stderr)

            farms.append(farm)
            time.sleep(0.6)

        browser.close()

    return farms


if __name__ == "__main__":
    # 単体実行: python sharebatake_scraper.py 大田区
    if len(sys.argv) < 2:
        print("usage: sharebatake_scraper.py <区/市名> [出力ディレクトリ]", file=sys.stderr)
        sys.exit(2)
    city = sys.argv[1]
    out = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("out")
    result = scrape_area(city, out)
    print(f"\n=== 取得結果: {len(result)} 農園 ===")
    for f in result:
        print(f"- {f.name}")
        print(f"  住所: {f.address}")
        print(f"  料金: {f.fee}")
        print(f"  入会金: {f.entry_fee}")
        print(f"  施設: {f.facilities}")
        print(f"  状態タグ: {', '.join(f.status_tags)}")
        print(f"  lat/lng: {f.lat}, {f.lng}")
        print(f"  scrshot: {f.screenshot_path}")
