' UNI-DESKTOP-SILENT.vbs - launch UNI-DESKTOP.bat without visible console
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c ""C:\LLM\UNI\UNI-DESKTOP.bat""", 0, False
Set WshShell = Nothing
