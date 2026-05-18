"""
ASP固定データ（5社分）
バナー画像HTML、4行テーブルデータ、ショートコードID
"""

ASP_LIST = {
    "valuecommerce": {
        "name": "バリューコマース",
        "shortcode": '[st_af id="2784"]',
        "banner_html": (
            '<a href="//ck.jp.ap.valuecommerce.com/servlet/referral?sid=3548721&amp;pid=892566121" rel="nofollow">'
            '<img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/vc.png" '
            'alt="バリューコマース" width="500" height="200" /></a>'
        ),
        "table": {
            "サイト審査": "あり",
            "最低支払額": "1,000円",
            "振込手数料": "無料",
            "得意ジャンル": "大手EC・Yahoo!ショッピング・金融・旅行",
        },
    },
    "a8": {
        "name": "A8.net",
        "shortcode": '[st_af id="4113"]',
        "banner_html": (
            '<a href="https://px.a8.net/svt/ejp?a8mat=3BG026+FXXVXU+0K+10A5LT" rel="nofollow noopener">'
            '<img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/a8.png" '
            'alt="A8net" width="500" height="200" /></a>'
        ),
        "table": {
            "サイト審査": "なし",
            "最低支払額": "1,000円",
            "振込手数料": "66〜660円",
            "得意ジャンル": "オールジャンル（国内最大級）",
        },
    },
    "accesstrade": {
        "name": "アクセストレード",
        "shortcode": '[st_af id="4115"]',
        "banner_html": (
            '<a href="https://h.accesstrade.net/sp/cc?rk=0100nldw00kolw" rel="nofollow">'
            '<img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/acces.png" '
            'alt="アクセストレード" width="500" height="200" /></a>'
        ),
        "table": {
            "サイト審査": "あり",
            "最低支払額": "1,000円",
            "振込手数料": "無料",
            "得意ジャンル": "金融・通信・ゲーム",
        },
    },
    "afb": {
        "name": "afb",
        "shortcode": '[st_af id="4122"]',
        "banner_html": (
            '<a href="https://t.afi-b.com/visit.php?a=l44x-c11095x&amp;p=T779612O" rel="nofollow">'
            '<img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/afb.png" '
            'alt="afb" width="500" height="200" /></a>'
        ),
        "table": {
            "サイト審査": "あり",
            "最低支払額": "777円",
            "振込手数料": "無料",
            "得意ジャンル": "美容・健康・脱毛",
        },
    },
    "moshimo": {
        "name": "もしもアフィリエイト",
        "shortcode": '[st_af id="4124"]',
        "banner_html": (
            '<a href="//af.moshimo.com/af/c/click?a_id=4207547&amp;p_id=1&amp;pc_id=1&amp;pl_id=82635" rel="nofollow">'
            '<img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/moshimo.png" '
            'alt="もしもアフィリエイト" width="500" height="200" /></a>'
        ),
        "table": {
            "サイト審査": "なし",
            "最低支払額": "1,000円",
            "振込手数料": "無料",
            "得意ジャンル": "物販（Amazon・楽天）・スクール系",
        },
    },
}

# ブロック1（◯✕比較テーブル）用のASP行HTMLテンプレート
ASP_ROW_TEMPLATE = {
    "a8": {
        "cell_html": (
            '<td style="width: 50%; text-align: center; vertical-align: middle;">'
            '<a href="https://px.a8.net/svt/ejp?a8mat=3BG026+FXXVXU+0K+10A5LT" rel="nofollow noopener">'
            '<img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/a8.png" '
            'alt="A8net" width="500" height="200" /></a>\n'
            '<a href="https://px.a8.net/svt/ejp?a8mat=3BG026+FXXVXU+0K+10A5LT" rel="nofollow">'
            'https://www.a8.net/</a></td>'
        ),
    },
    "valuecommerce": {
        "cell_html": (
            '<td style="width: 50%; text-align: center; vertical-align: middle;">'
            '<a href="//ck.jp.ap.valuecommerce.com/servlet/referral?sid=3548721&amp;amp;pid=892566121" rel="nofollow">'
            '<img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/vc.png" '
            'alt="バリューコマース" width="500" height="200" /></a>\n'
            '<a href="//ck.jp.ap.valuecommerce.com/servlet/referral?sid=3548721&amp;pid=892566121" rel="nofollow">'
            '<img src="//ad.jp.ap.valuecommerce.com/servlet/gifbanner?sid=3548721&amp;pid=892566121" '
            'width="1" height="1" border="0" />https://www.valuecommerce.ne.jp/</a></td>'
        ),
    },
    "accesstrade": {
        "cell_html": (
            '<td style="width: 50%; text-align: center; vertical-align: middle;">'
            '<a href="https://h.accesstrade.net/sp/cc?rk=0100nldw00kolw" rel="nofollow">'
            '<img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/acces.png" '
            'alt="アクセストレード" width="500" height="200" /></a>\n'
            '<a href="https://h.accesstrade.net/sp/cc?rk=0100nldw00kolw" rel="nofollow">'
            'https://www.accesstrade.ne.jp/</a></td>'
        ),
    },
    "afb": {
        "cell_html": (
            '<td style="width: 50%; text-align: center; vertical-align: middle;">'
            '<a href="https://t.afi-b.com/visit.php?a=l44x-c11095x&amp;p=T779612O" rel="nofollow">'
            '<img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/afb.png" '
            'alt="afb" width="500" height="200" /></a>\n'
            '<a href="https://t.afi-b.com/visit.php?a=l44x-c11095x&amp;p=T779612O" rel="nofollow">'
            'https://www.afi-b.com/</a></td>'
        ),
    },
    "moshimo": {
        "cell_html": (
            '<td style="width: 50%; text-align: center; vertical-align: middle;">'
            '<a href="//af.moshimo.com/af/c/click?a_id=4207547&amp;p_id=1&amp;pc_id=1&amp;pl_id=82635" rel="nofollow">'
            '<img class="alignnone size-full" src="https://www.garage-xxx.jp/wp-content/uploads/2026/04/moshimo.png" '
            'alt="もしもアフィリエイト" width="500" height="200" /></a>\n'
            '<a href="//af.moshimo.com/af/c/click?a_id=4207547&amp;p_id=1&amp;pc_id=1&amp;pl_id=82635" rel="nofollow">'
            'https://af.moshimo.com/</a></td>'
        ),
    },
}

