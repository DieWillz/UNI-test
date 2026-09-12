# Creates links only. Does not start UNI, models, devices or capture the screen.
# Uses the existing desktop launcher, which preserves the configured LM Studio
# provider instead of forcing the obsolete embedded Qwen model in UNI-START.bat.
$ErrorActionPreference = 'Stop'
$uniRoot = Split-Path -Parent $PSScriptRoot
$uniDesktop = [Environment]::GetFolderPath('Desktop')
$uniShell = New-Object -ComObject WScript.Shell
$uniLauncher = Join-Path $uniRoot 'UNI-DESKTOP-SILENT.vbs'
if (-not (Test-Path -LiteralPath $uniLauncher -PathType Leaf)) {
    throw "Existing UNI desktop launcher is missing: $uniLauncher"
}
$uniLinks = @(
    @{ Name = 'UNI-Open'; Target = "$env:WINDIR\System32\wscript.exe";
       Arguments = '"' + $uniLauncher + '"';
       Description = 'Start UNI WebUI and desktop. Start the configured LM Studio model separately.' },
    @{ Name = 'UNI-Panel'; Target = "$env:WINDIR\explorer.exe";
       Arguments = '"http://127.0.0.1:8787/"';
       Description = 'Open UNI admin after starting UNI-Open.' },
    @{ Name = 'UNI-Logs'; Target = "$env:WINDIR\explorer.exe";
       Arguments = '"' + (Join-Path $uniRoot 'runtime\logs') + '"';
       Description = 'Open UNI runtime logs.' }
)
foreach ($uniLink in $uniLinks) {
    $uniPath = Join-Path $uniDesktop ($uniLink.Name + '.lnk')
    if (Test-Path -LiteralPath $uniPath) {
        Write-Output "Preserved existing shortcut: $uniPath"
        continue
    }
    $uniShortcut = $uniShell.CreateShortcut($uniPath)
    $uniShortcut.TargetPath = $uniLink.Target
    $uniShortcut.Arguments = $uniLink.Arguments
    $uniShortcut.WorkingDirectory = $uniRoot
    $uniShortcut.Description = $uniLink.Description
    $uniIcon = Join-Path $uniRoot 'uni.ico'
    if (Test-Path -LiteralPath $uniIcon) { $uniShortcut.IconLocation = $uniIcon }
    $uniShortcut.Save()
    $uniSaved = $uniShell.CreateShortcut($uniPath)
    if (-not (Test-Path -LiteralPath $uniPath) -or
        $uniSaved.TargetPath -ne $uniLink.Target -or
        $uniSaved.Arguments -ne $uniLink.Arguments) {
        throw "Shortcut verification failed: $uniPath"
    }
    Write-Output "Created and read back: $uniPath"
}
