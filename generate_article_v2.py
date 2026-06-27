#!/usr/bin/env python3
"""
記事生成スクリプト v2 — 複数ASP対応版

使い方:
  from generate_article_v2 import *

  row = find_case_in_csv('案件名')
  case_info = parse_case_info_from_csv_row(row)
  case_name = '案件名'
  case_info['case_name'] = case_name
  asp_status = {'a8':True,'valuecommerce':True,'accesstrade':False,'afb':False,'moshimo':False}
  asp_names = get_available_asp_names(asp_status)
  asp_descriptions = generate_asp_descriptions(case_name, asp_status, case_info)
  case_description = generate_case_description(case_name, case_info, asp_names)
  content = build_full_article(case_name, case_info, asp_status, asp_descriptions, case_description)
  title = f'{case_name}のアフィリエイトはどこのASP？'
  slug = 'slug-here'
  write_post_csv(title, content, slug, '')
"""

import csv
import os
import re

CSV_SOURCE = os.path.join(os.path.dirname(__file__), "csv", "vc_raw_utf8.csv")
CSV_OUTPUT = os.path.join(os.path.dirname(__file__), "csv", "post.csv")

IMG_BASE = "https://www.civichat.jp/wp-content/uploads/2026/03"

ASP_SHORTCODE_IDS = {
    "valuecommerce": "2784",
    "a8": "4113",
    "accesstrade": "4115",
    "afb": "4122",
    "moshimo": "4124",
}

ASP_DISPLAY_NAMES = {
    "a8": "A8.net",
    "valuecommerce": "バリューコマース",
    "accesstrade": "アクセストレード",
    "afb": "afb",
    "moshimo": "もしもアフィリエイト",
}

ASP_TABLE_DATA = [
    {
        "key": "a8",
        "name": "A8net",
        "img": f"{IMG_BASE}/a8.png",
        "link": "https://px.a8.net/svt/ejp?a8mat=3BG026+FXXVXU+0K+10A5LT",
        "display_url": "https://www.a8.net/",
        "img_rel": "nofollow noopener",
    },
    {
        "key": "valuecommerce",
        "name": "バリューコマース",
        "img": f"{IMG_BASE}/vc.png",
        "link": "//ck.jp.ap.valuecommerce.com/servlet/referral?sid=3548721&amp;amp;pid=892566121",
        "text_link": "//ck.jp.ap.valuecommerce.com/servlet/referral?sid=3548721&amp;pid=892566121",
        "display_url": "https://www.valuecommerce.ne.jp/",
        "beacon": '<img src="//ad.jp.ap.valuecommerce.com/servlet/gifbanner?sid=3548721&amp;pid=892566121" width="1" height="1" border="0" />',
    },
    {
        "key": "accesstrade",
        "name": "アクセストレード",
        "img": f"{IMG_BASE}/acces.png",
        "link": "https://h.accesstrade.net/sp/cc?rk=0100nldw00kolw",
        "display_url": "https://www.accesstrade.ne.jp/",
    },
    {
        "key": "afb",
        "name": "afb",
        "img": f"{IMG_BASE}/afb.png",
        "link": "https://www.afi-b.com/",
        "display_url": "https://www.afi-b.com/",
    },
    {
        "key": "moshimo",
        "name": "もしもアフィリエイト",
        "img": f"{IMG_BASE}/moshimo.png",
        "link": "//af.moshimo.com/af/c/click?a_id=4207547&amp;p_id=1&amp;pc_id=1&amp;pl_id=82635",
        "display_url": "https://af.moshimo.com/",
    },
]

# --- ASP詳細セクション（静的データ） ---

VC_DETAIL_INFO = [
    ("サービス開始年", "1999年（日本初のASP）"),
    ("運営会社", "バリューコマース株式会社（LINEヤフーグループ）"),
    ("サイト審査", "あり（記事数目安：7〜10記事程度）"),
    ("SNS・サイトなしで登録", "✕（サイト必要）"),
    ("初心者向けサポート", "◯"),
    ("案件総数", "大規模（累計広告主6,500社以上）"),
    ("得意ジャンル", "Yahoo!ショッピング・大手EC・金融・旅行"),
    ("Amazon・楽天案件", "〇"),
    ("独自案件の豊富さ", "◎（大手企業の独占案件多数）"),
    ("最低支払額", "500円"),
    ("振込手数料", "無料"),
    ("特別報酬制度", "会員ランク制度（ゴールド・シルバー・ブロンズ・一般）"),
    ("高単価案件", "〇"),
    ("管理画面の使いやすさ", "◎"),
    ("専任担当者", "〇"),
    ("薬機法チェック機能", "×"),
    ("おまかせ広告機能", "◎（コンテンツに合わせ自動で最適広告を配信）"),
    ("会員数", "85万サイト以上登録"),
    ("満足度実績", "日本最古のASPとしての老舗ブランド力"),
]

