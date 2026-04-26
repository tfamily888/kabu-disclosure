' Hidden launcher for auto_start.bat
' This wrapper avoids the black console window flashing on PC startup.
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run """" & strPath & "\auto_start.bat""", 0, False
