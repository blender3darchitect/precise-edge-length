# SPDX-License-Identifier: GPL-3.0-or-later
<#
.SYNOPSIS
    Symlink this repo into Blender's user extensions folder for live development.

.DESCRIPTION
    Creates <AppData>/Blender Foundation/Blender/<version>/extensions/user_default/precise_edge_length
    pointing at this working copy, so edits take effect on the next add-on reload
    with no zip/install cycle.

    Uses a directory junction, which needs no elevation and no Developer Mode. Pass
    -Symlink to force a real symbolic link instead; that one does require Developer
    Mode (Settings > System > For developers) or an elevated shell.

.EXAMPLE
    ./dev/link.ps1 -BlenderVersion 5.2
    ./dev/link.ps1 -BlenderVersion 5.2 -Remove
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $BlenderVersion,

    [switch] $Remove,

    [switch] $Symlink
)

$ErrorActionPreference = 'Stop'

$source = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$extensionId = 'precise_edge_length'

$root = Join-Path $env:APPDATA "Blender Foundation\Blender\$BlenderVersion\extensions\user_default"
$target = Join-Path $root $extensionId

if ($Remove) {
    if (Test-Path $target) {
        # Delete the link itself. Remove-Item -Recurse would follow it into the
        # working copy and take the source with it.
        (Get-Item $target).Delete()
        Write-Host "Unlinked $target"
    } else {
        Write-Host "Nothing linked at $target"
    }
    return
}

if (-not (Test-Path $root)) {
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    Write-Host "Created $root"
}

if (Test-Path $target) {
    $item = Get-Item $target
    if ($item.LinkType -in @('SymbolicLink', 'Junction')) {
        $item.Delete()
    } else {
        throw "$target already exists and is a real folder. Move it aside first."
    }
}

$linkType = if ($Symlink) { 'SymbolicLink' } else { 'Junction' }
New-Item -ItemType $linkType -Path $target -Target $source | Out-Null

Write-Host ""
Write-Host "Linked ($linkType):" -ForegroundColor Green
Write-Host "  $target"
Write-Host "  -> $source"
Write-Host ""
Write-Host "In Blender $BlenderVersion :"
Write-Host "  1. Edit > Preferences > Get Extensions > Refresh"
Write-Host "  2. Enable 'Precise Edge Length' under Add-ons"
Write-Host "  3. In Edit Mode, the panel is in the sidebar (N) > Item > Edge Length"
