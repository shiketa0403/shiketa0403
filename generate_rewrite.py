#!/usr/bin/env python3
"""
リライト用記事一括生成スクリプト

既存のWordPress記事を新フォーマット（7見出し構成）でリライトするための
csv/post.csv を生成する。

使い方:
  python generate_rewrite.py
"""

import csv
import json
import os
import re
import sys


IMG_BASE = "https://www.garage-xxx.jp/wp-content/uploads/2026/04"

CASE_LIST = [
    ("アルペンオンラインストア", "alpen"),
    ("WEGO ONLINE STORE", "wego"),
    ("calif", "calif"),
    ("WORLD ONLINE STORE", "world-online-store"),
    ("SuperGroupies", "super-groupies"),
    ("資生堂パーラー", "shiseido-parlour"),
    ("JAタウン", "ja-town"),
    ("ベルーナグルメ", "belluna-gourmet"),
    ("Firadis WINE CLUB", "firadis-wine-club"),
    ("Cake.jp", "cake-jp"),
    ("成城石井.com", "seijoishii"),
    ("富澤商店オンラインショップ", "tomizawa-shouten"),
    ("ピエール・エルメ・パリ オンラインブティック", "pierre-herme"),
    ("サンクゼール〈久世福商店〉", "st-cousair"),
    ("ブルーボトルコーヒー公式オンラインストア", "blue-bottle-coffee"),
    ("辛子めんたい 福さ屋", "fukusaya"),
    ("BAKE THE ONLINE", "bake-the-online"),
    ("湖池屋オンラインショップ", "koikeya"),
    ("日本橋いなば園", "inabaen"),
    ("PAPABUBBLE（パパブブレ）", "papabubble"),
    ("Broad WiMAX", "broad-wimax"),
    ("BIGLOBE WiMAX", "biglobe-wimax"),
    ("ワイモバイル", "ymobile"),
    ("LINEMO（ラインモ）", "linemo"),
    ("サイバー大学", "cyber-university"),
    ("FURDI（ファディー）", "furdi"),
    ("GREEN SPOON", "green-spoon"),
    ("RISU", "risu"),
    ("ahamo", "ahamo"),
    ("おもちゃのサブスク Cha Cha Cha", "cha-cha-cha"),
    ("DMMプレミアム", "dmm-premium"),
    ("AI英会話スピーク", "speak"),
    ("にゃんこWi-Fi", "nyanko-wifi"),
    ("医療キャリアナビ", "iryou-career-navi"),
    ("LINE MUSIC", "line-music"),
    ("ノムコム", "nomu-com"),
    ("サジーのフィネス", "fineness-saji"),
    ("ホムホム", "homhom"),
    ("MCナースネット", "mc-nurse-net"),
    ("東邦ガス", "toho-gas"),
    ("コトラ", "kotora"),
    ("アサンテ", "asante"),
    ("ゼクシィ相談カウンター", "zexy-counter"),
    ("IIJmioひかり", "iijmio-hikari"),
    ("4℃ブライダル", "4c-bridal"),
    ("ハナユメ", "hanayume"),
    ("レバテックキャリア", "levtech-career"),
    ("ターキッシュエア＆トラベル", "turkish-air-travel"),
    ("タイズ", "tyz"),
    ("スマモニ", "sumamoni"),
    ("アルコシステム", "arco-system"),
    ("GMOクリック証券 FX", "gmo-click-fx"),
    ("JAC Recruitment", "jac-recruitment"),
    ("ナースではたらこ", "nurse-de-hatarako"),
    ("Airレジ", "air-regi"),
    ("松井証券 MATSUI FX", "matsui-fx"),
    ("SoftBank Air", "softbank-air"),
    ("弁護士法人みやびの退職代行", "miyabi-taishoku"),
    ("薬用ナノインパクト8", "nano-impact"),
    ("保険マンモス", "hoken-mammoth"),
    ("ABLENET VPS", "ablenet-vps"),
    ("SoftBank光", "softbank-hikari"),
    ("エイジレスエージェント", "ageless-agent"),
    ("TechClipsエージェント", "techclips-agent"),
    ("スーパーナース", "super-nurse"),
    ("パーソルクロステクノロジー", "persol-cross-tech"),
    ("イデックスでんき", "idex-denki"),
    ("タウンライフ", "town-life"),
    ("auひかり", "au-hikari"),
    ("フレッツ光", "flets-hikari"),
    ("アールイズ・ウエディング", "arluis-wedding"),
    ("プレサンスグループ", "pressance"),
    ("Watepoint ポット型浄水器Lifewater Jug", "watepoint"),
    ("anote", "anote"),
    ("マネーフォワード ME", "money-forward-me"),
    ("airalo 紹介プログラム", "airalo"),
    ("DMMカード新規発行", "dmm-card"),
    ("ブーリスチェアオンラインストア", "bourisce-hair"),
]


