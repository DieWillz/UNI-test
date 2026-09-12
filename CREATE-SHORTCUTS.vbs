' CREATE-SHORTCUTS.vbs - create shortcuts on Desktop for all UNI launchers
' Names are in Latin to avoid encoding issues with WScript.
Set WshShell = CreateObject("WScript.Shell")
desktop = WshShell.SpecialFolders("Desktop")
root = "C:\LLM\UNI"
ico = root & "\uni.ico"

' 1. UNI-Start (full stack, silent)
Set s = WshShell.CreateShortcut(desktop & "\UNI-Start.lnk")
s.TargetPath = root & "\UNI-START-SILENT.vbs"
s.WorkingDirectory = root
s.Description = "Start UNI (LLM + WebUI + Desktop, all hidden)"
s.IconLocation = ico
s.Save

' 2. UNI-Stop
Set s = WshShell.CreateShortcut(desktop & "\UNI-Stop.lnk")
s.TargetPath = root & "\UNI-STOP-SILENT.vbs"
s.WorkingDirectory = root
s.Description = "Stop all UNI services"
s.IconLocation = ico
s.Save

' 3. UNI-Server (WebUI only, silent)
Set s = WshShell.CreateShortcut(desktop & "\UNI-Server.lnk")
s.TargetPath = root & "\UNI-SERVER-SILENT.vbs"
s.WorkingDirectory = root
s.Description = "Start WebUI server only (port 8787)"
s.IconLocation = ico
s.Save

' 4. UNI-Desktop (overlay only, silent)
Set s = WshShell.CreateShortcut(desktop & "\UNI-Desktop.lnk")
s.TargetPath = root & "\UNI-DESKTOP-SILENT.vbs"
s.WorkingDirectory = root
s.Description = "Start Electron overlay only"
s.IconLocation = ico
s.Save

' 5. UNI-Admin (open browser)
Set s = WshShell.CreateShortcut(desktop & "\UNI-Admin.lnk")
s.TargetPath = "http://127.0.0.1:8787"
s.Description = "Open UNI admin panel in browser"
s.IconLocation = ico
s.Save

' 6. UNI-Mobile (open mobile-control on LAN)
Set s = WshShell.CreateShortcut(desktop & "\UNI-Mobile.lnk")
s.TargetPath = "http://127.0.0.1:8787/mobile-control.html"
s.Description = "Open UNI mobile control page (touchpad + clipboard)"
s.IconLocation = ico
s.Save

WScript.Echo "UNI shortcuts created on Desktop: UNI-Start, UNI-Stop, UNI-Server, UNI-Desktop, UNI-Admin, UNI-Mobile."
