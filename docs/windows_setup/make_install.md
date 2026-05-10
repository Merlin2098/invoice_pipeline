# Install GNU Make on Windows

Use this guide when you need a clear Windows setup path for:

- GNU Make with administrator rights and automatic `PATH` integration
- GNU Make without administrator rights using manual binaries and manual setup

This guide is intentionally split into `PATH` and corporate/manual flows so the
operational difference stays explicit.

## 1. GNU Make With Administrator Rights

Use this path when you control the machine and want `make.exe` installed in a
standard way that becomes available in `PATH`.

### Install Chocolatey

Open PowerShell as Administrator.

If needed, relax the execution policy for the current session:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
```

Install Chocolatey:

```powershell
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

Close and reopen PowerShell, then verify:

```powershell
choco --version
```

Reference: https://docs.chocolatey.org/en-us/choco/setup/

### Install Make With Chocolatey

```powershell
choco install make -y
```

Close and reopen PowerShell, then verify:

```powershell
make --version
Get-Command make
```

Expected behavior:

- `make` is available directly in `PATH`
- `scripts/windows/run_make.ps1` should resolve `make` from `PATH` first

Reference: https://community.chocolatey.org/packages/make

## 2. GNU Make Without Administrator Rights

Use this path when you cannot install system-wide tools and must keep the setup
inside a user-controlled folder.

### Option A: Use an Approved Corporate Binary Folder

If your company provides an approved `make.exe`, place it in a known location,
for example:

```text
C:\approved-tools\make\bin\make.exe
```

Verify it directly:

```powershell
C:\approved-tools\make\bin\make.exe --version
```

### Option B: Add the Binary Folder to the Current Session PATH

If session-level `PATH` changes are allowed:

```powershell
$env:Path = "C:\approved-tools\make\bin;$env:Path"
make --version
Get-Command make
```

This gives you a `PATH`-style workflow without requiring admin rights.

### Option C: Keep the Binary Out of PATH

If you want an explicit corporate path and do not want to touch `PATH`:

```powershell
C:\approved-tools\make\bin\make.exe test
C:\approved-tools\make\bin\make.exe package
```

Or use the repository wrapper:

```powershell
.\scripts\windows\run_make.ps1 -MakePath 'C:\approved-tools\make\bin\make.exe' test
```

### How the Template Wrapper Behaves

`scripts/windows/run_make.ps1` currently resolves make in this order:

1. `-MakePath` if you pass it explicitly
2. `make` already available in `PATH`
3. `where.exe make.exe`
4. filesystem discovery for `make.exe`

That means:

- admin installs through Chocolatey usually hit the `PATH` case
- corporate/manual installs can use `-MakePath` or be discovered from known folders

## 3. Recommended Operational Choices

For GNU Make:

- Prefer the Chocolatey install when admin rights are available and a normal
  `PATH` workflow is acceptable.
- Prefer the explicit binary + wrapper path when the machine is restricted.

## 4. Quick Verification Commands

```powershell
make --version
.\scripts\windows\run_make.ps1
.\scripts\windows\run_make.ps1 -n test
```

For ready-to-copy `make` command examples, see [make_cheatlist.md](make_cheatlist.md).

For uv installation and validation, see [uv_install.md](uv_install.md).
