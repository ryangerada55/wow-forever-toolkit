<#
.SYNOPSIS
    Link addon folders from a dev checkout into a World of Warcraft flavor's
    Interface\AddOns folder. On Windows it creates directory junctions, which
    need neither admin rights nor Developer Mode.

.DESCRIPTION
    Runs on Windows PowerShell 5.1 and PowerShell 7. Commands:
      list    Show detected WoW installs and their flavor folders (default when
              no addon folder is given).
      link    Junction each addon into <root>\<flavor>\Interface\AddOns (default
              when an addon folder is given). A real folder that is in the way
              (for example a copy installed by CurseForge) is moved to
              <flavor>\Interface\AddOns-devsetup-backup\<Name>.<timestamp> first.
      unlink  Remove links that point at the given checkout. Never deletes a
              real folder. -Restore moves the newest backup back.
      status  Show what AddOns\<Name> currently is.

    Detection order: -WowRoot / $env:WOW_ROOT; Battle.net's product.db
    (%ProgramData%\Battle.net\Agent\product.db, then <drive>:\ProgramData\... on
    every drive, as WowUp does); the default
    "C:\Program Files (x86)\World of Warcraft" and "C:\Program Files\World of Warcraft".

    -Flavor accepts retail, ptr, xptr, beta, classic (MoP), era, anniversary,
    classic_ptr, era_ptr, forever, or a literal folder such as _classic_beta_.
    'forever' picks the folder whose product version (.build.info, product from
    the folder's .flavor.info or product.db) is 1.60 or later, or whose
    WTF\Config.wtf says lastAddonVersion 160xx, or _classic_beta_ (the Forever
    beta folder). If several folders match (for example the beta and the
    stress-test product, Oct 16-19), it lists them with product and build and
    stops: pass -Flavor _folder_ or -ForeverFolder. Forever's launch layout
    (2026-11-04) has not been announced: its own folder, a game type inside
    _retail_, or the beta slot. -ForeverFolder (or $env:WOW_FOREVER_FOLDER)
    pins what 'forever' means, for example _forever_ or _retail_.

    Version 1.2.0.

    Keep this file ASCII-only: Windows PowerShell 5.1 reads BOM-less files in
    the system ANSI code page.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\link-addons.ps1 list
.EXAMPLE
    .\link-addons.ps1 link -Flavor forever D:\dev\MyAddon -DryRun
.EXAMPLE
    .\link-addons.ps1 unlink -Flavor forever D:\dev\MyAddon -Restore
.EXAMPLE
    .\link-addons.ps1 link -Flavor forever -ForeverFolder _forever_ D:\dev\MyAddon
#>
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '', Justification = 'Interactive console tool')]
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Position = 0)]
    [string]$Command,

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$AddonPath,

    [string]$Flavor = $env:WOW_FLAVOR,

    [string]$WowRoot = $env:WOW_ROOT,

    [string]$ProductDb,

    # What 'forever' means: a folder such as _forever_ or an alias such as retail.
    [string]$ForeverFolder = $env:WOW_FOREVER_FOLDER,

    # Print what would happen; change nothing (same as -WhatIf).
    [switch]$DryRun,

    # unlink: move the newest backup back into AddOns.
    [switch]$Restore,

    # link: re-point a link that targets another checkout; unlink: remove it anyway.
    [switch]$Force,

    # Create a symbolic link instead of a junction (needs Developer Mode or an
    # elevated prompt; required for \\wsl.localhost\ or network-share checkouts).
    [switch]$Symlink
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
# parameters used by the functions below
$script:OptFlavor = $Flavor
$script:OptWowRoot = $WowRoot
$script:OptProductDb = $ProductDb
$script:OptRestore = [bool]$Restore
$script:OptForce = [bool]$Force
$script:OptSymlink = [bool]$Symlink
$script:OptForeverFolder = $ForeverFolder
if ($DryRun) {
    $WhatIfPreference = $true
    Write-Host 'Dry run: nothing will be changed.'
}

# --------------------------------------------------------------- platform
$script:NativeWindows = ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT)
# Test hooks: WOW_DEVSETUP_OS overrides the OS (Windows/Darwin/Linux) and
# WOW_DEVSETUP_TEST_PREFIX is prepended to built-in default paths (C:\x -> <prefix>/C/x).
$script:OsName = $env:WOW_DEVSETUP_OS
if (-not $script:OsName) {
    if ($script:NativeWindows) { $script:OsName = 'Windows' }
    elseif (Test-Path -LiteralPath '/System/Library/CoreServices') { $script:OsName = 'Darwin' }
    else { $script:OsName = 'Linux' }
}
$script:TestPrefix = $env:WOW_DEVSETUP_TEST_PREFIX
if ($script:NativeWindows) {
    $script:PathCompare = [StringComparison]::OrdinalIgnoreCase
} else {
    $script:PathCompare = [StringComparison]::Ordinal
}

$KnownFlavors = @('_retail_', '_ptr_', '_xptr_', '_beta_', '_classic_', '_classic_era_',
    '_anniversary_', '_classic_ptr_', '_classic_era_ptr_', '_classic_beta_')

function Exit-WithError([string]$Message) {
    Write-Host "error: $Message" -ForegroundColor Red
    exit 1
}

function Write-Warn([string]$Message) {
    Write-Host "warning: $Message" -ForegroundColor Yellow
}

# Map a built-in default path into the test prefix (no-op unless the hook is set)
function ConvertTo-TestPath([string]$Path) {
    if (-not $script:TestPrefix) { return $Path }
    if ($Path -match '^([A-Za-z]):[\\/](.*)$') {
        $rest = $Matches[2] -replace '\\', '/'
        return (Join-Path $script:TestPrefix ($Matches[1].ToUpper() + '/' + $rest))
    }
    if ($Path.StartsWith('/')) { return $script:TestPrefix + $Path }
    return $Path
}

