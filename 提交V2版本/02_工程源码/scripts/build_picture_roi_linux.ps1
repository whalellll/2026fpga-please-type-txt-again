param([string]$CandidateDirectory='build/picture-roi-linux-candidate',
      [string]$EngineDirectory='build/picture-engine/source/src',
      [string]$Distro='Ubuntu-22.04')
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
function WslPath([string]$path){
 $full=[IO.Path]::GetFullPath($path)
 if($full -notmatch '^([A-Za-z]):\\(.*)$'){throw 'Expected Windows absolute path'}
 return '/mnt/'+$Matches[1].ToLowerInvariant()+'/'+$Matches[2].Replace('\','/')
}
$out=[IO.Path]::GetFullPath((Join-Path $repo $CandidateDirectory))
$engine=[IO.Path]::GetFullPath((Join-Path $repo $EngineDirectory))
$allowed=[IO.Path]::GetFullPath((Join-Path $repo 'build'))+[IO.Path]::DirectorySeparatorChar
if(!$out.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $out)){
 throw 'Choose a fresh GUI candidate directory strictly under build/.'
}
if(!(Test-Path -LiteralPath (Join-Path $engine 'pikafish_mac_runtime.o'))){throw 'Missing frozen P19 engine object inputs'}
& wsl.exe -d $Distro -- timeout 300 sh (WslPath (Join-Path $repo 'linux/vision/build_roi_candidate.sh')) (WslPath $repo) (WslPath $out) (WslPath $engine)
if($LASTEXITCODE){throw 'ROI GUI target build failed'}
& (Join-Path $PSScriptRoot 'make_picture_rootfs.ps1') -CandidateDirectory $CandidateDirectory -RoiPreview
