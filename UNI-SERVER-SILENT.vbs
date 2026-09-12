' UNI-SERVER-SILENT.vbs - launch UNI-SERVER.bat without visible console
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c ""C:\LLM\UNI\UNI-SERVER.bat""", 0, False
Set WshShell = Nothing
