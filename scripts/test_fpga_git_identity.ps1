param([string]$PythonPath = 'D:\LJL\WORK\msys64\mingw64\bin\python3.exe')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$fixture = Join-Path $tempBase ('fpga-git-identity-' + [guid]::NewGuid().ToString('N'))
$utf8 = [Text.UTF8Encoding]::new($false)
$checks = 0
function Reject-Identity([scriptblock]$Action, [string]$Pattern) {
    $failure = ''
    try { & $Action | Out-Null } catch { $failure = $_.Exception.Message }
    if ($failure -notlike $Pattern) { throw "Expected $Pattern; got $failure" }
    $script:checks++
}
try {
    New-Item -ItemType Directory -Path (Join-Path $fixture 'rtl') -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $fixture 'VERSION'), '6.5', $utf8)
    [IO.File]::WriteAllText((Join-Path $fixture 'rtl/core.v'), '// SYNTHETIC ONLY', $utf8)
    [void](Read-FpgaGitBytes $fixture 'init --quiet')
    [void](Read-FpgaGitBytes $fixture 'add --all')
    [void](Read-FpgaGitBytes $fixture '-c user.name=Fixture -c user.email=fixture@invalid commit --quiet -m synthetic')
    $inputs = Get-FpgaHashMap $fixture @('VERSION','rtl/core.v')
    $identity = New-FpgaGitIdentity $fixture $inputs
    Assert-FpgaGitIdentity $fixture $inputs $identity
    $checks++
    $copy = $identity | ConvertTo-Json -Depth 6 | ConvertFrom-Json
    $copy.commit_sha1 = '0' * 40
    Reject-Identity { Assert-FpgaGitIdentity $fixture $inputs $copy } '*commit proof hash differs*'
    $copy = $identity | ConvertTo-Json -Depth 6 | ConvertFrom-Json
    $first = @($copy.tree_objects_base64.PSObject.Properties)[0].Name
    $copy.tree_objects_base64.$first = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes('changed'))
    Reject-Identity { Assert-FpgaGitIdentity $fixture $inputs $copy } '*tree proof hash differs*'
    [IO.File]::AppendAllText((Join-Path $fixture 'rtl/core.v'), ' uncommitted', $utf8)
    Reject-Identity { New-FpgaGitIdentity $fixture (Get-FpgaHashMap $fixture @('VERSION','rtl/core.v')) } '*differs from implementation commit*'
    [IO.File]::WriteAllText((Join-Path $fixture 'rtl/core.v'), '// SYNTHETIC ONLY', $utf8)
    [IO.File]::WriteAllText((Join-Path $fixture 'rtl/new.v'), '// untracked', $utf8)
    Reject-Identity { New-FpgaGitIdentity $fixture (Get-FpgaHashMap $fixture @('VERSION','rtl/new.v')) } '*not in implementation HEAD*'
    [IO.File]::WriteAllText((Join-Path $fixture 'README.md'), 'docs-only delivery update', $utf8)
    [void](Read-FpgaGitBytes $fixture 'add README.md')
    [void](Read-FpgaGitBytes $fixture '-c user.name=Fixture -c user.email=fixture@invalid commit --quiet -m docs-only')
    Assert-FpgaGitIdentity $fixture $inputs $identity
    $checks++
    $snapshotPath = Join-Path $fixture 'snapshot.json'
    [IO.File]::WriteAllText($snapshotPath, ([ordered]@{inputs=$inputs;implementation_git=$identity}|ConvertTo-Json -Depth 8), $utf8)
    $pythonCode = @'
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from verify_board_release import validate_implementation
root=Path(sys.argv[2])
snapshot=json.loads((root/"snapshot.json").read_text(encoding="utf-8"))
validate_implementation(snapshot,snapshot["implementation_git"]["commit_sha1"],root)
print("PYTHON_GIT_PROOF_REPLAY_PASS")
'@
    $pythonCode | & $PythonPath -B - $PSScriptRoot $fixture
    if ($LASTEXITCODE -ne 0) { throw 'Python replay of real Git proof failed' }
    $checks++
    Write-Output "FPGA_GIT_IDENTITY_PASS checks=$checks TEMP_GIT_ONLY_NO_PDS_NO_JTAG"
} finally {
    if (Test-Path -LiteralPath $fixture) {
        $resolved = (Get-Item -LiteralPath $fixture -Force).FullName
        if (!$resolved.StartsWith($tempBase + '\fpga-git-identity-', [StringComparison]::OrdinalIgnoreCase) -or
            ((Get-Item -LiteralPath $fixture -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            @(Get-ChildItem -LiteralPath $fixture -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
            throw 'Unsafe Git identity fixture cleanup'
        }
        Remove-Item -LiteralPath $fixture -Recurse -Force
    }
}
