# dropcatch_jp.ps1 — Windows PowerShell 用ランチャー
#
# 使い方:
#   1) このファイルの「設定」部分を自分の値に書き換える
#   2) PowerShell で実行:
#        まず疎通確認（登録しない）:  .\dropcatch_jp.ps1 -Preflight
#        本番:                        .\dropcatch_jp.ps1
#
#   もし「スクリプトの実行が無効」と出たら、そのPowerShellウィンドウで一度だけ:
#        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

param([switch]$Preflight)

# ====================== 設定（ここを書き換える）======================
$env:VD_API_KEY    = "ここにValue DomainのAPIキー"
$env:VD_DOMAIN     = "example.jp"            # 取りたいドメイン

$env:VD_START_AT   = "2026-06-01T00:00:00"   # JST。この時刻まで待って自動開始（空なら即開始）
$env:VD_DEADLINE_SEC = "1800"                # 開始後この秒数で諦める（30分）
$env:VD_REG_INTERVAL = "2.0"                 # 登録リトライ間隔(秒)

$env:VD_YEARS      = "1"
$env:VD_WHOIS_PROXY = "1"                    # 1=Whois代理公開 / 0=自分の情報を公開

# 登録者情報（.jp はレジストリ必須なのは登録者のみ）
$env:VD_LASTNAME   = "Yamada"
$env:VD_FIRSTNAME  = "Taro"
$env:VD_ORG        = "personal"              # 個人は personal、法人は正式名称
$env:VD_COUNTRY    = "JP"
$env:VD_POSTALCODE = "530-0011"
$env:VD_STATE      = "Osaka"
$env:VD_CITY       = "Osaka-shi Kita-ku"
$env:VD_ADDRESS1   = "3-1 Ofuka-cho"
$env:VD_ADDRESS2   = ""
$env:VD_EMAIL      = "you@example.com"
$env:VD_PHONE      = "+81.676342727"         # 国際表記 +81.XXXXXXXXX
# ===================================================================

# python / python3 を自動判定
$py = "python"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Get-Command python3 -ErrorAction SilentlyContinue) { $py = "python3" }
    else {
        Write-Host "Python が見つかりません。https://www.python.org/ からインストールしてください。" -ForegroundColor Red
        exit 1
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $scriptDir "dropcatch_jp.py"

if ($Preflight) {
    & $py $target --preflight
} else {
    & $py $target
}
