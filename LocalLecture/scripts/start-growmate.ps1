param([switch]$NoBrowser, [switch]$Transcript)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $repoPath 'app\backend\.venv\Scripts\python.exe'
$backendPath = Join-Path $repoPath 'app\backend'
$frontendPath = Join-Path $repoPath 'app\frontend'
$url = 'http://127.0.0.1:8876'
$openUrl = if ($Transcript) { "$url/?transcript" } else { $url }

if ($Transcript) {
    $requiredModelFiles = @(
        'models\classroom-benchmark\funasr-runtime\llama-funasr-cli.exe',
        'models\classroom-benchmark\funasr\funasr-encoder-f16.gguf',
        'models\classroom-benchmark\funasr\qwen3-0.6b-q8_0.gguf'
    )
    foreach ($relativePath in $requiredModelFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $repoPath $relativePath))) {
            throw "缺少本地转写模型文件：$relativePath。请先下载并放入 LocalLecture/models/classroom-benchmark。"
        }
    }
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw '未找到 Python 环境。请先在 LocalLecture 目录运行 .\scripts\install.ps1。'
}
try {
    $existing = Invoke-RestMethod -Uri "$url/health" -TimeoutSec 2
    if ($existing.app -eq 'GrowMate') {
        Write-Host 'GrowMate 已在运行，正在打开浏览器。'
        if (-not $NoBrowser) { Start-Process $openUrl }
        exit 0
    }
    throw '8876 端口被其他服务使用。请先检查占用程序。'
} catch {
    if ($_.Exception.Message -like '*8876 端口*') { throw }
}

$distPath = Join-Path $frontendPath 'dist\index.html'
$rebuild = -not (Test-Path -LiteralPath $distPath)
if (-not $rebuild) {
    $builtAt = (Get-Item -LiteralPath $distPath).LastWriteTimeUtc
    $sourceFiles = Get-ChildItem -LiteralPath (Join-Path $frontendPath 'src') -Recurse -File
    $sourceFiles += Get-ChildItem -LiteralPath (Join-Path $frontendPath 'public') -Recurse -File
    $sourceFiles += Get-Item -LiteralPath (Join-Path $frontendPath 'index.html'), (Join-Path $frontendPath 'vite.config.ts'), (Join-Path $frontendPath 'package.json'), (Join-Path $frontendPath 'package-lock.json')
    $rebuild = [bool]($sourceFiles | Where-Object { $_.LastWriteTimeUtc -gt $builtAt } | Select-Object -First 1)
}
if ($rebuild) {
    Write-Host '正在构建 GrowMate 浏览器界面……'
    Push-Location $frontendPath
    try {
        if (-not (Test-Path -LiteralPath 'node_modules')) {
            & npm.cmd ci
            if ($LASTEXITCODE -ne 0) { throw '安装前端依赖失败，请检查网络。' }
        }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw '网页构建失败，请检查上面的错误。' }
    } finally { Pop-Location }
}

$dataPath = Join-Path $repoPath 'data'
New-Item -ItemType Directory -Path $dataPath -Force | Out-Null
$outLog = Join-Path $dataPath 'growmate-web.log'
$errLog = Join-Path $dataPath 'growmate-web.err.log'
$server = Start-Process -FilePath $pythonPath -ArgumentList '-m','meetingbro.growmate.web' -WorkingDirectory $backendPath -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($server.HasExited) { throw "服务启动失败，请检查 $errLog" }
        try {
            $health = Invoke-RestMethod -Uri "$url/health" -TimeoutSec 2
            if ($health.app -eq 'GrowMate') { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "服务启动超时，请检查 $errLog" }
    Write-Host "GrowMate 已启动：$url"
    Write-Host '请保留这个窗口。结束录音并看到“资源已释放”后，可按 Ctrl+C 关闭服务。'
    if (-not $NoBrowser) { Start-Process $openUrl }
    while (-not $server.HasExited) { Start-Sleep -Seconds 1 }
} finally {
    if (-not $server.HasExited) {
        Write-Host '正在停止服务；如有剩余录音，先等待转写与保存完成……'
        try {
            Invoke-RestMethod -Uri "$url/api/shutdown" -Method Post -Headers @{ 'X-GrowMate-Request' = '1' } -TimeoutSec 3 | Out-Null
        } catch { }
        for ($attempt = 0; $attempt -lt 620; $attempt++) {
            if ($server.HasExited) { break }
            Start-Sleep -Seconds 1
        }
        if (-not $server.HasExited) {
            & taskkill.exe /PID $server.Id /T /F 2>$null | Out-Null
            Write-Host '停止等待超时，已保存的文字下次启动可以恢复。'
        }
    }
}
