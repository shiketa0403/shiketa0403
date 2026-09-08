# 装飾セット: plain（テーマ非依存・インラインCSS）

サイト設定 `sites.local.json` の該当サイトに `"decoration": "plain"` がある場合、
prompts/07 のAFFINGERショートコードの代わりに**本書の書式**を使う。
`"decoration"` の指定が無いサイトは従来通りAFFINGER（prompts/07）を使う。

## 配色

サイト設定の `main_color`（例: `"#1565c0"`）を基準に、次を使う。
未指定なら `#1565c0`（青）を既定とする。

| 役割 | 値の作り方 | 青(#1565c0)の場合 |
|---|---|---|
| メイン | main_color | #1565c0 |
| メイン濃 | main_colorを暗く | #0d47a1 |
| メイン淡背景 | main_colorの薄い色 | #e8f0fe |
| 強調色（赤系） | 固定 | #c62828 |
| マーカー | 固定（黄） | #ffeb3b |

**同一サイト内では毎回同じ色を使う**（記事ごとに変えない）。

## 装飾の書式（この通りに出力する）

### 1. 黄色マーカー（最重要ポイント・記事全体で1箇所）
```html
<span style="background:linear-gradient(transparent 60%,#ffeb3b 60%);font-weight:bold;">テキスト</span>
```

### 2. 強調（補足的な強調・記事全体で1〜2箇所）
```html
<span style="color:#c62828;font-weight:bold;">テキスト</span>
```

### 3. まとめボックス（冒頭「この記事のまとめ」）
```html
<div style="border:2px solid #1565c0;border-radius:8px;margin:24px 0;overflow:hidden;">
<div style="background:#1565c0;color:#fff;font-weight:bold;padding:10px 16px;">この記事のまとめ</div>
<div style="padding:16px;">
<ul style="margin:0;padding-left:1.2em;line-height:1.9;">
<li>要点1</li>
<li>要点2</li>
<li>要点3</li>
</ul>
</div>
</div>
```

### 4. CTAボタン
```html
<div style="text-align:center;margin:28px 0;">
<a href="リンク先URL" target="_blank" rel="nofollow noopener" style="display:inline-block;background:#1565c0;color:#fff;font-weight:bold;text-decoration:none;padding:16px 32px;border-radius:8px;box-shadow:0 3px 0 #0d47a1;">ボタン文言</a>
<div style="font-size:0.85em;color:#666;margin-top:8px;">※掲載内容は公式サイトの表示をご確認ください</div>
</div>
```
- `rel` はアフィリエイトリンクのとき `nofollow noopener`、通常の公式リンクは `noopener`
- ボタン文言はページ内で少しずつ変える（全部同じ文言にしない）

### 5. 注意・メモ枠（アフィリエイト明示ブロックにも使う）
```html
<div style="background:#fffde7;border-left:4px solid #fbc02d;padding:14px 16px;margin:20px 0;">
テキスト
</div>
```

### 6. ポイント枠（メイン色の囲み）
```html
<div style="background:#e8f0fe;border-left:4px solid #1565c0;padding:14px 16px;margin:20px 0;">
<strong>ポイント</strong><br>
テキスト
</div>
```

### 7. ピックアップボックス（通常モードのみ・ライトでは出力しない）
```html
<div style="background:#f5f5f5;border-radius:8px;padding:18px;margin:24px 0;">
<div style="font-weight:bold;margin-bottom:10px;">サービス名</div>
（バナー画像があればここに {{IMG:...}}）
<div style="line-height:1.9;">紹介文</div>
（CTAボタン）
</div>
```

### 8. 比較表
```html
<table style="border-collapse:collapse;width:100%;margin:20px 0;">
<tr><th style="background:#1565c0;color:#fff;padding:10px;border:1px solid #ddd;">項目</th><th style="background:#1565c0;color:#fff;padding:10px;border:1px solid #ddd;">内容</th></tr>
<tr><td style="padding:10px;border:1px solid #ddd;">…</td><td style="padding:10px;border:1px solid #ddd;">…</td></tr>
</table>
```

## 禁止

- AFFINGERショートコード（`[st-` で始まるもの・`[st_af]`）を出力しない
- `class="graybox"` `class="st-mymarker-s"` `class="hutoaka"` 等のテーマ依存クラスを使わない
- ふきだしは使わない（このセットでは非対応）
- 上記以外の装飾を自作しない（種類を増やさない）

## 密度ルール（AFFINGER版と共通）

- マーカーは記事全体で1箇所、強調は1〜2箇所
- 装飾のない本文段落を4つ以上連続させない（機械監査で検出される）
- 各H2はH3 2〜3個に分割し、H3ごとに装飾を配置する
- CTAボタンは各H2の直前とまとめ文末（WORKFLOW通り）
