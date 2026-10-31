param(
    [string]$Distro = 'pikafish-verify',
    [string]$OutputDir = '',
    [switch]$DisableGuiAutostart
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!$OutputDir) { $OutputDir = Join-Path $root 'build\vision\mac-conv-board' }
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path

function Convert-ToWslPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to WSL: $full"
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
        $Matches[2].Replace('\', '/')
}

$wslRoot = Convert-ToWslPath $root
$wslOutput = Convert-ToWslPath $OutputDir
$guiAutostartCommand = if ($DisableGuiAutostart) {
    'mv etc/init.d/S95pikafish etc/init.d/X95pikafish'
} else { ':' }
$command = @"
set -eu
cc=/opt/toolchain/bin/riscv32-linux-musl-gcc
strip=/opt/toolchain/bin/riscv32-linux-musl-strip
test -x "`$cc"
"`$cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -static \
  -ffunction-sections -fdata-sections -Wl,--gc-sections \
  -Wall -Wextra -Werror \
  '$wslRoot/linux/mac_accel/pango_mac_conv_window_test.c' \
  -o '$wslOutput/pango-mac-conv-window-test'
"`$cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -static \
  -ffunction-sections -fdata-sections -Wl,--gc-sections \
  -Wall -Wextra -Werror \
  '$wslRoot/linux/mac_accel/pango_mac_conv_compute_test.c' \
  -o '$wslOutput/pango-mac-conv-compute-test'
"`$cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -static -pthread \
  -ffunction-sections -fdata-sections -Wl,--gc-sections \
  -Wall -Wextra -Werror \
  '$wslRoot/linux/mac_accel/pango_mac_scheduler_test.c' \
  -o '$wslOutput/pango-mac-scheduler-test'
"`$cc" -std=gnu11 -march=rv32ima -mabi=ilp32 -Os -static \
  -ffunction-sections -fdata-sections -Wl,--gc-sections \
  -Wall -Wextra -Werror \
  '$wslRoot/linux/mac_accel/pango_mac_pool_test.c' \
  -o '$wslOutput/pango-mac-pool-test'
"`$strip" '$wslOutput/pango-mac-conv-window-test' \
  '$wslOutput/pango-mac-conv-compute-test' \
  '$wslOutput/pango-mac-scheduler-test' \
  '$wslOutput/pango-mac-pool-test'
tmp=`$(mktemp -d)
trap 'rm -rf -- "`$tmp"' EXIT
cd "`$tmp"
cpio -idmu --quiet < '$wslRoot/linux/boot/rootfs.cpio'
$guiAutostartCommand
# This initrd has no sysctl configuration. Avoid the unused startup pipeline.
if [ ! -e etc/sysctl.conf ] && \
   ! find etc/sysctl.d usr/local/lib/sysctl.d usr/lib/sysctl.d \
          lib/sysctl.d -maxdepth 1 -name '*.conf' -print -quit \
          2>/dev/null | grep -q .; then
  mv etc/init.d/S02sysctl etc/init.d/X02sysctl
  cat > etc/init.d/S02sysctl <<'EOF'
#!/bin/sh
# SYSCTL_NO_CONFIGS_SKIP: this immutable initrd contains no sysctl settings.
case "`$1" in
  start|restart|reload) printf 'Running sysctl: OK\n' ;;
esac
exit 0
EOF
  chmod 0755 etc/init.d/S02sysctl
fi
install -m 0755 '$wslOutput/pango-mac-conv-window-test' \
  usr/bin/pango-mac-conv-window-test
install -m 0755 '$wslOutput/pango-mac-conv-compute-test' \
  usr/bin/pango-mac-conv-compute-test
install -m 0755 '$wslOutput/pango-mac-scheduler-test' \
  usr/bin/pango-mac-scheduler-test
install -m 0755 '$wslOutput/pango-mac-pool-test' \
  usr/bin/pango-mac-pool-test
find . -print | LC_ALL=C sort | cpio -o -H newc --owner=0:0 --quiet \
  > '$wslOutput/rootfs.cpio'
sha256sum '$wslOutput/rootfs.cpio' \
  '$wslOutput/pango-mac-conv-window-test' \
  '$wslOutput/pango-mac-conv-compute-test' \
  '$wslOutput/pango-mac-scheduler-test' \
  '$wslOutput/pango-mac-pool-test' > '$wslOutput/sha256sums.txt'
printf '%s\n' MAC_CONV_ROOTFS_CANDIDATE_PASS
"@.Replace("`r`n", "`n")
$script = Join-Path $OutputDir 'build_rootfs.sh'
[IO.File]::WriteAllText($script, $command, [Text.UTF8Encoding]::new($false))
& wsl.exe -d $Distro -u root -- bash (Convert-ToWslPath $script)
if ($LASTEXITCODE -ne 0) { throw 'Convolution board rootfs build failed' }

# Candidate executables change the initrd length. Compile a matching DTB so
# Linux unpacks the entire archive instead of using the production range.
$rootfsPath = Join-Path $OutputDir 'rootfs.cpio'
$sourceDts = Join-Path $root 'linux\cpu_v2.dts'
$candidateDts = Join-Path $OutputDir 'cpu_v2.candidate.dts'
$candidateDtb = Join-Path $OutputDir 'cpu_v2.dtb'
$dtsText = [IO.File]::ReadAllText($sourceDts)
$startMatch = [regex]::Match($dtsText,
    'linux,initrd-start\s*=\s*<0x([0-9a-fA-F]+)>;')
$endMatches = [regex]::Matches($dtsText,
    'linux,initrd-end\s*=\s*<0x[0-9a-fA-F]+>;')
if (!$startMatch.Success -or $endMatches.Count -ne 1) {
    throw 'Unexpected initrd properties in source DTS'
}
$startAddress = [Convert]::ToInt64($startMatch.Groups[1].Value, 16)
if ($startAddress -ne 0x03000000) {
    throw ('Unexpected Linux initrd load address: 0x{0:x8}' -f $startAddress)
}
$endAddress = $startAddress + (Get-Item -LiteralPath $rootfsPath).Length
if ($endAddress -ge 0x18000000) {
    throw ('Candidate rootfs overlaps OpenSBI DDR at 0x{0:x8}' -f $endAddress)
}
$hexEnd = '{0:x8}' -f $endAddress
$candidateText = [regex]::Replace($dtsText,
    'linux,initrd-end\s*=\s*<0x[0-9a-fA-F]+>;',
    "linux,initrd-end = <0x$hexEnd>;")
[IO.File]::WriteAllText($candidateDts, $candidateText,
    [Text.UTF8Encoding]::new($false))
$ErrorActionPreference = 'Continue'
& wsl.exe -d $Distro -u root -- dtc -q -I dts -O dtb -o `
    (Convert-ToWslPath $candidateDtb) (Convert-ToWslPath $candidateDts) 2>$null
$dtcExit = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
if ($dtcExit -ne 0) { throw 'Candidate DTB build failed' }
& (Join-Path $PSScriptRoot 'test_mac_conv_stage2_initrd_contract.ps1') `
    -RootfsPath $rootfsPath -DtbPath $candidateDtb -Distro $Distro

Write-Output "Candidate rootfs: $rootfsPath"
Write-Output "Candidate DTB: $candidateDtb"