function Get-FullPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($full)
    if ($full.Length -gt $root.Length) { $full = $full.TrimEnd('\', '/') }
    return $full
}

function Test-SamePath([string]$A, [string]$B) {
    return [string]::Equals((Get-FullPath $A), (Get-FullPath $B), $script:PathCompare)
}

function Get-FlavorLabel([string]$Folder) {
    switch ($Folder) {
        '_retail_' { 'Retail (Midnight 12.x)' }
        '_ptr_' { 'Retail PTR' }
        '_xptr_' { 'Retail xPTR' }
        '_beta_' { 'Retail beta' }
        '_classic_' { 'MoP Classic (5.5.x)' }
        '_classic_era_' { 'Classic Era (1.15.x)' }
        '_anniversary_' { 'TBC Anniversary (2.5.x)' }
        '_classic_ptr_' { 'Classic PTR' }
        '_classic_era_ptr_' { 'Classic Era PTR' }
        '_classic_beta_' { 'WoW: Forever beta (wow_classic_beta)' }
        default { 'unknown flavor folder (new product? check for Forever)' }
    }
}

function Get-FlavorAlias([string]$Name) {
    switch ($Name.ToLowerInvariant()) {
        { $_ -in 'retail', 'mainline' } { return '_retail_' }
        'ptr' { return '_ptr_' }
        'xptr' { return '_xptr_' }
        'beta' { return '_beta_' }
        { $_ -in 'classic', 'mists', 'mop' } { return '_classic_' }
        { $_ -in 'era', 'classic_era', 'vanilla' } { return '_classic_era_' }
        { $_ -in 'anniversary', 'tbc' } { return '_anniversary_' }
        'classic_ptr' { return '_classic_ptr_' }
        { $_ -in 'era_ptr', 'classic_era_ptr' } { return '_classic_era_ptr_' }
        { $_ -in 'forever', 'camelot' } { return '@forever' }
    }
    if ($Name -match '^_.+_$') { return $Name }
    return $null
}

# SET lastAddonVersion "16001" from <flavor>\WTF\Config.wtf (instawow reads the same line)
function Get-LastAddonVersion([string]$FlavorPath) {
    $cfg = Join-Path (Join-Path $FlavorPath 'WTF') 'Config.wtf'
    if (-not (Test-Path -LiteralPath $cfg -PathType Leaf)) { return $null }
    foreach ($line in [IO.File]::ReadAllLines($cfg)) {
        if ($line -match '^SET lastAddonVersion\s+"?(\d+)"?') { return [int]$Matches[1] }
    }
    return $null
}

function Get-FlavorFolder([string]$Root) {
    Get-ChildItem -LiteralPath $Root -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^_.+_$' } | Sort-Object Name | ForEach-Object { $_.Name }
}

function Test-WowRoot([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Container)) { return $false }
    if (Test-Path -LiteralPath (Join-Path $Path '.build.info') -PathType Leaf) { return $true }
    foreach ($f in $KnownFlavors) {
        if (Test-Path -LiteralPath (Join-Path $Path $f) -PathType Container) { return $true }
    }
    foreach ($d in (Get-FlavorFolder $Path)) {
        if (Test-Path -LiteralPath (Join-Path (Join-Path $Path $d) '.flavor.info') -PathType Leaf) { return $true }
    }
    return $false
}

# ------------------------------------------------- products, versions, Forever
# WoW: Forever's launch layout (2026-11-04) is unannounced. Three cases are handled:
#   A  its own product and folder (the stress test runs as product 'wowf')
#   B  a game type inside the retail product, sharing _retail_
#   C  the beta slot (product wow_classic_beta, folder _classic_beta_)
# so 'forever' is resolved from evidence instead of a fixed folder name.

# root/folder/product triples collected from product.db
$script:ProductDbMap = New-Object System.Collections.ArrayList

# TACT product of a flavor folder: <folder>\.flavor.info (written by the Battle.net
# agent: a "Product Flavor!STRING:0" header line, then the product), else product.db.
function Get-FolderProduct([string]$Root, [string]$Folder) {
    $fi = Join-Path (Join-Path $Root $Folder) '.flavor.info'
    if (Test-Path -LiteralPath $fi -PathType Leaf) {
        foreach ($line in [IO.File]::ReadAllLines($fi)) {
            $l = $line.Trim()
            if (-not $l -or $l.StartsWith('#') -or $l.Contains('!')) { continue }
            $code = $l.Split('|')[0].Trim()
            if ($code) { return $code }
        }
    }
    foreach ($m in $script:ProductDbMap) {
        if ($m.Folder -eq $Folder -and (Test-SamePath $m.Root $Root)) { return $m.Code }
    }
    return $null
}

# All "product, version" rows of <root>\.build.info (BPSV; Active rows first)
function Get-BuildInfoRow([string]$Root) {
    $bi = Join-Path $Root '.build.info'
    $rows = @()
    if (-not (Test-Path -LiteralPath $bi -PathType Leaf)) { return $rows }
    $lines = [IO.File]::ReadAllLines($bi)
    if ($lines.Count -lt 2) { return $rows }
    $hdr = $lines[0].Split('|')
    $pi = -1; $vi = -1; $ai = -1
    for ($i = 0; $i -lt $hdr.Count; $i++) {
        if ($hdr[$i] -like 'Product!*') { $pi = $i }
        if ($hdr[$i] -like 'Version!*') { $vi = $i }
        if ($hdr[$i] -like 'Active!*') { $ai = $i }
    }
    if ($pi -lt 0 -or $vi -lt 0) { return $rows }
    foreach ($line in ($lines | Select-Object -Skip 1)) {
        $c = $line.Split('|')
        if ($c.Count -le [Math]::Max($pi, $vi) -or -not $c[$pi] -or -not $c[$vi]) { continue }
        $active = ($ai -ge 0 -and $c.Count -gt $ai -and $c[$ai] -eq '1')
        $rows += New-Object PSObject -Property @{ Product = $c[$pi]; Version = $c[$vi]; Active = $active }
    }
    return $rows
}