VC_RECOMMEND = [
    "Yahoo!ショッピングのアフィリエイトを扱いたい人",
    "大手企業・有名ブランドの信頼性の高い案件を紹介したい人",
    "広告の貼り替えの手間を省いて効率よく運用したい人",
]

VC_DESCRIPTION_TEXT = (
    '日本初のASPとして1999年に誕生した、<span class="hutoaka">信頼と実績のあるサービス</span>です。\n\n'
    'Yahoo!ショッピングのアフィリエイトを扱えるのはバリューコマースだけ。\n\n'
    '大手企業・有名ECサイトの案件が充実しているので、「信頼できるブランドの商品を紹介したい」という方に特に向いています。\n\n'
    'コンテンツに合わせて広告を自動表示してくれる<span class="st-mymarker-s">「おまかせ広告」機能も便利</span>です。\n\n'
    'また、会員ランク制度があり、成果を積み上げるほど特典や報酬条件が有利になっていく仕組みも魅力のひとつです。'
)

A8_DETAIL_INFO = [
    ("サービス開始年", "2000年"),
    ("運営会社", "株式会社ファンコミュニケーションズ（東証プライム上場）"),
    ("サイト審査", "なし（登録時の審査不要）"),
    ("SNS・サイトなしで登録", "◯（ファンブログで即開始可能）"),
    ("初心者向けサポート", "◎（A8キャンパス・セミナーなど充実）"),
    ("案件総数", "累計広告主数25,000社以上"),
    ("得意ジャンル", "美容・健康・金融・EC・サービス全般"),
    ("Amazon・楽天案件", "〇"),
    ("独自案件の豊富さ", "◎（国内最大級の案件数）"),
    ("最低支払額", "1,000円（即時支払いは1円から）"),
    ("振込手数料", "ゆうちょ66円、その他110〜770円"),
    ("特別報酬制度", "メディアランク制度（ゴールド・シルバー・ブロンズ等）"),
    ("高単価案件", "◎"),
    ("管理画面の使いやすさ", "◯"),
    ("専任担当者", "△（ランクによる）"),
    ("セルフバック", "◎（セルフバック専用ページあり）"),
    ("満足度実績", "13年連続利用者満足度No.1（アフィリエイトASP部門）"),
]

A8_RECOMMEND = [
    "アフィリエイト初心者でまず登録するASPを探している人",
    "できるだけ多くの案件から選びたい人",
    "審査なしですぐにアフィリエイトを始めたい人",
]

A8_DESCRIPTION_TEXT = (
    '国内最大級のアフィリエイトASPとして、<span class="hutoaka">累計25,000社以上の広告主</span>が参加しています。\n\n'
    '登録時にサイト審査がないため、初心者でもすぐに始められるのが大きな特徴です。\n\n'
    '案件数の多さはもちろん、セルフバック（自己アフィリエイト）機能も充実しており、'
    '自分で商品を試しながら報酬を得ることもできます。\n\n'
    '<span class="st-mymarker-s">13年連続でアフィリエイトASP満足度No.1</span>を獲得しており、'
    '信頼性の高さも魅力です。\n\n'
    'まずはA8.netに登録して、気になる案件を探してみましょう。'
)

AT_DETAIL_INFO = [
    ("サービス開始年", "2001年"),
    ("運営会社", "株式会社インタースペース（東証グロース上場）"),
    ("サイト審査", "あり"),
    ("SNS・サイトなしで登録", "◯（Instagramアカウントで登録可能）"),
    ("初心者向けサポート", "◯"),
    ("案件総数", "累計広告主数27,000社以上"),
    ("得意ジャンル", "金融・人材・通信・ゲーム"),
    ("Amazon・楽天案件", "×"),
    ("独自案件の豊富さ", "◯（金融・通信に強い独自案件）"),
    ("最低支払額", "1,000円"),
    ("振込手数料", "無料"),
    ("特別報酬制度", "ATステージ制度（報酬額に応じてランクアップ）"),
    ("高単価案件", "◎（金融・通信系に強い）"),
    ("管理画面の使いやすさ", "◯"),
    ("専任担当者", "◯（ランクに応じて）"),
    ("AIチャットサポート", "◯（24時間対応のAIチャットボット）"),
    ("満足度実績", "広告主満足度の高さに定評あり"),
]

