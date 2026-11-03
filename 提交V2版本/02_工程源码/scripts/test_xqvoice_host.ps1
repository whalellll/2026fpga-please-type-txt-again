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
cc -std=gnu11 -O2 -Wall -Wextra -Werror \
  -Ilinux/voice -Isw/xiangqi \
  sim/test_xqvoice_protocol.c \
  linux/voice/xqvoice_protocol.c linux/voice/xqvoice_notation.c \
  sw/xiangqi/xiangqi_search.c -o /tmp/test_xqvoice_protocol
/tmp/test_xqvoice_protocol
cc -std=gnu11 -O2 -Wall -Wextra -Werror \
  -Ilinux/voice sim/test_xqvoice_model.c \
  linux/voice/xqvoice_protocol.c linux/voice/xqvoice_model.c \
  linux/voice/xqvoice_features.c -o /tmp/test_xqvoice_model
/tmp/test_xqvoice_model
cc -std=gnu11 -O2 -Wall -Wextra -Werror \
  -Ilinux/voice sim/test_xqvoice_assembler.c \
  linux/voice/xqvoice_assembler.c -o /tmp/test_xqvoice_assembler
/tmp/test_xqvoice_assembler
cc -std=gnu11 -O2 -Wall -Wextra -Werror \
  -Ilinux/voice -fsyntax-only linux/voice/xqvoice_gui_ipc.c
cc -std=gnu11 -O2 -Wall -Wextra -Werror \
  -Ilinux/voice sim/test_xqvoice_gui_ipc.c \
  linux/voice/xqvoice_protocol.c linux/voice/xqvoice_client.c \
  linux/voice/xqvoice_gui_ipc.c -o /tmp/test_xqvoice_gui_ipc
/tmp/test_xqvoice_gui_ipc
"@

$command = $command.Replace("`r`n", "`n")
& wsl.exe -d $Distro -- bash -lc $command
if ($LASTEXITCODE -ne 0) {
    throw 'XQVoice host regression failed'
}
Write-Output 'XQVOICE_HOST_REGRESSION_PASS'
