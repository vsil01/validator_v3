Param(
    [string]$TargetPath = "${PSScriptRoot}\validator_config_wizard.bat",
    [string]$ShortcutPath = "${PSScriptRoot}\Validator Config Wizard.lnk"
)

$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = $PSScriptRoot
$Shortcut.Save()
Write-Host "Created shortcut: $ShortcutPath"