AT_RECOMMEND = [
    "金融・通信・人材系の案件を重点的に扱いたい人",
    "振込手数料を無料にしたい人",
    "Instagram等のSNSでアフィリエイトを始めたい人",
]

AT_DESCRIPTION_TEXT = (
    '2001年サービス開始の老舗ASPで、<span class="hutoaka">金融・通信・人材系のジャンルに特に強い</span>のが特徴です。\n\n'
    '振込手数料が無料なので、報酬がそのまま受け取れるのも嬉しいポイントです。\n\n'
    'InstagramなどのSNSアカウントでも登録できるため、ブログを持っていない方でも始められます。\n\n'
    '<span class="st-mymarker-s">金融系・通信系の高単価案件が豊富</span>で、単価重視のアフィリエイターにも人気があります。\n\n'
    'ATステージ制度で成果に応じたランクアップ特典も用意されています。'
)

AFB_DETAIL_INFO = [
    ("サービス開始年", "2006年"),
    ("運営会社", "株式会社フォーイット"),
    ("サイト審査", "あり"),
    ("SNS・サイトなしで登録", "×（サイト必要）"),
    ("初心者向けサポート", "◯"),
    ("案件総数", "累計広告主数13,000社以上"),
    ("得意ジャンル", "美容・健康・脱毛・エステ・金融"),
    ("Amazon・楽天案件", "×"),
    ("独自案件の豊富さ", "◯（美容・健康系に独自案件多数）"),
    ("最低支払額", "777円"),
    ("振込手数料", "無料"),
    ("特別報酬制度", "ステージ制度（報酬+消費税分上乗せ）"),
    ("高単価案件", "◎（美容・脱毛系で高単価）"),
    ("管理画面の使いやすさ", "◎"),
    ("専任担当者", "◯"),
    ("報酬支払い", "翌月末払い（業界最速水準）"),
    ("満足度実績", "利用者満足度率が高い（パートナー第一主義）"),
]

AFB_RECOMMEND = [
    "美容・健康・脱毛系の案件を扱いたい人",
    "報酬の支払いが早いASPを使いたい人",
    "消費税分も上乗せで受け取りたい人",
]

AFB_DESCRIPTION_TEXT = (
    '「パートナー第一主義」を掲げ、<span class="hutoaka">報酬の支払いが翌月末と業界最速水準</span>のASPです。\n\n'
    '最低支払額が777円と低く設定されているため、初心者でも報酬を受け取りやすいのが魅力です。\n\n'
    '美容・健康・脱毛・エステなどの案件に特に強く、高単価案件も豊富に揃っています。\n\n'
    '<span class="st-mymarker-s">報酬に消費税分が上乗せ</span>されるため、同じ成果件数でも他ASPより実質報酬が高くなります。\n\n'
    '管理画面も使いやすく、アフィリエイター満足度の高いASPです。'
)

MOSHIMO_DETAIL_INFO = [
    ("サービス開始年", "2004年"),
    ("運営会社", "株式会社もしも"),
    ("サイト審査", "なし（登録時の審査不要）"),
    ("SNS・サイトなしで登録", "◯"),
    ("初心者向けサポート", "◎"),
    ("案件総数", "累計広告主数8,000社以上"),
    ("得意ジャンル", "Amazon・楽天・物販・プログラミングスクール"),
    ("Amazon・楽天案件", "◎（かんたんリンクで一括表示）"),
    ("独自案件の豊富さ", "◯（プログラミング・英会話等に独自案件）"),
    ("最低支払額", "1,000円（住信SBIは1円から）"),
    ("振込手数料", "無料"),
    ("特別報酬制度", "W報酬制度（通常報酬+12%ボーナス）"),
    ("高単価案件", "◯"),
    ("管理画面の使いやすさ", "◎"),
    ("かんたんリンク", "◎（Amazon・楽天・Yahoo!を1つのリンクで表示）"),
    ("Amazon提携", "◎（もしも経由で審査通過しやすい）"),
    ("満足度実績", "初心者満足度が高い"),
]

