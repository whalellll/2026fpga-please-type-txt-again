param([Parameter(Mandatory=$true)][string]$ArchivePath,
      [string]$CandidateDirectory='build/picture-roi-prep-20261019/kernel-r01',
      [string]$WorkDirectory='/home/dogandlamb/picture-roi-kernel-20261019-r01',
      [string]$Distro='Ubuntu-22.04')
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$out=[IO.Path]::GetFullPath((Join-Path $repo $CandidateDirectory))
$allowed=[IO.Path]::GetFullPath((Join-Path $repo 'build'))+[IO.Path]::DirectorySeparatorChar
if (!$out.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $out)) {
 throw 'Choose a fresh kernel candidate directory strictly under build/.'
}
if ($WorkDirectory -notmatch '^/home/[a-zA-Z0-9_-]+/picture-roi-kernel-[a-zA-Z0-9_-]+$') {
 throw 'Use an isolated picture-roi-kernel work directory.'
}
function WslPath([string]$path) {
 $full=[IO.Path]::GetFullPath($path)
 if($full -notmatch '^([A-Za-z]):\\(.*)$'){throw 'Expected absolute Windows path'}
 return '/mnt/'+$Matches[1].ToLowerInvariant()+'/'+$Matches[2].Replace('\','/')
}
$archive=[IO.Path]::GetFullPath($ArchivePath)
if(!(Test-Path -LiteralPath $archive -PathType Leaf)){throw 'Missing verified kernel archive'}
& wsl.exe -d $Distro -- timeout 1800 sh (WslPath (Join-Path $repo 'linux/mac_accel/build_picture_kernel.sh')) (WslPath $repo) (WslPath $archive) (WslPath $out) $WorkDirectory
if($LASTEXITCODE){throw "Isolated kernel build failed: $LASTEXITCODE; inputs and work tree retained"}
Write-Output 'PICTURE_ROI_KERNEL_CANDIDATE_READY installed=false'
