# Make Cheatlist

Use the command style that matches your shell and how `make.exe` is installed.

## `make` available in `PATH`

Use this in PowerShell or Git Bash:

```bash
make treemap
make test
make package
make ai-refresh
```

## PowerShell without `make.exe` in `PATH`

Use the repository wrapper:

```powershell
.\scripts\windows\run_make.ps1 treemap
.\scripts\windows\run_make.ps1 test
.\scripts\windows\run_make.ps1 package
.\scripts\windows\run_make.ps1 ai-refresh
```

## PowerShell with an explicit corporate `make.exe`

Use the wrapper with the fixed binary path:

```powershell
.\scripts\windows\run_make.ps1 -MakePath 'C:\Users\user\tools\make\bin\make.exe' treemap
.\scripts\windows\run_make.ps1 -MakePath 'C:\Users\user\tools\make\bin\make.exe' test
.\scripts\windows\run_make.ps1 -MakePath 'C:\Users\user\tools\make\bin\make.exe' package
```

## Git Bash without `make.exe` in `PATH`

Call the PowerShell wrapper explicitly:

```bash
powershell.exe -ExecutionPolicy Bypass -File ./scripts/windows/run_make.ps1 treemap
powershell.exe -ExecutionPolicy Bypass -File ./scripts/windows/run_make.ps1 test
powershell.exe -ExecutionPolicy Bypass -File ./scripts/windows/run_make.ps1 package
```
