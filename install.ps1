# Sets up CalendarDesk for the current user: a private Python environment and a Start-menu shortcut.
# Nothing is added to startup; turn that on in Settings if you want it.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $here '.venv'

if (-not (Test-Path (Join-Path $venv 'Scripts\pythonw.exe'))) {
    Write-Host 'Creating Python environment...'
    python -m venv $venv
}
Write-Host 'Installing packages...'
& (Join-Path $venv 'Scripts\python.exe') -m pip install -q -r (Join-Path $here 'requirements.txt')

$programs = [Environment]::GetFolderPath('Programs')
$lnk = Join-Path $programs 'CalendarDesk.lnk'
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($lnk)
# Use the main pythonw.exe so the app is one process; CalendarDesk.pyw loads packages from .venv.
$basePythonw = & (Join-Path $venv 'Scripts\python.exe') -c "import os,sys;print(os.path.join(sys.base_prefix,'pythonw.exe'))"
$s.TargetPath = $basePythonw
$s.Arguments = '"' + (Join-Path $here 'CalendarDesk.pyw') + '"'
$s.WorkingDirectory = $here
$s.Description = 'CalendarDesk desktop calendar'
$s.Save()

Write-Host "Done. Start CalendarDesk from the Start menu, or run:"
Write-Host "  `"$basePythonw`" `"$here\CalendarDesk.pyw`""
