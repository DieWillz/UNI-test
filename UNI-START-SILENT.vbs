' UNI-START-SILENT.vbs - launch UNI-START.bat without visible console
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c ""C:\LLM\UNI\UNI-START.bat""", 0, False
Set WshShell = Nothing
