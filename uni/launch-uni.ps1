$ErrorActionPreference = "SilentlyContinue"
$portOpen = Test-NetConnection -ComputerName 127.0.0.1 -Port 8787 -InformationLevel Quiet
if (-not $portOpen) {
    Start-Process -FilePath "py" -ArgumentList "-3.12", "-m", "uni.webui.server" -WorkingDirectory "C:\LLM\UNI" -WindowStyle Hidden
    Start-Sleep -Seconds 2
}
Start-Process "http://127.0.0.1:8787"
