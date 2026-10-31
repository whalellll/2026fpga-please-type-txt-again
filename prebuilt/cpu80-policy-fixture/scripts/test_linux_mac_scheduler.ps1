param(
    [string]$Distro = 'Ubuntu-22.04'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

$driverPath = Join-Path $root 'linux\mac_accel\kernel\pango_mac.c'
$uapiPath = Join-Path $root 'linux\mac_accel\pango_mac_uapi.h'
$patchPath = Join-Path $root 'linux\mac_accel\linux-5.14-integration.patch'
$runtimePath = Join-Path $root 'linux\pikafish\pikafish_mac_runtime.cpp'
$dtsPath = Join-Path $root 'linux\cpu_v2.dts'
$configPath = Join-Path $root 'linux\cpu_v2_defconfig.fragment'
foreach ($path in @($driverPath, $uapiPath, $patchPath, $runtimePath, $dtsPath,
                     $configPath)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Linux MAC scheduler source: $path"
    }
}

$driverText = [IO.File]::ReadAllText($driverPath)
$runtimeText = [IO.File]::ReadAllText($runtimePath)
$dtsText = [IO.File]::ReadAllText($dtsPath)
$configText = [IO.File]::ReadAllText($configPath)
foreach ($needle in @('struct pango_mac_file', 'PANGO_MAC_POOL_CONTEXTS',
                       'alloc_pages(GFP_KERNEL | __GFP_ZERO',
                       'mutex_lock_interruptible(&mac->run_lock)',
                       'PANGO_MAC_IOC_RUN', 'remap_pfn_range')) {
    if (!$driverText.Contains($needle)) {
        throw "Kernel scheduler contract missing: $needle"
    }
}
foreach ($needle in @('/dev/pango-mac0', 'PANGO_MAC_IOC_GET_INFO',
                       'PANGO_MAC_IOC_RUN', 'backend=legacy-devmem')) {
    if (!$runtimeText.Contains($needle)) {
        throw "Pikafish scheduler migration contract missing: $needle"
    }
}
if (!$dtsText.Contains('pango,cpu-alias = <0x9b000000>;')) {
    throw 'MAC scheduler CPU alias is missing from the DTS'
}
if (!$configText.Contains('CONFIG_PANGO_MAC_ACCEL=y')) {
    throw 'MAC scheduler is missing from the kernel config fragment'
}

$wslRoot = Convert-ToWslPath $root
$command = @"
set -eu
tmp=`$(mktemp -d)
trap 'rm -rf -- "`$tmp"' EXIT
cat > "`$tmp/uapi-size.c" <<'EOF'
#include "pango_mac_uapi.h"
_Static_assert(sizeof(struct pango_mac_info) == 64, "pango_mac_info ABI size");
_Static_assert(sizeof(struct pango_mac_job) == 64, "pango_mac_job ABI size");
int main(void) { return 0; }
EOF
cc -std=c11 -Wall -Wextra -Werror -I'$wslRoot/linux/mac_accel' \
  "`$tmp/uapi-size.c" -o "`$tmp/uapi-size"
"`$tmp/uapi-size"
g++ -std=c++17 -Wall -Wextra -Werror -pedantic -pthread \
  -DPIKAFISH_STAGEA_ACCEL -fsyntax-only \
  -iquote '$wslRoot/linux/pikafish' \
  '$wslRoot/linux/pikafish/pikafish_mac_runtime.cpp'
cc -std=gnu11 -Wall -Wextra -Werror -pthread -fsyntax-only \
  -I'$wslRoot/linux/mac_accel' \
  '$wslRoot/linux/mac_accel/pango_mac_scheduler_test.c'
cc -std=gnu11 -Wall -Wextra -Werror -fsyntax-only \
  -I'$wslRoot/linux/mac_accel' \
  '$wslRoot/linux/mac_accel/pango_mac_pool_test.c'
printf '%s\n' LINUX_MAC_SCHEDULER_TEST_PASS
"@.Replace("`r`n", "`n")

$command | wsl.exe -d $Distro -- bash -s
if ($LASTEXITCODE -ne 0) {
    throw 'Linux MAC scheduler host validation failed'
}
