param([string]$Title, [string]$Body)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$icon = New-Object System.Windows.Forms.NotifyIcon
try {
    $icon.Icon = [System.Drawing.SystemIcons]::Information
    $icon.Visible = $true
    $icon.BalloonTipTitle = $Title
    $icon.BalloonTipText = $Body
    $icon.ShowBalloonTip(7000)
    Start-Sleep -Seconds 8
} finally {
    $icon.Dispose()
}
