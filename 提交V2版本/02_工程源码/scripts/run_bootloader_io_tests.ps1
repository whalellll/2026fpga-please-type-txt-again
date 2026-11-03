param(
    [string]$HostGccPath = 'D:\LJL\WORK\msys64\mingw64\bin\gcc.exe'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (!(Test-Path -LiteralPath $HostGccPath -PathType Leaf)) {
    throw "Host GCC not found: $HostGccPath"
}
$compilerDirectory = Split-Path -Parent $HostGccPath
$savedPath = $env:PATH
$audioExe = Join-Path ([IO.Path]::GetTempPath()) `
    ('soc_audio_gain_' + [guid]::NewGuid().ToString('N') + '.exe')
$consoleExe = Join-Path ([IO.Path]::GetTempPath()) `
    ('soc_console_history_' + [guid]::NewGuid().ToString('N') + '.exe')
$cameraExe = Join-Path ([IO.Path]::GetTempPath()) `
    ('soc_camera_snapshot_' + [guid]::NewGuid().ToString('N') + '.exe')
$runtimeObj = Join-Path ([IO.Path]::GetTempPath()) `
    ('soc_camera_runtime_' + [guid]::NewGuid().ToString('N') + '.o')
$rangeExe = Join-Path ([IO.Path]::GetTempPath()) `
    ('soc_ddr_range_' + [guid]::NewGuid().ToString('N') + '.exe')
$coremarkExe = Join-Path ([IO.Path]::GetTempPath()) `
    ('soc_coremark_port_' + [guid]::NewGuid().ToString('N') + '.exe')
$flashExe = Join-Path ([IO.Path]::GetTempPath()) `
    ('soc_flash_autoboot_' + [guid]::NewGuid().ToString('N') + '.exe')
try {
    $env:PATH = $compilerDirectory + [IO.Path]::PathSeparator + $savedPath
    Push-Location $root
    try {
        & $HostGccPath -std=c99 -O2 -Wall -Wextra -Werror -fno-builtin `
            -ffunction-sections -fdata-sections '-Wl,--gc-sections' `
            sim/bootloader_flash_autoboot_test.c -o $flashExe
        if ($LASTEXITCODE -ne 0) { throw 'Flash autoboot host compile failed' }
        & $flashExe
        if ($LASTEXITCODE -ne 0) { throw 'Flash autoboot host test failed' }
        & $HostGccPath -std=c99 -O2 -Wall -Wextra -Werror -fno-builtin -I sw/coremark `
            sw/coremark/core_portme.c sim/coremark_port_test.c -o $coremarkExe
        if ($LASTEXITCODE -ne 0) { throw 'CoreMark port host compile failed' }
        & $coremarkExe
        if ($LASTEXITCODE -ne 0) { throw 'CoreMark port host test failed' }
        & $HostGccPath -std=c99 -Wall -Wextra -Werror -I sw/bootloader `
            sw/bootloader/audio_sample.c sim/bootloader_audio_gain_test.c `
            -o $audioExe
        if ($LASTEXITCODE -ne 0) { throw 'Audio gain host compile failed' }
        & $audioExe
        if ($LASTEXITCODE -ne 0) { throw 'Audio gain host test failed' }
        & $HostGccPath -std=c99 -Wall -Wextra -Werror -I sw/bootloader `
            sw/bootloader/console_line.c sim/bootloader_console_line_test.c `
            -o $consoleExe
        if ($LASTEXITCODE -ne 0) { throw 'Console history host compile failed' }
        & $consoleExe
        if ($LASTEXITCODE -ne 0) { throw 'Console history host test failed' }
        & $HostGccPath -std=c99 -O2 -fno-builtin -ffunction-sections -fdata-sections `
            -Wno-int-to-pointer-cast -Dread_mtime_ticks32=runtime_read_mtime_ticks32 `
            -Dconsole_puts=runtime_console_puts -Dconsole_getc_timeout=runtime_console_getc_timeout `
            -c sw/bootloader/runtime.c -o $runtimeObj
        if ($LASTEXITCODE -ne 0) { throw 'Production CRC host build failed' }
        & $HostGccPath -std=c99 -O2 -Wall -Wextra -Werror -fno-builtin `
            -ffunction-sections -fdata-sections '-Wl,--gc-sections' -I sw/bootloader `
            sim/bootloader_ddr_range_test.c $runtimeObj -o $rangeExe
        if ($LASTEXITCODE -ne 0) { throw 'DDR range host compile failed' }
        & $rangeExe
        if ($LASTEXITCODE -ne 0) { throw 'DDR range host test failed' }
        & $HostGccPath -std=c99 -O2 -Wall -Wextra -Werror -fno-builtin `
            -ffunction-sections -fdata-sections '-Wl,--gc-sections' `
            sim/bootloader_camera_snapshot_test.c sw/bootloader/crc32_fast.c `
            $runtimeObj -o $cameraExe
        if ($LASTEXITCODE -ne 0) { throw 'Camera snapshot host compile failed' }
        & $cameraExe
        if ($LASTEXITCODE -ne 0) { throw "Camera snapshot host test failed (exit $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
} finally {
    $env:PATH = $savedPath
    foreach ($testExe in @($audioExe, $consoleExe, $cameraExe, $runtimeObj, $rangeExe, $coremarkExe, $flashExe)) {
        if (Test-Path -LiteralPath $testExe) {
            Remove-Item -LiteralPath $testExe -Force
        }
    }
}
