param([string]$Root=(Split-Path -Parent $PSScriptRoot),[Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
$Root=[IO.Path]::GetFullPath($Root).TrimEnd('\')
. (Join-Path $PSScriptRoot 'project_files.ps1')
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
$names=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach($p in @(Get-ProjectFiles $Root)){$null=$names.Add($p)}
# Clock-contract regressions consume these exact tracked historical sources.
# They are test inputs, not the current FPGA or SD implementation. The generic
# artifact whitelist omits them, so keep their dependency closure explicit.
foreach($p in @('artifacts/voice_hw_candidate_20261016/loader/loader.c',
               'artifacts/voice_hw_candidate_20261016/boot/voice.soc.dts')) {
    if(!(Test-Path -LiteralPath (Join-Path $Root $p) -PathType Leaf)){throw "Missing clock regression fixture $p"}
    $null=$names.Add($p)
}
foreach($name in @('MAIN70_RELEASE.json','MAIN70_PUBLICATION.json','SHA256SUMS.txt','pds/build_snapshot.json')) {
    if(Test-Path -LiteralPath (Join-Path $Root $name)){$null=$names.Add($name)}
}
$snapshot=Get-Content -LiteralPath (Join-Path $Root 'artifacts/build_snapshot.json') -Raw -Encoding UTF8|ConvertFrom-Json
$evidence=Get-Content -LiteralPath (Join-Path $Root 'artifacts/build_evidence.json') -Raw -Encoding UTF8|ConvertFrom-Json
foreach($map in @($snapshot.inputs,$evidence.report_hashes,$evidence.outputs)) {
    foreach($p in $map.PSObject.Properties.Name){$null=$names.Add($p)}
}
# GUI/native readers consume the staged aliases as well as their canonical
# FPGA inputs. Include the complete declared map, with exact byte equality.
foreach($entry in (Get-FpgaStagedAssets).GetEnumerator()) {
    $alias=Get-FpgaSafePath $Root $entry.Key
    $canonical=Get-FpgaSafePath $Root $entry.Value
    if(!(Test-Path -LiteralPath $alias -PathType Leaf)){throw "Missing staged PDS asset $($entry.Key)"}
    if((Get-FileHash -LiteralPath $alias -Algorithm SHA256).Hash -cne (Get-FileHash -LiteralPath $canonical -Algorithm SHA256).Hash){throw "PDS asset differs from canonical input $($entry.Key)"}
    $null=$names.Add($entry.Key)
}
foreach($directory in @('artifacts/main70_20261027','docs/validation/main70-release-20261027',
                       'prebuilt/cpu80-policy-fixture')) {
    foreach($file in Get-ChildItem -LiteralPath (Join-Path $Root $directory) -Recurse -File -Force) {
        if($file.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked current release evidence'}
        if($file.Name -like '*.pyc' -or $file.FullName -match '\\__pycache__\\'){continue}
        $null=$names.Add($file.FullName.Substring($Root.Length+1).Replace('\','/'))
    }
}
# Include the actual attachments of inherited Markdown; never fabricate missing
# ones. The normal audit still checks the full local link set independently.
$changed=$true
while($changed) {
    $changed=$false
    foreach($name in @($names|Where-Object {$_ -like '*.md'})) {
        $doc=Join-Path $Root $name
        foreach($m in [regex]::Matches([IO.File]::ReadAllText($doc),'\]\(([^)]+)\)')) {
            $target=$m.Groups[1].Value.Trim('<','>')
            if($target -match '^(https?:|mailto:|#)'){continue}
            $target=[Uri]::UnescapeDataString(($target -split '#',2)[0]);if(!$target){continue}
            $p=[IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $doc) $target))
            if(!$p.StartsWith($Root+'\',[StringComparison]::OrdinalIgnoreCase) -or !(Test-Path -LiteralPath $p)){throw "Missing/escaping attachment $name -> $target"}
            $items=if(Test-Path -LiteralPath $p -PathType Leaf){@(Get-Item -LiteralPath $p)}else{@(Get-ChildItem -LiteralPath $p -Recurse -File -Force)}
            foreach($file in $items) {
                if($file.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked Markdown attachment'}
                if($names.Add($file.FullName.Substring($Root.Length+1).Replace('\','/'))){$changed=$true}
            }
        }
    }
}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($Output),(@($names|Sort-Object)|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
