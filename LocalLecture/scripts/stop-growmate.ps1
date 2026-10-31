param()
$ErrorActionPreference = 'Stop'
$url = 'http://127.0.0.1:8876'
try {
    $health = Invoke-RestMethod -Uri "$url/health" -TimeoutSec 3
} catch {
    Write-Host 'GrowMate 当前没有运行，无需停止。'
    exit 0
}
if ($health.app -ne 'GrowMate') {
    throw '8876 端口不是 GrowMate，不会停止其他程序。'
}
$connection = Get-NetTCPConnection -LocalPort 8876 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$serviceProcess = $null
if ($connection) {
    $serviceProcess = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
}
Write-Host '正在停止 GrowMate；如有剩余录音，将先完成转写与保存，请等待。'
Invoke-RestMethod -Uri "$url/api/shutdown" -Method Post -Headers @{ 'X-GrowMate-Request' = '1' } -TimeoutSec 5 | Out-Null
if ($serviceProcess -and -not $serviceProcess.WaitForExit(620000)) {
    throw '服务还未完成退出。请查看日志，暂不要强制关闭，以免丢失未保存的录音。'
}
Write-Host 'GrowMate 已收到退出请求，本地服务已停止。'
