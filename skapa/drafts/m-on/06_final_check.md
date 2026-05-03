```html
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>装飾済み本文 - H2-7</title>
<style>
body { margin: 0; padding: 16px; font-family: -apple-system, sans-serif; background: #f5f5f5; }
textarea { width: 100%; height: 600px; font-family: monospace; font-size: 13px; white-space: pre-wrap; word-wrap: break-word; padding: 12px; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px; background: #fff; }
button { margin-top: 10px; padding: 10px 20px; background: #2196F3; color: #fff; border: none; border-radius: 4px; font-size: 14px; cursor: pointer; }
button:hover { background: #1976D2; }
button.copied { background: #4CAF50; }
</style>
</head>
<body>
<textarea id="content" readonly><h2>まとめ:放送日までにエムオンを契約する</h2>

エムオンをスカパー経由で契約すれば、<span class="st-mymarker-s"><strong>月1,199円(税込)で推しの番組を確実に視聴</strong></span>できます。

[st-mybox title="ポイント" webicon="st-svg-check-circle" color="#FFD54F" bordercolor="#FFD54F" bgcolor="#FFFDE7" borderwidth="2" borderradius="5" titleweight="bold" fontsize="" myclass="st-mybox-class" margin="25px 0 25px 0"]
<div class="maruck">
<ul>
<li>月額<strong>1,199円(税込)</strong>(視聴料770円+基本料429円)</li>
<li>最低1ヶ月分の支払いで解約OK</li>
<li>加入月は基本料・視聴料ともに0円</li>
<li>申込はB-CASカード番号があれば10分で完了</li>
<li>月初の契約ほど無料期間が長くなる</li>
</ul>
</div>
[/st-mybox]

月初の契約ほど無料期間が長くなるため、放送日が決まっているなら今日中の申込が最もお得です。

推しの放送日を逃さないために、B-CASカード番号を手元に用意してスカパー!公式のエムオン申込ページから契約を済ませましょう。

[st-mcbutton url="#" title="スカパー!公式でエムオンを申込む" rel="nofollow" webicon="" target="" color="#fff" bgcolor="#e53935" bgcolor_top="#f44336" bordercolor="#e57373" borderwidth="1" borderradius="10" fontweight="bold" fontsize="120" width="90" webicon_after="st-svg-chevron-right" shadow="#c62828" ref="on" mcbox_bg="#fafafa" mcbox_color="" mcbox_title="加入月は基本料・視聴料0円" beacon=""]※B-CASカード番号があれば10分で完了[/st-mcbutton]</textarea>
<button id="copyBtn" onclick="copyContent()">📋 コピー</button>
<script>
function copyContent() {
  const t = document.getElementById('content');
  navigator.clipboard.writeText(t.value).then(() => {
    const b = document.getElementById('copyBtn');
    b.textContent = '✅ コピー完了';
    b.classList.add('copied');
    setTimeout(() => { b.textContent = '📋 コピー'; b.classList.remove('copied'); }, 2000);
  });
}
</script>
</body>
</html>
```

✅ ここまで出力しました：H2-7 まとめ:放送日までにエムオンを契約する
全セクションの出力が完了しました。続けてフェーズ3（最終チェック）に進みます。

---

📋 フェーズ3：最終チェック

【装飾バランス】
- H2-1：テーブル1、クリップメモ1、ふきだし1、画像1 → 適切
- H2-2：テーブル1、クリップメモ1、マイボックス1 → 適切
- H2-3：クリップメモ2、タイムライン1、画像1、CTA1 → 適切（クリップメモは異なる種類で密集なし）
- H2-4：引用1、マイボックス1、ふきだし1 → 適切
- H2-5：マイボックス1、クリップメモ1 → 適切
- H2-6：クリップメモ2、ふきだし1 → 適切（クリップメモは異なる種類）
- H2-7：マイボックス1、CTA1 → 適切

【ふきだし使用回数】
- H2-1：1回（右配置）
- H2-2：0回
- H2-3：0回
- H2-4：1回（左配置）
- H2-5：0回
- H2-6：1回（右配置）
- 合計3回／連続使用なし／1セクション最大1回 → ルール遵守

【色装飾の使用バランス】
- 黄マーカー：3箇所（H2-1、H2-4、H2-7）→ 要点に絞り適切
- 太赤字：3箇所（H2-4、H2-5×2）→ 期限・注意に集中、適切
- 太字：全体に適切な分散、料金・サービス名・数字に使用 → 適切

【CTA位置の最終確認】
- リード文下：なし（プラン通り）
- H2-3末尾：MCボタン1つ（プラン通り）
- 記事末尾（H2-7内）：MCボタン1つ（プラン通り）
- アフィリエイト明示ブロック：H2-1冒頭（リード文下相当）に挿入済み

【画像挿入位置】
- 「チャンネルページ」: H2-1のH3-1料金内訳テーブル直下 → 配置済み
- 「スカパー公式」: H2-3のH3-2タイムライン直前 → 配置済み

【rel属性チェック】
- CTAボタン2箇所すべて `rel="nofollow"` 設定済み

修正箇所：なし