function Get-BuildInfoVersion([string]$Root, [string]$Product) {
    if (-not $Product) { return $null }
    $match = @(Get-BuildInfoRow $Root | Where-Object { $_.Product -eq $Product })
    if ($match.Count -eq 0) { return $null }
    $act = @($match | Where-Object { $_.Active })
    if ($act.Count -gt 0) { return $act[0].Version }
    return $match[0].Version
}

# 1.60.x up to 1.99.x is WoW: Forever (Classic Era is 1.15.x); same band as interface 16000-19999
function Test-ForeverBuild([string]$Version) {
    return ($Version -match '^1\.(6[0-9]|[7-9][0-9])\.')
}

# beta, PTR and internal products: never the live game
function Test-TestProduct([string]$Code) {
    return ($Code -match 'beta|ptr|alpha|dev|livetest' -or $Code -match '^(wowt|wowz|wowv[0-9]*|wowe[0-9]+)$')
}

# Why a folder looks like WoW: Forever; $null if it does not
function Get-ForeverEvidence([string]$Root, [string]$Folder) {
    $prod = Get-FolderProduct $Root $Folder
    $bver = Get-BuildInfoVersion $Root $prod
    if ($bver -and (Test-ForeverBuild $bver)) { return "product $prod $bver" }
    # A folder whose product is known to run another game is not Forever, whatever an old
    # Config.wtf says. _retail_ is the exception: Forever may share it (case B).
    if ($bver -and $Folder -ne '_retail_') { return $null }
    $v = Get-LastAddonVersion (Join-Path $Root $Folder)
    if ($null -ne $v -and $v -ge 16000 -and $v -lt 20000) { return "lastAddonVersion $v" }
    if ($Folder -eq '_classic_beta_') { return 'Forever beta folder' }
    return $null
}

function Get-ForeverCandidate([string]$Root) {
    $c = @()
    foreach ($d in (Get-FlavorFolder $Root)) {
        $why = Get-ForeverEvidence $Root $d
        if ($why) { $c += New-Object PSObject -Property @{ Folder = $d; Why = $why; Product = (Get-FolderProduct $Root $d) } }
    }
    return $c
}

# One line per Forever candidate: folder, product and build, and the evidence when it is not
# the product version (for the "pick one" messages)
function Get-CandidateLine([string]$Root) {
    $lines = @()
    foreach ($c in @(Get-ForeverCandidate $Root)) {
        if ($c.Product) {
            $bver = Get-BuildInfoVersion $Root $c.Product
            if (-not $bver) { $bver = '(not in .build.info)' }
            $text = "product $($c.Product) $bver"
        } else {
            $text = 'product unknown'
        }
        if (-not ($c.Why -like 'product*')) { $text += "; $($c.Why)" }
        $lines += ('      {0,-18} {1}' -f $c.Folder, $text)
    }
    return $lines
}

# Get-FlavorLabel, corrected by what the folder actually holds
function Get-FolderLabel([string]$Root, [string]$Folder) {
    $label = Get-FlavorLabel $Folder
    $why = Get-ForeverEvidence $Root $Folder
    if ($Folder -eq '_retail_') {
        if ($why) { $label = 'Retail + WoW: Forever (shared folder?)' }
    } elseif ($Folder -eq '_classic_beta_') {
        if (-not $why) { $label = 'Classic beta slot (not running Forever)' }
    } elseif ($why -and $label.StartsWith('unknown')) {
        $label = 'WoW: Forever (new folder)'
    }
    return $label
}

# Live products in .build.info with a Forever version that no folder could be tied to
function Get-UntiedForeverProduct([string]$Root) {
    $out = @()
    $folders = @(Get-FlavorFolder $Root)
    foreach ($r in (Get-BuildInfoRow $Root)) {
        if (-not (Test-ForeverBuild $r.Version) -or (Test-TestProduct $r.Product)) { continue }
        $tied = $false
        foreach ($d in $folders) { if ((Get-FolderProduct $Root $d) -eq $r.Product) { $tied = $true } }
        if (-not $tied) { $out += ('{0} {1}' -f $r.Product, $r.Version) }
    }
    return $out
}

# ------------------------------------------------------ product.db (protobuf)
# repeated field 1 = product install { 2: product code, 3: settings { 1: install
# path, 13: game subfolder }, 6: family }. Field numbers as decoded by WowUp
# (src/common/wowup/product-db.ts).
function Read-Varint([byte[]]$Bytes, [ref]$Pos) {
    [long]$value = 0
    $shift = 0
    while ($Pos.Value -lt $Bytes.Length) {
        $b = $Bytes[$Pos.Value]
        $Pos.Value++
        $value = $value -bor ([long]($b -band 0x7F) -shl $shift)
        if (($b -band 0x80) -eq 0) { break }
        $shift += 7
    }
    return $value
}

function Skip-Field([byte[]]$Bytes, [ref]$Pos, [long]$WireType) {
    switch ($WireType) {
        0 { [void](Read-Varint $Bytes $Pos) }
        1 { $Pos.Value += 8 }
        2 { $len = Read-Varint $Bytes $Pos; $Pos.Value += $len }
        5 { $Pos.Value += 4 }
        default { $Pos.Value = $Bytes.Length }
    }
}

