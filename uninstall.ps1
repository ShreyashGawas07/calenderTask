# Removes everything CalendarDesk added outside its own folder. No prompts to keep it.
#   .\uninstall.ps1              keep your calendar data
#   .\uninstall.ps1 -RemoveData  also delete %APPDATA%\CalendarDesk
param([switch]$RemoveData)
$ErrorActionPreference = 'Continue'

Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like '*CalendarDesk.pyw*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host "Stopped CalendarDesk (PID $($_.ProcessId))" }

Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'CalendarDesk' -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) 'CalendarDesk.lnk') -ErrorAction SilentlyContinue
Write-Host 'Removed startup entry and Start-menu shortcut.'

$data = Join-Path $env:APPDATA 'CalendarDesk'
if ($RemoveData) {
    Remove-Item $data -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Deleted data folder $data"
} else {
    Write-Host "Your data is kept in $data (run with -RemoveData to delete it)."
}
Write-Host "You can now delete this folder: $(Split-Path -Parent $MyInvocation.MyCommand.Path)"
