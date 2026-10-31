# VERSION and the synchronized CPU manifest own displayed release identities.
function Get-SocReleaseHeaderText([string]$Root) {
    $version = ([IO.File]::ReadAllText((Join-Path $Root 'VERSION'))).Trim()
    if ($version -cnotmatch '^[0-9]+\.[0-9]+$') { throw 'Invalid SoC VERSION' }
    $cpu = Get-Content -LiteralPath (Join-Path $Root 'rtl/cpu/source.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($cpu.cpu_version -cnotmatch '^[0-9]+\.[0-9]+\.[0-9]+$') { throw 'Invalid synchronized CPU version' }
    $cpuDisplay = ([regex]::Match($cpu.cpu_version, '^[0-9]+\.[0-9]+')).Value
    return "#ifndef SOC_RELEASE_VERSION_H`n#define SOC_RELEASE_VERSION_H`n#define SOC_RELEASE_VERSION `"V$version`"`n#define CPU_RELEASE_VERSION `"V$cpuDisplay`"`n#endif`n"
}

function Write-SocReleaseHeader([string]$Root) {
    $path = Join-Path $Root 'sw/bootloader/release_version.h'
    [IO.File]::WriteAllText($path, (Get-SocReleaseHeaderText $Root), [Text.UTF8Encoding]::new($false))
}

function Assert-SocReleaseHeader([string]$Root) {
    $path = Join-Path $Root 'sw/bootloader/release_version.h'
    if (!(Test-Path -LiteralPath $path -PathType Leaf) -or
        [IO.File]::ReadAllText($path) -cne (Get-SocReleaseHeaderText $Root)) {
        throw 'Bootloader release header differs from VERSION or synchronized CPU source.json'
    }
}