# ◯✕比較テーブルの行順序
ASP_ORDER = ["a8", "valuecommerce", "accesstrade", "afb", "moshimo"]


def build_asp_comparison_table(asp_status):
    """
    ASP◯✕比較テーブルのHTMLを生成する。

    asp_status: dict like {"a8": True, "valuecommerce": True, "accesstrade": False, ...}
    """
    rows_html = []
    for key in ASP_ORDER:
        available = asp_status.get(key, False)
        cell = ASP_ROW_TEMPLATE[key]["cell_html"]
        if available:
            mark = '<span class="hutoaka"><span style="font-size: 7em;">◯</span></span>'
        else:
            mark = '<span style="font-size: 7em;">✕</span>'
        status_cell = f'<td style="width: 50%; text-align: center; vertical-align: middle;">{mark}</td>'
        rows_html.append(f"<tr>\n{cell}\n{status_cell}\n</tr>")

    return (
        '<table style="border-collapse: collapse; width: 100%;">\n<tbody>\n'
        '<tr>\n'
        '<th style="width: 50%; background-color: #301ef7;"></th>\n'
        '<th style="width: 50%; background-color: #301ef7;"><strong><span style="color: #ffffff;">広告掲載状況</span></strong></th>\n'
        '</tr>\n'
        + "\n".join(rows_html)
        + "\n</tbody>\n</table>"
    )


def build_asp_detail_section(asp_key, description_text):
    """
    個別ASPのH3セクション（バナー + 4行テーブル + 説明文 + ボタン）を生成。

    asp_key: "valuecommerce", "a8", etc.
    description_text: 4文のユニーク説明文
    """
    asp = ASP_LIST[asp_key]
    table_rows = []
    for label, value in asp["table"].items():
        table_rows.append(
            f'<tr>\n'
            f'<th style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;">'
            f'<span style="color: #ffffff;">{label}</span></th>\n'
            f'<td style="width: 50%; text-align: center; vertical-align: middle;">{value}</td>\n'
            f'</tr>'
        )

    table_html = (
        '<table style="border-collapse: collapse; width: 100%;">\n<tbody>\n'
        + "\n".join(table_rows)
        + "\n</tbody>\n</table>"
    )

    return (
        f"<h3>{asp['name']}</h3>\n"
        f"{asp['banner_html']}\n"
        f"{table_html}\n"
        f"{description_text}\n\n"
        f"{asp['shortcode']}"
    )


def build_case_info_table(case_name, company, site_url, site_display, genre, reward, condition, approval):
    """案件情報テーブル（7行）を生成"""
    rows = [
        ("案件名", case_name),
        ("運営会社", company),
        ("公式サイト", f'<a href="{site_url}" target="_blank" rel="noopener">{site_display}</a>'),
        ("ジャンル", genre),
        ("報酬単価", reward),
        ("成果条件", condition),
        ("承認基準", approval),
    ]
    rows_html = []
    for label, value in rows:
        rows_html.append(
            f'<tr>\n'
            f'<td style="width: 50%; text-align: center; vertical-align: middle; background-color: #4a4a4a;">'
            f'<strong><span style="color: #ffffff;">{label}</span></strong></td>\n'
            f'<td style="width: 50%; text-align: center; vertical-align: middle;">{value}</td>\n'
            f'</tr>'
        )
    return (
        '<table style="border-collapse: collapse; width: 100%;">\n<tbody>\n'
        + "\n".join(rows_html)
        + "\n</tbody>\n</table>"
    )
