' Launch_Anki_Deck_Creator.vbs — Silent Background Launcher (Zero Terminal)
Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)

' Check if virtual environment python exists
VenvPython = ScriptDir & "\.venv\Scripts\pythonw.exe"
If Not FSO.FileExists(VenvPython) Then
    VenvPython = "pythonw.exe"
End If

' Run UI server silently using pythonw (no console window)
WshShell.CurrentDirectory = ScriptDir
WshShell.Run """" & VenvPython & """ """ & ScriptDir & "\scripts\ui_server.py""", 0, False

' Give server a moment to start and open default browser
WScript.Sleep 1000
WshShell.Run "http://localhost:5050"
