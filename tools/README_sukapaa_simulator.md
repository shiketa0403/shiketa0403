# スカパー！料金シミュレーター

`sukapaa-simulator.html` は単独で動作するシミュレーターです。WordPress（AFFINGER）にはiframe方式で埋め込みます。

## 構成
- 単一HTMLファイル（CSS・JS内包、外部依存なし）
- 商品データ: セット7件 + チャンネル57件 = 64件
- 計算ロジック: 加入月/解約月から課金月数を算出 → (基本料 + 視聴料) × 課金月数
- 組み合わせ割引: 7ルール（同一対象に複数該当時は最安価格を採用）

## ローカル動作確認
```
cd tools
python3 -m http.server 8000
# ブラウザで http://localhost:8000/sukapaa-simulator.html
```

## WordPressへの埋め込み（iframe方式）

### 手順
1. `sukapaa-simulator.html` を WordPress のメディアにアップロード（または独自ドメイン配下にFTP等で配置）
2. アップロード先URL（例: `https://www.civichat.jp/wp-content/uploads/2026/05/sukapaa-simulator.html`）を控える
3. クラシックエディタの「テキスト」タブで挿入したい箇所に下記を貼り付ける

```html
<div style="max-width:760px;margin:0 auto;">
<iframe
  src="https://www.civichat.jp/wp-content/uploads/2026/05/sukapaa-simulator.html"
  style="width:100%;height:1400px;border:0;display:block;"
  loading="lazy"
  scrolling="auto"
  title="スカパー！料金シミュレーター">
</iframe>
</div>
```

### 高さ調整について
内部コンテンツに応じて自動リサイズしたい場合は、親ページとiframe間で `postMessage` をやり取りする方式を別途追加可能。最初は固定高（1400px程度）でモバイル/PC両方で見切れないか確認するのが確実。

### メディアアップロードでHTMLが拒否される場合
WordPressは標準でHTMLファイルのアップロードを許可していないことがある。対応策:
- functions.php に `upload_mimes` フィルタでHTMLを許可
- またはサーバーに直接FTP/SSHでアップロード
- またはサブドメインの静的サイトに置いて、そのURLをiframeに指定

## なぜiframe方式か
WordPress本文に直接 `<script>` を貼ると、Advanced Editor Tools（およびWPの自動整形）に削られる/壊されることが既知。iframe内であればHTML/CSS/JSは独立した文書として扱われ、テーマやエディタの干渉を受けない。