function Read-ProductDb([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    $utf8 = [Text.Encoding]::UTF8
    $pos = 0
    $result = @()
    while ($pos -lt $bytes.Length) {
        $key = Read-Varint $bytes ([ref]$pos)
        if (($key -shr 3) -ne 1 -or ($key -band 7) -ne 2) { Skip-Field -Bytes $bytes -Pos ([ref]$pos) -WireType ($key -band 7); continue }
        $len = Read-Varint $bytes ([ref]$pos)
        $end = $pos + $len
        $prod = @{ Code = ''; Family = ''; Location = ''; Subfolder = '' }
        while ($pos -lt $end) {
            $k2 = Read-Varint $bytes ([ref]$pos)
            if (($k2 -band 7) -ne 2) { Skip-Field -Bytes $bytes -Pos ([ref]$pos) -WireType ($k2 -band 7); continue }
            $l2 = Read-Varint $bytes ([ref]$pos)
            $s2 = $pos
            $e2 = $pos + $l2
            switch ($k2 -shr 3) {
                2 { $prod.Code = $utf8.GetString($bytes, $s2, $l2) }
                6 { $prod.Family = $utf8.GetString($bytes, $s2, $l2) }
                3 {
                    while ($pos -lt $e2) {
                        $k3 = Read-Varint $bytes ([ref]$pos)
                        if (($k3 -band 7) -ne 2) { Skip-Field -Bytes $bytes -Pos ([ref]$pos) -WireType ($k3 -band 7); continue }
                        $l3 = Read-Varint $bytes ([ref]$pos)
                        if (($k3 -shr 3) -eq 1) { $prod.Location = $utf8.GetString($bytes, $pos, $l3) }
                        elseif (($k3 -shr 3) -eq 13) { $prod.Subfolder = $utf8.GetString($bytes, $pos, $l3) }
                        $pos += $l3
                    }
                }
            }
            $pos = $e2
        }
        $pos = $end
        if ($prod.Family -eq 'wow' -or $prod.Code.StartsWith('wow')) { $result += New-Object PSObject -Property $prod }
    }
    return $result
}

# --------------------------------------------------------- root detection
$script:Roots = New-Object System.Collections.ArrayList

function Add-Root([string]$Path, [string]$Source) {
    if (-not (Test-WowRoot $Path)) { return }
    $full = Get-FullPath $Path
    foreach ($r in $script:Roots) {
        if ([string]::Equals($r.Path, $full, $script:PathCompare)) {
            if ($r.Source -notlike "*$Source*") { $r.Source = "$($r.Source), $Source" }
            return
        }
    }
    [void]$script:Roots.Add((New-Object PSObject -Property @{ Path = $full; Source = $Source }))
}

function Find-WowRoot {
    if ($script:OptWowRoot) {
        if (-not (Test-WowRoot $script:OptWowRoot)) {
            Exit-WithError "-WowRoot '$script:OptWowRoot' does not look like a WoW install (no .build.info or _retail_/_classic_*_ folders)"
        }
        Add-Root $script:OptWowRoot '-WowRoot'
        return
    }
    $dbs = @()
    if ($script:OptProductDb) {
        if (-not (Test-Path -LiteralPath $script:OptProductDb -PathType Leaf)) { Write-Warn "product.db not found: $script:OptProductDb" }
        $dbs += $script:OptProductDb
    } elseif ($script:OsName -eq 'Windows') {
        $programData = $env:ProgramData
        if (-not $programData -or $script:TestPrefix) { $programData = 'C:\ProgramData' }
        $dbs += (ConvertTo-TestPath ([IO.Path]::Combine($programData, 'Battle.net\Agent\product.db')))
        # WowUp scans every drive for <drive>\ProgramData\Battle.net\Agent\product.db
        if ($script:TestPrefix) {
            $letters = Get-ChildItem -LiteralPath $script:TestPrefix -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match '^[A-Za-z]$' } | ForEach-Object { $_.Name + ':\' }
        } else {
            $letters = Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue | ForEach-Object { $_.Root }
        }
        foreach ($l in $letters) { $dbs += (ConvertTo-TestPath ([IO.Path]::Combine($l, 'ProgramData\Battle.net\Agent\product.db'))) }
    } elseif ($script:OsName -eq 'Darwin') {
        $dbs += (ConvertTo-TestPath '/Users/Shared/Battle.net/Agent/product.db')
    }
    foreach ($db in ($dbs | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $db -PathType Leaf)) { continue }
        try {
            foreach ($p in (Read-ProductDb $db)) {
                if (-not $p.Location) { continue }
                $loc = ConvertTo-TestPath $p.Location
                Add-Root $loc 'product.db'
                # remember which product owns which folder (labels and 'forever' resolution)
                if ($p.Code -and $p.Subfolder -and (Test-WowRoot $loc)) {
                    [void]$script:ProductDbMap.Add((New-Object PSObject -Property @{ Root = (Get-FullPath $loc); Folder = $p.Subfolder; Code = $p.Code }))
                }
            }
        } catch {
            Write-Warn "could not read $db : $($_.Exception.Message)"
        }
    }
    if ($script:OsName -eq 'Windows') {
        $pf86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
        if (-not $pf86 -or $script:TestPrefix) { $pf86 = 'C:\Program Files (x86)' }
        $pf = $env:ProgramFiles
        if (-not $pf -or $script:TestPrefix) { $pf = 'C:\Program Files' }
        Add-Root (ConvertTo-TestPath ([IO.Path]::Combine($pf86, 'World of Warcraft'))) 'default path'
        Add-Root (ConvertTo-TestPath ([IO.Path]::Combine($pf, 'World of Warcraft'))) 'default path'
    } elseif ($script:OsName -eq 'Darwin') {
        Add-Root (ConvertTo-TestPath '/Applications/World of Warcraft') 'default path'
    }
}

# -ForeverFolder / $env:WOW_FOREVER_FOLDER as a folder name; $null (with a warning) if invalid
function Get-ForeverPin {
    $f = Get-FlavorAlias $script:OptForeverFolder
    if ($f -and $f -ne '@forever') { return $f }
    Write-Warn ("-ForeverFolder/WOW_FOREVER_FOLDER '{0}' must be a folder such as _forever_ or an alias such as retail" -f $script:OptForeverFolder)
    return $null
}