MOSHIMO_RECOMMEND = [
    "Amazon・楽天の商品紹介をまとめてやりたい人",
    "W報酬制度で報酬を12%上乗せしたい人",
    "審査なしで手軽にアフィリエイトを始めたい人",
]

MOSHIMO_DESCRIPTION_TEXT = (
    '「個人のための」をコンセプトにした、<span class="hutoaka">初心者に優しいASP</span>です。\n\n'
    'Amazon・楽天・Yahoo!ショッピングの商品を1つのリンクでまとめて紹介できる「かんたんリンク」が便利です。\n\n'
    'もしもアフィリエイト経由でAmazonアソシエイトに申請すると、審査に通りやすいと言われています。\n\n'
    '<span class="st-mymarker-s">W報酬制度で通常報酬に12%のボーナス</span>が上乗せされるのが最大の魅力です。\n\n'
    '物販アフィリエイトを始めるなら、まず登録しておきたいASPのひとつです。'
)

ASP_DETAILS = {
    "valuecommerce": {
        "info": VC_DETAIL_INFO,
        "recommend": VC_RECOMMEND,
        "description": VC_DESCRIPTION_TEXT,
        "screenshot": f"{IMG_BASE}/スクリーンショット-2026-03-15-182118.png",
        "screenshot_alt": "バリューコマース",
        "screenshot_w": 951, "screenshot_h": 535,
    },
    "a8": {
        "info": A8_DETAIL_INFO,
        "recommend": A8_RECOMMEND,
        "description": A8_DESCRIPTION_TEXT,
        "screenshot": f"{IMG_BASE}/a8_detail.png",
        "screenshot_alt": "A8.net",
        "screenshot_w": 951, "screenshot_h": 535,
    },
    "accesstrade": {
        "info": AT_DETAIL_INFO,
        "recommend": AT_RECOMMEND,
        "description": AT_DESCRIPTION_TEXT,
        "screenshot": f"{IMG_BASE}/accesstrade_detail.png",
        "screenshot_alt": "アクセストレード",
        "screenshot_w": 951, "screenshot_h": 535,
    },
    "afb": {
        "info": AFB_DETAIL_INFO,
        "recommend": AFB_RECOMMEND,
        "description": AFB_DESCRIPTION_TEXT,
        "screenshot": f"{IMG_BASE}/afb_detail.png",
        "screenshot_alt": "afb",
        "screenshot_w": 951, "screenshot_h": 535,
    },
    "moshimo": {
        "info": MOSHIMO_DETAIL_INFO,
        "recommend": MOSHIMO_RECOMMEND,
        "description": MOSHIMO_DESCRIPTION_TEXT,
        "screenshot": f"{IMG_BASE}/moshimo_detail.png",
        "screenshot_alt": "もしもアフィリエイト",
        "screenshot_w": 951, "screenshot_h": 535,
    },
}


