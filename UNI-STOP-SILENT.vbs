' UNI-STOP-SILENT.vbs - launch UNI-STOP.bat without visible console
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c ""C:\LLM\UNI\UNI-STOP.bat""", 0, False
Set WshShell = Nothing
