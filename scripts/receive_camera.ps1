[CmdletBinding()]
param(
    [string]$OutputDirectory = [Environment]::GetFolderPath('MyPictures'),
    [string]$ListenAddress = '0.0.0.0',
    [string]$BoardAddress = '192.168.1.50'
)

$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'camera_receiver.cs'
Add-Type -TypeDefinition ([IO.File]::ReadAllText($source)) `
    -ReferencedAssemblies @('System', 'System.Core', 'System.Drawing')
[CameraReceiver]::Run($OutputDirectory, $ListenAddress, $BoardAddress)
