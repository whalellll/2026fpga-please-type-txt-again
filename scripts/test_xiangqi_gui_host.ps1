param([string]$Distro = 'chiplab_sim')

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$full = [IO.Path]::GetFullPath($root)
if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
    throw "Cannot convert repository path to WSL: $full"
}
$wslRoot = '/mnt/' + $Matches[1].ToLowerInvariant() + '/' +
    $Matches[2].Replace('\', '/')

$command = @"
set -eu
cd '$wslRoot'
gcc -std=gnu11 -O2 -Wall -Wextra -Werror -DVIDEO_FB_LINUX_MMAP \
  -DXQ_TEST_NO_STALL \
  -Ilinux/pikafish/include -Isw/xiangqi -Isw/video \
  sim/test_xiangqi_gui_host.c \
  sw/xiangqi/xiangqi_fb_gui.c \
  sw/xiangqi/xiangqi_mouse_input.c \
  sw/xiangqi/xiangqi_pikafish_link.c \
  sw/xiangqi/xiangqi_search.c \
  -pthread -o /tmp/test_xiangqi_gui_reference
timeout 8 /tmp/test_xiangqi_gui_reference > /tmp/test_xiangqi_gui_reference.log

gcc -std=gnu11 -O2 -Wall -Wextra -Werror -DVIDEO_FB_LINUX_MMAP \
  -Ilinux/pikafish/include -Isw/xiangqi -Isw/video \
  sim/test_xiangqi_gui_host.c \
  linux/pikafish/xiangqi_fb_gui_linux.c \
  sw/xiangqi/xiangqi_mouse_input.c \
  sw/xiangqi/xiangqi_pikafish_link.c \
  sw/xiangqi/xiangqi_search.c \
  -pthread -o /tmp/test_xiangqi_gui_host
timeout 8 /tmp/test_xiangqi_gui_host | tee /tmp/test_xiangqi_gui_current.log
grep '^RASTER_FNV1A=' /tmp/test_xiangqi_gui_reference.log > /tmp/test_xiangqi_gui_reference.hash
grep '^RASTER_FNV1A=' /tmp/test_xiangqi_gui_current.log > /tmp/test_xiangqi_gui_current.hash
cmp /tmp/test_xiangqi_gui_reference.hash /tmp/test_xiangqi_gui_current.hash
echo XQ_GUI_RASTER_MATCH_PASS

gcc -std=gnu11 -O2 -Wall -Wextra -Werror \
  -Isw/xiangqi \
  linux/pikafish/xiangqi_gui_command_test.c \
  sw/xiangqi/xiangqi_gui_command.c \
  -o /tmp/test_xiangqi_gui_command
/tmp/test_xiangqi_gui_command
"@

& wsl.exe -d $Distro -- sh -lc $command
if ($LASTEXITCODE -ne 0) {
    throw 'Xiangqi host GUI regression failed'
}
Write-Output 'XIANGQI_GUI_HOST_REGRESSION_PASS'
