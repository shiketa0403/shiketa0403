# dropcatch_jp.ps1 — .jp ドロップキャッチ（PowerShellだけで動く完結版 / Python不要・git不要）
#
# 使い方:
#   1) 下の「設定」を自分の値に書き換えて保存
#   2) PowerShell で:
#        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#        .\dropcatch_jp.ps1 -Preflight   # まず疎通確認（登録しない）
#        .\dropcatch_jp.ps1              # 本番
#
#   ※ このPCの時計が日本時間(JST)である前提です（通常はそのままでOK）。
#   ※ 複数ドメイン対応。1つ取れたら残りを取りに行き続けます。

param([switch]$Preflight)

# ============================ 設定（ここを書き換える）============================
$VD_API_KEY      = "ここにValue DomainのAPIキー"

# 取りたいドメイン（複数OK）。1行に1つ、カンマ区切りで並べる。
$VD_DOMAINS = @(
    "example.jp",
    "example2.jp"
)

$VD_START_AT     = "2026-06-01T00:00:00"      # この時刻(JST)まで待って自動開始。即開始なら "" にする
$VD_DEADLINE_SEC = 1800                        # 開始後この秒数で諦める（1800=30分）
$VD_REG_INTERVAL = 2                            # 各リクエストの間隔(秒)

$VD_YEARS        = 1
$VD_WHOIS_PROXY  = 1                            # 1=Whois代理公開 / 0=自分の情報を公開

# 登録者情報（.jp はレジストリ必須なのは登録者のみ）。全ドメイン共通で使う。
$Registrant = @{
    firstname    = "Taro"
    lastname     = "Yamada"
    organization = "personal"                  # 個人は personal、法人は正式名称
    country      = "JP"
    postalcode   = "530-0011"
    state        = "Osaka"
    city         = "Osaka-shi Kita-ku"
    address1     = "3-1 Ofuka-cho"
    address2     = ""
    email        = "you@example.com"
    phone        = "+81.676342727"             # 国際表記 +81.XXXXXXXXX
    fax          = "+81.676342727"
}

$NS = @(
    "ns1.value-domain.com",
    "ns2.value-domain.com",
    "ns3.value-domain.com",
    "ns4.value-domain.com",
    "ns5.value-domain.com"
)
# ==============================================================================

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ErrorActionPreference = "Stop"

$base = "https://api.value-domain.com/v1"
$headers = @{ Authorization = "Bearer $VD_API_KEY" }

function Log($msg) { Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss.fff"), $msg) }

function Read-ErrBody($err) {
    try {
        $s = $err.Exception.Response.GetResponseStream()
        $r = New-Object IO.StreamReader($s)
        return $r.ReadToEnd()
    } catch { return "" }
}

# ドメイン文字列 → 送信ボディ(JSON) を作る
function Build-Body($domain) {
    $parts = $domain.ToLower().Trim(".").Split(".", 2)
    if ($parts.Count -ne 2) { return $null }
    $obj = @{
        registrar   = "GMO"
        sld         = $parts[0]
        tld         = $parts[1]
        years       = $VD_YEARS
        ns          = $NS
        whois_proxy = $VD_WHOIS_PROXY
        contact     = @{ registrant = $Registrant; admin = $Registrant; tech = $Registrant }
    }
    return ($obj | ConvertTo-Json -Depth 8)
}

# 対象ドメインを整える
$targets = @($VD_DOMAINS | ForEach-Object { $_.ToLower().Trim().Trim(".") } | Where-Object { $_ -ne "" })
if ($targets.Count -eq 0) { Write-Host "VD_DOMAINS が空です。" -ForegroundColor Red; exit 1 }

# ---- プリフライト ----
if ($Preflight) {
    Log "=== PREFLIGHT（登録しません）==="
    Log ("対象ドメイン({0}件): {1}" -f $targets.Count, ($targets -join ", "))
    foreach ($d in $targets) {
        if (-not (Build-Body $d)) { Log "  [警告] $d は形式が不正（example.jp の形にしてください）" }
    }
    Log "APIキー疎通確認 GET /domains ..."
    try {
        $r = Invoke-RestMethod -Method Get -Uri "$base/domains?limit=1" -Headers $headers
        Log "OK: APIキーは有効です。"
    } catch {
        $code = $null
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        if ($code -eq 401) { Log "NG: 401 認証失敗。APIキーを確認してください。" }
        else { Log ("応答 HTTP {0}: {1}" -f $code, (Read-ErrBody $_)) }
    }
    Log "=== PREFLIGHT 完了 ==="
    exit 0
}

# ---- 開始時刻まで待機 ----
if ($VD_START_AT -ne "") {
    $target = [datetime]::Parse($VD_START_AT)
    Log ("開始予定: {0} まで待機" -f $target.ToString("yyyy-MM-dd HH:mm:ss"))
    while ((Get-Date) -lt $target) {
        $remain = ($target - (Get-Date)).TotalSeconds
        if ($remain -gt 5) { Start-Sleep -Seconds ([Math]::Min($remain - 2, 30)) }
        else { Start-Sleep -Milliseconds 200 }
    }
    Log "開始時刻に到達。"
}

# ---- ドロップキャッチ本番 ----
$deadline = (Get-Date).AddSeconds($VD_DEADLINE_SEC)
Log ("ドロップキャッチ開始。締切 {0}" -f $deadline.ToString("HH:mm:ss"))
Log ("対象 {0}件を順番に再試行します（取れたものから確定 → 残りを継続）。" -f $targets.Count)

$remaining = [System.Collections.ArrayList]@($targets)
$caught = @()
$attempt = 0

while ($remaining.Count -gt 0 -and (Get-Date) -lt $deadline) {
    foreach ($d in @($remaining)) {
        if ((Get-Date) -ge $deadline) { break }
        $attempt++
        $body = Build-Body $d
        if (-not $body) { Log "[$d] 形式不正のためスキップ"; $remaining.Remove($d); continue }
        try {
            $resp = Invoke-RestMethod -Method Post -Uri "$base/domains" -Headers $headers -Body $body -ContentType "application/json"
            Log "*** [$d] 取得成功! ***"
            $resp | ConvertTo-Json -Depth 8 | Write-Host
            $caught += $d
            $remaining.Remove($d)
        } catch {
            $code = $null
            if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
            $snippet = (Read-ErrBody $_) -replace "`r`n", " "
            if ($snippet.Length -gt 140) { $snippet = $snippet.Substring(0, 140) }
            Log ("[#{0}][{1}] HTTP {2}: {3}" -f $attempt, $d, $code, $snippet)
            if ($code -eq 401) { Log "認証失敗(401)。APIキーが無効です。中止します。"; exit 2 }
        }
        Start-Sleep -Seconds $VD_REG_INTERVAL
    }
}

Log "=================================================="
if ($caught.Count -gt 0) { Log ("取得成功({0}件): {1}" -f $caught.Count, ($caught -join ", ")) }
if ($remaining.Count -gt 0) { Log ("取得できず({0}件): {1}" -f $remaining.Count, (($remaining) -join ", ")) }
Log "管理画面で確認してください。"
if ($remaining.Count -gt 0) { exit 1 } else { exit 0 }
