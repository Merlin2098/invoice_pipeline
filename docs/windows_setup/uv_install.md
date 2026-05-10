# Install uv on Windows

Use this guide when you need a clear Windows setup path for uv in one of these
two modes:

- uv available normally in `PATH`
- uv managed through an approved corporate or manual installation path

This guide is intentionally split into `PATH` and corporate/manual flows so the
operational difference stays explicit.

## 1. uv When It Is Available in PATH

Use this path when `uv` is already installed normally and can be called
directly.

Verify:

```powershell
uv --version
Get-Command uv
```

Typical usage:

```powershell
uv sync --extra local --group dev-local
uv lock
uv tree
```

This is the simplest path for local developer machines.

Reference: https://docs.astral.sh/uv/getting-started/installation/

## 2. uv In Corporate or Restricted Environments

Use this path when:

- the approved `uv` installation is not in `PATH`
- the standalone installer is blocked
- you need an explicit, supportable command path

Before choosing one of the options below, verify what Python entrypoint is
available on the machine:

```powershell
Get-Command python
python -V
py -0p
Test-Path 'C:\Program Files\Python314\python.exe'
```

You do not need every command above to succeed. The goal is to confirm which
approved Python path or launcher is actually available in your environment.

### Option A: Use Python to Run uv

If Python is available but `uv` is not exposed as a standalone command:

```powershell
py -3 -m uv --version
```

If that works, you can operate uv through Python:

```powershell
py -3 -m uv sync --extra local --group dev-local
py -3 -m uv tree
```

This is the preferred corporate path when Python is the approved entrypoint.

If you want one reusable pattern for support and diagnostics, keep the command
explicit and consistent:

```powershell
& 'C:\Program Files\Python314\python.exe' -m uv --version
& 'C:\Program Files\Python314\python.exe' -m uv sync --extra local --group dev-local
& 'C:\Program Files\Python314\python.exe' -m uv tree
```

### Option B: Use an Approved Corporate uv Binary

If your company distributes a dedicated `uv.exe`, verify it directly:

```powershell
C:\approved-tools\uv\uv.exe --version
```

Then use it explicitly:

```powershell
C:\approved-tools\uv\uv.exe sync --extra local --group dev
C:\approved-tools\uv\uv.exe tree
```

### Option C: Install uv Through an Approved Python

If the approved flow is to install `uv` via Python rather than as a standalone
binary:

```powershell
& 'C:\Program Files\Python314\python.exe' -m pip install uv
& 'C:\Program Files\Python314\python.exe' -m uv --version
```

After that, continue to run uv through the same Python:

```powershell
& 'C:\Program Files\Python314\python.exe' -m uv sync --extra local --group dev-local
```

This keeps the execution path explicit and avoids depending on `PATH` changes or
on a separately installed `uv.exe`.

## 3. How This Repository Uses uv

The Windows repository scripts assume uv is available through one of the paths
above and then use it to drive the local environment.

Primary commands:

```powershell
.\scripts\windows\setup_env.ps1
.\scripts\windows\update_venv.ps1
```

Behavior:

- `setup_env.ps1` resolves Python automatically, validates uv, creates `.venv`
  if needed, and syncs the local environment
- `update_venv.ps1` refreshes the environment after dependency changes
- both wrappers prefer `python -m uv` for the selected interpreter and fall
  back to `uv.exe` from `PATH` when that is the only valid local installation
- the normal local uv workflow is `base + local + dev-local`
- cloud hosts default to `base + local + cloud + dev-local + dev-cloud`
- the default host profile is read from `.template-profile`
- cloud can still be forced explicitly:

```powershell
.\scripts\windows\update_venv.ps1 -Profile cloud
```

## 4. Uv Host Package Refresh Warning

Some Windows hosts or VS Code extensions inspect the active environment with
`python -m pip list` or similar `pip`-based commands when they refresh the
package view.

For uv-based hosts, that refresh can show a warning such as
`error refreshing packages` even when the project environment is healthy and
`uv sync` completed successfully.

Treat this as a host-tooling limitation first, not as proof that dependency
installation failed.

When validating a uv-based host, prefer these checks:

```powershell
py -3 -m uv sync --extra local --group dev-local
py -3 -m uv tree
py -3 -m uv pip list --python .\.venv\Scripts\python.exe
```

If those commands work and the project dependencies import correctly, the
environment is generally usable even if the host package view still shows a
refresh warning.

If the host must refresh packages through `pip`, enable `pip` inside the
project virtual environment as an optional compatibility workaround:

```powershell
.\.venv\Scripts\python.exe -m ensurepip --upgrade
.\.venv\Scripts\python.exe -m pip list
```

Do not treat this step as part of the default uv workflow. Use it only when the
host tooling requires `pip` for package inspection.

## 5. Quick Verification Commands

```powershell
uv --version
py -3 -m uv --version
.\scripts\windows\setup_env.ps1
.\scripts\windows\update_venv.ps1
```

Replace `C:\Program Files\Python314\python.exe` with the real approved Python
path on the machine whenever you use the explicit Python-driven examples above.