def load_vc_data():
    """vc_raw_utf8.csv を読み込んで返す"""
    with open("csv/vc_raw_utf8.csv", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def match_case(case_name, rows):
    """案件名からCSVの行をマッチングする"""
    case_clean = re.sub(r'[（）〈〉\(\)＆&]', '', case_name).lower().replace('　', ' ').strip()

    for row in rows:
        adv = row.get('広告主名', '')
        prog = row.get('プログラム名', '')
        adv_clean = re.sub(r'[（）〈〉\(\)＆&]', '', adv).lower().replace('　', ' ').strip()
        prog_clean = re.sub(r'[（）〈〉\(\)＆&]', '', prog).lower().replace('　', ' ').strip()

        if case_clean == adv_clean or case_clean == prog_clean:
            return row
        if case_clean in adv_clean or adv_clean in case_clean:
            return row
        if case_clean in prog_clean or prog_clean in case_clean:
            return row

    return None


def format_reward(row):
    """報酬テキストを生成"""
    fixed = row.get('定額報酬', '').strip()
    rate = row.get('定率報酬', '').strip()
    if fixed and rate:
        return f"{fixed}円 / {rate}"
    if fixed:
        return f"{fixed}円"
    if rate:
        return f"購入金額の{rate}" if '%' in rate else rate
    return "不明"


def get_approval(row):
    """承認基準を取得"""
    approval = row.get('成果の承認基準', '').strip()
    if approval:
        return approval
    other = row.get('成果の承認基準（その他）', '').strip()
    if other:
        return other
    comment = row.get('コメント・注意事項（オファー）', '').strip()
    if comment and '承認' in comment:
        for line in comment.split('\n'):
            if '承認' in line:
                line = re.sub(r'^【承認基準】[:：]?\s*', '', line)
                return line.strip()
    return "公式サイト参照"


def get_condition(row):
    """成果条件を取得"""
    cond = row.get('注文発生対象・条件', '').strip()
    if cond:
        return cond
    comment = row.get('コメント・注意事項（オファー）', '').strip()
    if comment:
        for line in comment.split('\n'):
            if '条件' in line or '成果' in line or '承認' in line:
                line = re.sub(r'^【.*?】[:：]?\s*', '', line)
                if line.strip():
                    return line.strip()
    return "公式サイト参照"


def detect_genre(row):
    """ジャンルを判定"""
    fixed = row.get('定額報酬', '').strip()
    rate = row.get('定率報酬', '').strip()
    cat1 = row.get('カテゴリー1', '').lower()

    if rate and not fixed:
        return "物販"

    keywords_touroku = ['登録', '申込', '口座', '会員', '資料請求', '見積', '相談',
                        '予約', '査定', '応募', '体験', '入会', '契約', '開通']
    cond = row.get('注文発生対象・条件', '') + row.get('コメント・注意事項（オファー）', '')
    for kw in keywords_touroku:
        if kw in cond:
            return "登録"

    if fixed and not rate:
        return "登録"

    return "物販"


def build_block1(case_name):
    """Block1: 冒頭 + ASP比較テーブル"""
    return f"""{case_name}は<span class="st-mymarker-s">バリューコマース</span>でアフィリエイトできます。
<table style="border-collapse: collapse; width: 100%;">
<tbody>
<tr>
<th style="width: 50%; background-color: #301ef7;"></th>
<th style="width: 50%; background-color: #301ef7;"><strong><span style="color: #ffffff;">広告掲載状況</span></strong></th>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="https://px.a8.net/svt/ejp?a8mat=3BG026+FXXVXU+0K+10A5LT" rel="nofollow noopener"><img class="alignnone size-full" src="{IMG_BASE}/a8.png" alt="A8net" width="500" height="200" /></a>
<a href="https://px.a8.net/svt/ejp?a8mat=3BG026+FXXVXU+0K+10A5LT" rel="nofollow">https://www.a8.net/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span style="font-size: 7em;">✕</span></td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="//ck.jp.ap.valuecommerce.com/servlet/referral?sid=3548721&amp;amp;pid=892566121" rel="nofollow"><img class="alignnone size-full" src="{IMG_BASE}/vc.png" alt="バリューコマース" width="500" height="200" /></a>
<a href="//ck.jp.ap.valuecommerce.com/servlet/referral?sid=3548721&amp;pid=892566121" rel="nofollow"><img src="//ad.jp.ap.valuecommerce.com/servlet/gifbanner?sid=3548721&amp;pid=892566121" width="1" height="1" border="0" />https://www.valuecommerce.ne.jp/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span class="hutoaka"><span style="font-size: 7em;">◯</span></span></td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="https://h.accesstrade.net/sp/cc?rk=0100nldw00kolw" rel="nofollow"><img class="alignnone size-full" src="{IMG_BASE}/acces.png" alt="アクセストレード" width="500" height="200" /></a>
<a href="https://h.accesstrade.net/sp/cc?rk=0100nldw00kolw" rel="nofollow">https://www.accesstrade.ne.jp/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span style="font-size: 7em;">✕</span></td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="https://www.afi-b.com/" rel="nofollow"><img class="alignnone size-full" src="{IMG_BASE}/afb.png" alt="afb" width="500" height="200" /></a>
<a href="https://www.afi-b.com/" rel="nofollow">https://www.afi-b.com/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span style="font-size: 7em;">✕</span></td>
</tr>
<tr>
<td style="width: 50%; text-align: center; vertical-align: middle;"><a href="//af.moshimo.com/af/c/click?a_id=4207547&amp;p_id=1&amp;pc_id=1&amp;pl_id=82635" rel="nofollow"><img class="alignnone size-full" src="{IMG_BASE}/moshimo.png" alt="もしもアフィリエイト" width="500" height="200" /></a>
<a href="//af.moshimo.com/af/c/click?a_id=4207547&amp;p_id=1&amp;pc_id=1&amp;pl_id=82635" rel="nofollow">https://af.moshimo.com/</a></td>
<td style="width: 50%; text-align: center; vertical-align: middle;"><span style="font-size: 7em;">✕</span></td>
</tr>
</tbody>
</table>"""


def build_block2(case_name, row):
    """Block2: アフィリエイト情報テーブル"""
    company = row.get('会社名', '').strip() or '-'
    site_url = row.get('広告主サイトURL', '').strip()
    adv_name = row.get('広告主名', '').strip()
    genre = detect_genre(row)
    reward = format_reward(row)
    condition = get_condition(row)
    approval = get_approval(row)

    site_link = f'<a href="{site_url}" target="_blank" rel="noopener">{adv_name}</a>' if site_url else '-'

    TD_TH = 'style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"'
    TD = 'style="width: 50%; text-align: center; vertical-align: middle;"'

    return f"""<h2>{case_name}のアフィリエイト情報</h2>
<table style="border-collapse: collapse; width: 100%;">
<tbody>
<tr>
<td {TD_TH}><strong><span style="color: #ffffff;">案件名</span></strong></td>
<td {TD}>{case_name}</td>
</tr>
<tr>
<td {TD_TH}><strong><span style="color: #ffffff;">運営会社</span></strong></td>
<td {TD}>{company}</td>
</tr>
<tr>
<td {TD_TH}><strong><span style="color: #ffffff;">公式サイト</span></strong></td>
<td {TD}>{site_link}</td>
</tr>
<tr>
<td {TD_TH}><strong><span style="color: #ffffff;">ジャンル</span></strong></td>
<td {TD}>{genre}</td>
</tr>
<tr>
<td {TD_TH}><strong><span style="color: #ffffff;">報酬単価</span></strong></td>
<td {TD}>{reward}</td>
</tr>
<tr>
<td {TD_TH}><strong><span style="color: #ffffff;">成果条件</span></strong></td>
<td {TD}>{condition}</td>
</tr>
<tr>
<td {TD_TH}><strong><span style="color: #ffffff;">確定率</span></strong></td>
<td {TD}>不明</td>
</tr>
<tr>
<td {TD_TH}><strong><span style="color: #ffffff;">CVR</span></strong></td>
<td {TD}>不明</td>
</tr>
<tr>
<td {TD_TH}><strong><span style="color: #ffffff;">EPC</span></strong></td>
<td {TD}>不明</td>
</tr>
<tr>
<td {TD_TH}><strong><span style="color: #ffffff;">承認基準</span></strong></td>
<td {TD}>{approval}</td>
</tr>
</tbody>
</table>"""


def main():
    rows = load_vc_data()
    print(f"CSV読み込み: {len(rows)}件")

    results = []
    errors = []

    for case_name, slug in CASE_LIST:
        row = match_case(case_name, rows)
        if not row:
            errors.append(case_name)
            continue

        info = {
            "case_name": case_name,
            "slug": slug,
            "company": row.get('会社名', '').strip(),
            "site_url": row.get('広告主サイトURL', '').strip(),
            "adv_name": row.get('広告主名', '').strip(),
            "genre": detect_genre(row),
            "reward": format_reward(row),
            "condition": get_condition(row),
            "approval": get_approval(row),
            "block1": build_block1(case_name),
            "block2": build_block2(case_name, row),
        }
        results.append(info)

    if errors:
        print(f"マッチ失敗: {errors}")

    # JSON出力（Block3生成用）
    with open("/tmp/rewrite_data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"生成完了: {len(results)}件 → /tmp/rewrite_data.json")

    # サマリー出力
    for r in results:
        print(f"  {r['case_name']} | {r['genre']} | {r['reward']} | {r['slug']}")


if __name__ == "__main__":
    main()