def find_case_in_csv(keyword):
    with open(CSV_SOURCE, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if keyword in row.get("プログラム名", ""):
                return row
    raise ValueError(f"案件が見つかりません: {keyword}")


def parse_case_info_from_csv_row(row):
    cpc = (row.get("CPC報酬") or "").strip()
    fixed = (row.get("定額報酬") or "").strip()
    rate = (row.get("定率報酬") or "").strip()
    parts = []
    if fixed:
        parts.append(fixed)
    if rate:
        parts.append(rate)
    if cpc:
        parts.append(f"CPC: {cpc}")
    reward = " / ".join(parts) if parts else "-"

    condition = (row.get("注文発生対象・条件") or "").strip() or "-"
    approval = (row.get("成果の承認基準") or "").strip() or "-"

    if rate and not fixed:
        genre = "物販"
    elif "購入" in condition or "注文" in condition:
        genre = "物販"
    else:
        genre = "登録"

    return {
        "case_name": (row.get("プログラム名") or "").strip(),
        "company": (row.get("会社名") or "").strip(),
        "advertiser_name": (row.get("広告主名") or "").strip(),
        "site_url": (row.get("広告主サイトURL") or "").strip(),
        "reward": reward,
        "condition": condition,
        "approval": approval,
        "genre": genre,
        "program_content": (row.get("プログラム内容") or "").strip(),
        "fixed_reward": fixed,
        "rate_reward": rate,
        "cpc_reward": cpc,
    }


def get_available_asp_names(asp_status):
    order = ["a8", "valuecommerce", "accesstrade", "afb", "moshimo"]
    return [ASP_DISPLAY_NAMES[k] for k in order if asp_status.get(k)]


def _build_asp_comparison_table(asp_status):
    TH_STYLE = 'style="width: 50%; background-color: #301ef7;"'
    TD_CENTER = 'style="width: 50%; text-align: center; vertical-align: middle;"'

    rows_html = []
    for asp in ASP_TABLE_DATA:
        key = asp["key"]
        is_available = asp_status.get(key, False)

        if is_available:
            mark = '<span class="hutoaka"><span style="font-size: 7em;">◯</span></span>'
        else:
            mark = '<span style="font-size: 7em;">✕</span>'

        beacon = asp.get("beacon", "")
        img_rel = asp.get("img_rel", "nofollow")
        text_link = asp.get("text_link", asp["link"])

        rows_html.append(
            f'<tr>\n'
            f'<td {TD_CENTER}>'
            f'<a href="{asp["link"]}" rel="{img_rel}">'
            f'<img class="alignnone size-full" src="{asp["img"]}" alt="{asp["name"]}" width="500" height="200" /></a>\n'
            f'<a href="{text_link}" rel="nofollow">{beacon}{asp["display_url"]}</a></td>\n'
            f'<td {TD_CENTER}>{mark}</td>\n'
            f'</tr>'
        )

    return (
        f'<table style="border-collapse: collapse; width: 100%;">\n'
        f'<tbody>\n'
        f'<tr>\n<th {TH_STYLE}></th>\n'
        f'<th {TH_STYLE}><strong><span style="color: #ffffff;">広告掲載状況</span></strong></th>\n</tr>\n'
        + "\n".join(rows_html)
        + "\n</tbody>\n</table>"
    )


def _build_asp_detail_section(asp_key):
    detail = ASP_DETAILS[asp_key]
    TH_STYLE = 'style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"'
    TD_STYLE = 'style="width: 50%; text-align: center; vertical-align: middle;"'

    display_name = ASP_DISPLAY_NAMES[asp_key]

    table_rows = "\n".join(
        f'<tr>\n<th {TH_STYLE}><span style="color: #ffffff;">{label}</span></th>\n'
        f'<td {TD_STYLE}>{value}</td>\n</tr>'
        for label, value in detail["info"]
    )

    recommend_items = "\n".join(f' \t<li>{item}</li>' for item in detail["recommend"])

    screenshot_html = ""
    if asp_key == "valuecommerce":
        screenshot_html = (
            f'<img class="alignnone size-full" src="{detail["screenshot"]}" '
            f'alt="{detail["screenshot_alt"]}" width="{detail["screenshot_w"]}" height="{detail["screenshot_h"]}" />\n'
        )

    return (
        f'<h3>{display_name}</h3>\n'
        f'{screenshot_html}'
        f'<table style="border-collapse: collapse; width: 100%;">\n<tbody>\n'
        f'{table_rows}\n'
        f'</tbody>\n</table>\n'
        f'[st-minihukidashi webicon="" fontsize="" fontweight="" bgcolor="#FFB74D" color="#fff" '
        f'margin="0 0 20px 0" radius="" position="" myclass="" add_boxstyle=""]おすすめな人\n'
        f'<div class="st-square-checkbox st-square-checkbox-nobox">\n'
        f'<ul>\n{recommend_items}\n</ul>\n'
        f'</div>\n'
        f'[/st-minihukidashi]\n'
        f'{detail["description"]}'
    )


def generate_asp_descriptions(case_name, asp_status, case_info):
    order = ["a8", "valuecommerce", "accesstrade", "afb", "moshimo"]
    available = [k for k in order if asp_status.get(k)]

    sections = []
    for asp_key in available:
        section = _build_asp_detail_section(asp_key)
        shortcode_id = ASP_SHORTCODE_IDS[asp_key]
        section += f'\n[st_af id="{shortcode_id}"]'
        sections.append(section)

    return "\n\n".join(sections)


def generate_case_description(case_name, case_info, asp_names):
    asp_text = "・".join(asp_names)

    reward = case_info.get("reward", "-")
    condition = case_info.get("condition", "-")
    company = case_info.get("company", "")
    genre = case_info.get("genre", "登録")
    program_content = case_info.get("program_content", "")

    if genre == "物販":
        part1 = (
            f'{case_name}は、{company}が運営するサービスです。\n\n'
            f'豊富な商品ラインナップと使いやすいサイト設計で、多くのユーザーに支持されています。\n\n'
        )
    else:
        part1 = (
            f'{case_name}は、{company}が運営するサービスです。\n\n'
            f'<span class="hutoaka">無料で利用できる手軽さ</span>が魅力で、幅広いユーザー層に支持されています。\n\n'
        )

    part2 = (
        f'アフィリエイトとしては、<span class="st-mymarker-s">報酬単価{reward}円</span>で{condition}が成果条件となっています。\n\n'
    )

    if len(asp_names) == 1:
        part3 = f'{asp_names[0]}で提携できます。\n\n'
    else:
        part3 = f'{asp_text}で提携できます。\n\n'

    desc = part1 + part2 + part3

    if program_content:
        summary = program_content[:150].strip()
        if summary and not summary.endswith("。"):
            last = summary.rfind("。")
            if last > 0:
                summary = summary[:last + 1]
            else:
                summary = ""
        if summary:
            desc += summary + "\n\n"

    return desc.rstrip()


def _build_case_info_table(case_name, case_info, screenshot_url=""):
    TD_TH = 'style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;"'
    TD_STYLE = 'style="width: 50%; text-align: center; vertical-align: middle;"'

    site_url = case_info.get("site_url", "")
    adv_name = case_info.get("advertiser_name", case_name)
    site_link = (
        f'<a href="{site_url}" target="_blank" rel="noopener">{adv_name}</a>'
        if site_url else "-"
    )

    info_items = [
        ("案件名", case_name),
        ("運営会社", case_info.get("company", "-")),
        ("公式サイト", site_link),
        ("ジャンル", case_info.get("genre", "登録")),
        ("報酬単価", case_info.get("reward", "-") + "円" if case_info.get("reward", "-") != "-" else "-"),
        ("成果条件", case_info.get("condition", "-")),
        ("確定率", "不明"),
        ("CVR", "不明"),
        ("EPC", "不明"),
        ("承認基準", case_info.get("approval", "-")),
    ]

    rows_html = "\n".join(
        f'<tr>\n<td {TD_TH}><strong><span style="color: #ffffff;">{label}</span></strong></td>\n'
        f'<td {TD_STYLE}>{value}</td>\n</tr>'
        for label, value in info_items
    )

    screenshot_html = ""
    if screenshot_url:
        screenshot_html = (
            f'<img class="alignnone size-full" src="{screenshot_url}" '
            f'alt="{case_name}" width="1280" height="800" />\n'
        )

    return (
        f'{screenshot_html}'
        f'<table style="border-collapse: collapse; width: 100%;">\n'
        f'<tbody>\n{rows_html}\n</tbody>\n</table>'
    )


def build_full_article(case_name, case_info, asp_status, asp_descriptions, case_description, screenshot_url=""):
    available = [k for k in ["a8", "valuecommerce", "accesstrade", "afb", "moshimo"] if asp_status.get(k)]
    asp_names = get_available_asp_names(asp_status)

    if len(asp_names) == 1:
        lead_text = f'{case_name}は<span class="st-mymarker-s">{asp_names[0]}</span>でアフィリエイトできます。'
    else:
        lead_text = f'{case_name}は<span class="st-mymarker-s">{asp_names[0]}</span>・{"・".join(asp_names[1:])}でアフィリエイトできます。'

    section1 = lead_text

    last_asp = available[-1]
    last_shortcode = f'[st_af id="{ASP_SHORTCODE_IDS[last_asp]}"]'

    section3 = (
        f'<h2>{case_name}のアフィリエイト情報</h2>\n'
        + _build_case_info_table(case_name, case_info, screenshot_url) + "\n"
        + case_description + "\n"
        + last_shortcode
    )

    return "\n\n".join([section1, section3])


def write_post_csv(title, content, slug, screenshot_url=""):
    # スクリーンショットは今後の記事では不要なため、screenshot_url は常に空にする
    fieldnames = ["title", "content", "status", "category", "tags", "slug", "screenshot_url"]
    row = {
        "title": title,
        "content": content,
        "status": "draft",
        "category": "",
        "tags": "",
        "slug": slug,
        "screenshot_url": "",
    }
    with open(CSV_OUTPUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerow(row)

    print(f"csv/post.csv に出力しました: {title}")
