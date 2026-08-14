$ErrorActionPreference = "SilentlyContinue"
$portOpen = Test-NetConnection -ComputerName 127.0.0.1 -Port 8787 -InformationLevel Quiet
if (-not $portOpen) {
    $env:PYTHONPATH = "C:\LLM\UNI"
    $env:UNI_WEBUI_PORT = "8787"
    Start-Process -FilePath "C:\LLM\python312\python.exe" -ArgumentList "C:\LLM\UNI\uni\webui\server.py" -WorkingDirectory "C:\LLM\UNI\uni" -WindowStyle Hidden
    Start-Sleep -Seconds 2
}
Start-Process "http://127.0.0.1:8787"
