' Withdream Agent Team - hidden launcher for the Slack server.
' Runs supervisor.ps1 (watch + auto-restart loop) with no console window.
' Registered in HKCU Run by autostart.ps1 so it starts at every logon.
' NOTE: keep this file ASCII and BOM-free - wscript cannot read a UTF-8 BOM.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & here & "\supervisor.ps1""", 0, False