# Returns the folder, or $null when no folder qualifies or when several look like WoW: Forever.
# It never picks one of those by itself: from Oct 16 to Oct 19 the beta and the stress test are
# both installed and either may be the client you mean, and at launch the old beta folder may
# still be there. Test-ForeverAmbiguous tells the two $null cases apart.
function Resolve-FlavorFolder([string]$Root, [string]$Want, [switch]$Quiet) {
    if ($Want -ne '@forever') { return $Want }
    if ($script:OptForeverFolder) { return (Get-ForeverPin) }
    $cands = @(Get-ForeverCandidate $Root)
    if ($cands.Count -eq 1) { return $cands[0].Folder }
    if ($cands.Count -gt 1 -and -not $Quiet) {
        Write-Warn ("several folders in {0} look like WoW: Forever, so 'forever' is ambiguous:" -f $Root)
        foreach ($line in (Get-CandidateLine $Root)) { Write-Host $line }
        Write-Host "  Pick one: -Flavor _folder_ for this command, or -ForeverFolder _folder_ (or the environment variable"
        Write-Host "  WOW_FOREVER_FOLDER set to the folder) so that 'forever' means that folder. Uninstalling a client"
        Write-Host "  you no longer test on (the beta after Oct 19) makes 'forever' unambiguous again."
    }
    return $null
}

function Test-ForeverAmbiguous([string]$Root, [string]$Want) {
    if ($Want -ne '@forever' -or $script:OptForeverFolder) { return $false }
    return (@(Get-ForeverCandidate $Root).Count -gt 1)
}

# ------------------------------------------------------- addon discovery
function Get-TocBase([string]$FileName) {
    $base = [IO.Path]::GetFileNameWithoutExtension($FileName)
    return ($base -replace '[-_](Mainline|Standard|Classic|Vanilla|TBC|BCC|Wrath|WOTLKC|Cata|Mists|Camelot|Forever)$', '')
}

$script:Addons = New-Object System.Collections.ArrayList

function Add-AddonFolder([string]$Dir) {
    $tocs = @(Get-ChildItem -LiteralPath $Dir -Filter '*.toc' -File -Force -ErrorAction SilentlyContinue)
    if ($tocs.Count -eq 0) { return $false }
    $names = @($tocs | ForEach-Object { Get-TocBase $_.Name } | Select-Object -Unique)
    $leaf = Split-Path -Leaf $Dir
    $name = $null
    foreach ($n in $names) { if ($n -eq $leaf) { $name = $n } }
    if (-not $name) {
        if ($names.Count -ne 1) { Exit-WithError ("{0} has TOCs for several addon names ({1}) - pass the addon sub-folder instead" -f $Dir, ($names -join ' ')) }
        $name = $names[0]
        Write-Host "note: $leaf contains $name.toc, so it will be linked as AddOns\$name"
    }
    [void]$script:Addons.Add((New-Object PSObject -Property @{ Source = $Dir; Name = $name }))
    return $true
}

function Get-AddonList([string[]]$Paths) {
    foreach ($p in $Paths) {
        if (-not (Test-Path -LiteralPath $p -PathType Container)) { Exit-WithError "not a directory: $p" }
        $dir = Get-FullPath (Resolve-Path -LiteralPath $p).ProviderPath
        if (Add-AddonFolder $dir) { continue }
        $found = $false
        foreach ($sub in (Get-ChildItem -LiteralPath $dir -Directory -ErrorAction SilentlyContinue)) {
            if ($sub.Name.StartsWith('.')) { continue }
            $own = @(Get-ChildItem -LiteralPath $sub.FullName -Filter ($sub.Name + '*.toc') -File -ErrorAction SilentlyContinue)
            if ($own.Count -eq 0) { continue }
            if (Add-AddonFolder $sub.FullName) { $found = $true }
        }
        if (-not $found) { Exit-WithError "no .toc file in $p or its sub-folders" }
    }
}

# ------------------------------------------------------------ link state
function Get-EntryItem([string]$Path) {
    try { return (Get-Item -LiteralPath $Path -Force -ErrorAction Stop) } catch { $null = $_ }
    # a dangling symlink may not resolve with Get-Item; look it up in the parent listing
    $parent = Split-Path -Parent $Path
    $leaf = Split-Path -Leaf $Path
    return (Get-ChildItem -LiteralPath $parent -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq $leaf } | Select-Object -First 1)
}

# junction or symbolic link? (LinkType exists on PS 5.1 and 7; fall back to the attribute)
function Test-IsLink($Item) {
    $lt = $Item.PSObject.Properties['LinkType']
    if ($lt) { return ($lt.Value -in 'Junction', 'SymbolicLink') }
    return [bool]($Item.Attributes -band [IO.FileAttributes]::ReparsePoint)
}

