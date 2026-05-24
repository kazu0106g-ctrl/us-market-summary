Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c ""E:\projects\us-market-summary\run.bat"" >> ""E:\projects\us-market-summary\run_log.txt"" 2>&1", 0, True