function Get-LinkTarget($Item) {
    $prop = $Item.PSObject.Properties['Target']
    if (-not $prop) { return $null }
    $t = @($prop.Value) | Where-Object { $_ } | Select-Object -First 1
    if (-not $t) { return $null }
    $t = [string]$t
    if ($t.StartsWith('\??\')) { $t = $t.Substring(4) }
    if (-not [IO.Path]::IsPathRooted($t)) { $t = Join-Path (Split-Path -Parent $Item.FullName) $t }
    return (Get-FullPath $t)
}

# returns @{ State = missing|link-ok|link-other|dangling|dir|file; Target = ... }
function Get-TargetState([string]$Path, [string]$Source) {
    $item = Get-EntryItem $Path
    if ($null -eq $item) { return @{ State = 'missing'; Target = $null } }
    if (Test-IsLink $item) {
        $target = Get-LinkTarget $item
        if (-not $target -or -not (Test-Path -LiteralPath $target)) { return @{ State = 'dangling'; Target = $target } }
        if (Test-SamePath $target $Source) { return @{ State = 'link-ok'; Target = $target } }
        return @{ State = 'link-other'; Target = $target }
    }
    if ($item.PSIsContainer) { return @{ State = 'dir'; Target = $null } }
    return @{ State = 'file'; Target = $null }
}

# --------------------------------------------------------------- actions
function Invoke-Step {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param([string]$Target, [string]$Action, [scriptblock]$Body)
    if ($WhatIfPreference) {
        Write-Host "[dry-run] would: $Action"
    } elseif ($PSCmdlet.ShouldProcess($Target, $Action)) {
        Write-Host "+ $Action"
        & $Body
    }
}

function Invoke-CreateLink([string]$Path, [string]$Source) {
    if ($script:NativeWindows -and -not $script:OptSymlink) {
        $isUnc = $Source.StartsWith('\\')
        $isNetwork = $false
        if (-not $isUnc) {
            try { $isNetwork = ((New-Object IO.DriveInfo([IO.Path]::GetPathRoot($Source))).DriveType -eq [IO.DriveType]::Network) } catch { $isNetwork = $false }
        }
        if ($isUnc -or $isNetwork) {
            Write-Warn ("{0} is on a network or WSL path; junctions only work between local NTFS volumes. Re-run with -Symlink " -f $Source) +
                '(needs Developer Mode or an elevated prompt), or clone the checkout onto a local NTFS drive.'
            return $false
        }
    }
    $kind = 'Junction'
    if ($script:OptSymlink -or $script:OsName -ne 'Windows') { $kind = 'SymbolicLink' }
    $itemType = $kind
    if (-not $script:NativeWindows) {
        $itemType = 'SymbolicLink'
        if ($kind -eq 'Junction' -and -not $WhatIfPreference) {
            Write-Host '  (test mode: junctions need Windows, so a symbolic link is created instead)'
        }
    }
    try {
        Invoke-Step -Target $Path -Action "create $kind $Path -> $Source" -Body { [void](New-Item -ItemType $itemType -Path $Path -Target $Source -Force:$false) }
        return $true
    } catch {
        $msg = $_.Exception.Message
        if ($kind -eq 'Junction') {
            Write-Warn ("could not create a junction at {0} -> {1}: {2}" -f $Path, $Source, $msg)
            Write-Warn 'Junctions need no admin rights or Developer Mode, but both folders must be on local NTFS volumes (not FAT32/exFAT, not a network share). Fix the location, or retry with -Symlink from an elevated prompt or with Developer Mode on (Settings > For developers).'
            Write-Warn ('Manual equivalent in cmd.exe: mklink /J "{0}" "{1}"' -f $Path, $Source)
        } else {
            Write-Warn ("could not create a symbolic link at {0} -> {1}: {2}" -f $Path, $Source, $msg)
            Write-Warn 'Symbolic links need Developer Mode (Settings > For developers) or an elevated prompt. Without -Symlink a junction is used, which needs neither.'
        }
        return $false
    }
}

# removes only the link itself (junction or symlink), never the target's files
function Invoke-RemoveLink([string]$Path) {
    $item = Get-EntryItem $Path
    if ($null -eq $item -or -not (Test-IsLink $item)) {
        throw "refusing to remove $Path : it is not a junction or symbolic link"
    }
    Invoke-Step -Target $Path -Action "remove link $Path" -Body {
        if ($script:NativeWindows) {
            [IO.Directory]::Delete($Path, $false)
        } else {
            [IO.File]::Delete($Path)
        }
    }
}

# ------------------------------------------------------------- commands
function Show-List {
    $flt = $null
    if ($script:OptFlavor) { $flt = Get-FlavorAlias $script:OptFlavor }
    if ($script:Roots.Count -eq 0) {
        Write-Host 'No WoW install found. Pass -WowRoot "D:\Games\World of Warcraft".'
        exit 1
    }
    foreach ($r in $script:Roots) {
        Write-Host ("WoW install: {0}   (found via: {1})" -f $r.Path, $r.Source)
        $bi = Join-Path $r.Path '.build.info'
        if (Test-Path -LiteralPath $bi -PathType Leaf) {
            $lines = [IO.File]::ReadAllLines($bi)
            if ($lines.Count -gt 1) {
                $hdr = $lines[0].Split('|')
                $pi = -1; $vi = -1
                for ($i = 0; $i -lt $hdr.Count; $i++) {
                    if ($hdr[$i] -like 'Product!*') { $pi = $i }
                    if ($hdr[$i] -like 'Version!*') { $vi = $i }
                }
                if ($pi -ge 0 -and $vi -ge 0) {
                    foreach ($line in ($lines | Select-Object -Skip 1)) {
                        $c = $line.Split('|')
                        if ($c.Count -gt [Math]::Max($pi, $vi) -and $c[$pi]) {
                            Write-Host ("    .build.info product {0,-22} version {1}" -f $c[$pi], $c[$vi])
                        }
                    }
                }
            }
        }
        foreach ($d in (Get-FlavorFolder $r.Path)) {
            if ($flt -and $flt -ne '@forever' -and $flt -ne $d) { continue }
            $v = Get-LastAddonVersion (Join-Path $r.Path $d)
            $ver = ''
            if ($null -ne $v) { $ver = ", lastAddonVersion $v" }
            $label = Get-FolderLabel $r.Path $d
            $prod = Get-FolderProduct $r.Path $d
            $info = ''
            if ($prod) {
                $info = ", product $prod"
                $bver = Get-BuildInfoVersion $r.Path $prod
                if ($bver) { $info += " $bver" }
            }
            $addons = Join-Path (Join-Path (Join-Path $r.Path $d) 'Interface') 'AddOns'
            if (Test-Path -LiteralPath $addons -PathType Container) {
                $entries = @(Get-ChildItem -LiteralPath $addons -Force -ErrorAction SilentlyContinue)
                $links = @($entries | Where-Object { Test-IsLink $_ } | ForEach-Object { $_.Name })
                $linkText = ''
                if ($links.Count -gt 0) { $linkText = ', dev links: ' + ($links -join ' ') }
                Write-Host ("  {0,-18} {1,-40} AddOns: {2} folder(s){3}{4}{5}" -f $d, $label, $entries.Count, $ver, $info, $linkText)
            } else {
                Write-Host ("  {0,-18} {1,-40} (no {2} yet){3}{4}" -f $d, $label, (Join-Path 'Interface' 'AddOns'), $ver, $info)
            }
        }
        # what '-Flavor forever' would pick in this install, and why
        $f = Resolve-FlavorFolder $r.Path '@forever' -Quiet
        if ($f) {
            if ($script:OptForeverFolder) {
                $x = 'pinned by -ForeverFolder/WOW_FOREVER_FOLDER'
                if (-not (Test-Path -LiteralPath (Join-Path $r.Path $f) -PathType Container)) { $x += '; no such folder in this install' }
            } else {
                $x = Get-ForeverEvidence $r.Path $f
            }
            Write-Host ("  -Flavor forever -> {0} ({1})" -f $f, $x)
            if ($f -eq '_retail_') { Write-Host '     _retail_ is shared: addons linked there load in WoW: Forever and in retail (README, launch day)' }
        } else {
            $cands = @(Get-ForeverCandidate $r.Path)
            if ($cands.Count -gt 0) {
                Write-Host ("  -Flavor forever -> ambiguous: {0} (several folders look like WoW: Forever):" -f (($cands | ForEach-Object { $_.Folder }) -join ' '))
                foreach ($line in (Get-CandidateLine $r.Path)) { Write-Host $line }
                Write-Host '     pick one: -Flavor _folder_, or -ForeverFolder _folder_ (or the environment variable WOW_FOREVER_FOLDER)'
            } else {
                Write-Host '  -Flavor forever -> no WoW: Forever folder found in this install'
            }
        }
    }
    Write-Host "Note: WoW: Forever's launch layout (2026-11-04) is unannounced: the beta uses _classic_beta_,"
    Write-Host 'the stress test is product wowf (its own folder). With both installed, link into each one by'
    Write-Host 'folder name (-Flavor _classic_beta_, -Flavor _forever_). If Forever runs from _retail_, use -ForeverFolder _retail_.'
}

function Get-Target {
    if (-not $script:OptFlavor) { Exit-WithError "-Flavor is required (e.g. -Flavor forever, -Flavor retail, -Flavor _classic_beta_). Run 'link-addons.ps1 list' to see folders." }
    $want = Get-FlavorAlias $script:OptFlavor
    if (-not $want) { Exit-WithError "unknown flavor '$script:OptFlavor'" }
    if ($script:Roots.Count -eq 0) { Exit-WithError 'no WoW install found; pass -WowRoot "D:\Games\World of Warcraft"' }
    $hits = @()
    $ambiguous = $false
    foreach ($r in $script:Roots) {
        $f = Resolve-FlavorFolder $r.Path $want
        if (Test-ForeverAmbiguous $r.Path $want) { $ambiguous = $true }
        elseif ($f -and (Test-Path -LiteralPath (Join-Path $r.Path $f) -PathType Container)) {
            $hits += New-Object PSObject -Property @{ Root = $r.Path; Folder = $f }
        }
    }
    if ($ambiguous) { Exit-WithError ("'{0}' is ambiguous (the folders are listed above); nothing was changed. Pass -Flavor _folder_, or -ForeverFolder _folder_ (or set the environment variable WOW_FOREVER_FOLDER)." -f $script:OptFlavor) }
    if ($hits.Count -eq 0) { Exit-WithError ("flavor '{0}' not found in: {1} (run 'link-addons.ps1 list'; install/launch that client once, or pass -Flavor _folder_)" -f $script:OptFlavor, (($script:Roots | ForEach-Object { $_.Path }) -join '; ')) }
    if ($hits.Count -gt 1) { Exit-WithError "flavor '$script:OptFlavor' exists in several installs; pick one with -WowRoot" }
    $t = $hits[0]
    $addons = Join-Path (Join-Path (Join-Path $t.Root $t.Folder) 'Interface') 'AddOns'
    $why = Get-ForeverEvidence $t.Root $t.Folder
    $label = Get-FolderLabel $t.Root $t.Folder
    if ($want -eq '@forever') {
        if ($script:OptForeverFolder) {
            $why = 'pinned by -ForeverFolder/WOW_FOREVER_FOLDER'
        } elseif (-not ($why -like 'product*')) {
            $untied = @(Get-UntiedForeverProduct $t.Root)
            if ($untied.Count -gt 0) {
                Write-Warn (".build.info also lists {0}, but no folder could be tied to it; if that is WoW: Forever, pass -Flavor _its_folder_" -f ($untied -join ', '))
            }
        }
        if (-not $why) { $why = 'no Forever evidence' }
        Write-Host ("Target: {0}  [{1}] (forever: {2})" -f $addons, $label, $why)
    } else {
        Write-Host ("Target: {0}  [{1}]" -f $addons, $label)
    }
    # case B: one AddOns folder for two game types
    if ($t.Folder -eq '_retail_' -and ($want -eq '@forever' -or $why)) {
        Write-Warn ("WoW: Forever and retail share {0}: an addon linked here loads in both game types unless its TOC gates them (## AllowLoadGameType and ## ExcludeLoadGameType; PATCH_DAY.md, TOC rule)" -f $addons)
    }
    return $addons
}

function Invoke-Link {
    $addonsDir = Get-Target
    $rc = 0
    if (-not (Test-Path -LiteralPath $addonsDir -PathType Container)) {
        Invoke-Step -Target $addonsDir -Action "create folder $addonsDir" -Body { [void](New-Item -ItemType Directory -Path $addonsDir -Force) }
    }
    $backupRoot = Join-Path (Split-Path -Parent $addonsDir) 'AddOns-devsetup-backup'
    foreach ($a in $script:Addons) {
        $t = Join-Path $addonsDir $a.Name
        $prefix = $addonsDir.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
        if ($a.Source.StartsWith($prefix, $script:PathCompare)) {
            Write-Warn "$($a.Source) is inside the AddOns folder; refusing to link it to itself"; $rc = 1; continue
        }
        $s = Get-TargetState $t $a.Source
        switch ($s.State) {
            'link-ok' { Write-Host "ok: $($a.Name) already linked -> $($a.Source)" }
            'missing' { if (-not (Invoke-CreateLink $t $a.Source)) { $rc = 1 } }
            { $_ -in 'dangling', 'link-other' } {
                if ($s.State -eq 'link-other' -and -not $script:OptForce) {
                    Write-Warn "$t links to $($s.Target), not $($a.Source); re-run with -Force to re-point it"; $rc = 1
                } else {
                    Write-Host "re-pointing $($a.Name) (was -> $($s.Target))"
                    $removed = $true
                    try { Invoke-RemoveLink $t } catch { Write-Warn $_.Exception.Message; $rc = 1; $removed = $false }
                    if ($removed -and -not (Invoke-CreateLink $t $a.Source)) { $rc = 1 }
                }
            }
            { $_ -in 'dir', 'file' } {
                $bk = Join-Path $backupRoot ("{0}.{1}" -f $a.Name, (Get-Date -Format 'yyyyMMdd-HHmmss'))
                if (Test-Path -LiteralPath $bk) { $bk = "$bk.$PID" }
                Write-Host "$t is a real $($s.State) (installed copy?) - moving it to $bk"
                $moved = $true
                try {
                    if (-not (Test-Path -LiteralPath $backupRoot)) {
                        Invoke-Step -Target $backupRoot -Action "create folder $backupRoot" -Body { [void](New-Item -ItemType Directory -Path $backupRoot -Force) }
                    }
                    Invoke-Step -Target $t -Action "move $t -> $bk" -Body { Move-Item -LiteralPath $t -Destination $bk }
                } catch { Write-Warn "could not back up $t : $($_.Exception.Message)"; $rc = 1; $moved = $false }
                if ($moved -and -not (Invoke-CreateLink $t $a.Source)) { $rc = 1 }
            }
        }
    }
    if ($rc -eq 0 -and -not $WhatIfPreference) {
        Write-Host 'Done. Restart the game client after adding or renaming a .toc file; /reload is enough for Lua/XML edits.'
    }
    return $rc
}

function Invoke-Unlink {
    $addonsDir = Get-Target
    $rc = 0
    $backupRoot = Join-Path (Split-Path -Parent $addonsDir) 'AddOns-devsetup-backup'
    foreach ($a in $script:Addons) {
        $t = Join-Path $addonsDir $a.Name
        $s = Get-TargetState $t $a.Source
        # note: 'continue' inside a PowerShell switch only leaves the switch, so use a flag
        $skip = $false
        switch ($s.State) {
            { $_ -in 'link-ok', 'dangling' } { try { Invoke-RemoveLink $t } catch { Write-Warn $_.Exception.Message; $rc = 1; $skip = $true } }
            'link-other' {
                if (-not $script:OptForce) { Write-Warn "$t links to $($s.Target), not $($a.Source); left alone (use -Force to remove the link anyway)"; $rc = 1; $skip = $true }
                else { try { Invoke-RemoveLink $t } catch { Write-Warn $_.Exception.Message; $rc = 1; $skip = $true } }
            }
            'missing' { Write-Host "ok: nothing at $t" }
            { $_ -in 'dir', 'file' } { Write-Warn "$t is a real $($s.State), not a link; left alone"; $rc = 1; $skip = $true }
        }
        if ($skip) { continue }
        if ($script:OptRestore) {
            $newest = Get-ChildItem -LiteralPath $backupRoot -Force -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -like ($a.Name + '.[0-9]*') } | Sort-Object Name | Select-Object -Last 1
            if ($newest) {
                $from = $newest.FullName
                try { Invoke-Step -Target $from -Action "restore $from -> $t" -Body { Move-Item -LiteralPath $from -Destination $t } } catch { Write-Warn "could not restore $from : $($_.Exception.Message)"; $rc = 1 }
            } else {
                Write-Host "no backup of $($a.Name) to restore"
            }
        }
    }
    return $rc
}

function Show-Status {
    $addonsDir = Get-Target
    foreach ($a in $script:Addons) {
        $s = Get-TargetState (Join-Path $addonsDir $a.Name) $a.Source
        switch ($s.State) {
            'link-ok' { Write-Host "$($a.Name): linked -> $($a.Source)" }
            'link-other' { Write-Host "$($a.Name): link to another checkout -> $($s.Target)" }
            'dangling' { Write-Host "$($a.Name): BROKEN link -> $($s.Target)" }
            'dir' { Write-Host "$($a.Name): real folder (installed copy, not linked)" }
            'file' { Write-Host "$($a.Name): a file is in the way" }
            'missing' { Write-Host "$($a.Name): not present" }
        }
    }
    return 0
}

# ------------------------------------------------------------------ main
$paths = @()
if ($AddonPath) { $paths += $AddonPath }
$cmd = $Command
if ($cmd -and $cmd -notin 'list', 'link', 'unlink', 'status') {
    $paths = @($cmd) + $paths
    $cmd = $null
}
if (-not $cmd) {
    if ($paths.Count -gt 0) { $cmd = 'link' } else { $cmd = 'list' }
}

Find-WowRoot
$exitCode = 0
switch ($cmd) {
    'list' { Show-List }
    default {
        if ($paths.Count -eq 0) { Exit-WithError "$cmd needs at least one addon folder" }
        Get-AddonList $paths
        switch ($cmd) {
            'link' { $exitCode = Invoke-Link }
            'unlink' { $exitCode = Invoke-Unlink }
            'status' { $exitCode = Show-Status }
        }
    }
}
exit $exitCode
