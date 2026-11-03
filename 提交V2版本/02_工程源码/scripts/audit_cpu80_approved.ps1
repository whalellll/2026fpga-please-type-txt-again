param([string]$Root = (Split-Path -Parent $PSScriptRoot), [switch]$CheckHashes)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root).TrimEnd('\')
. (Join-Path $PSScriptRoot 'project_files.ps1')
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
. (Join-Path $PSScriptRoot 'release_version.ps1')
Assert-SocReleaseHeader $Root
& (Join-Path $PSScriptRoot 'check_clock_config.ps1') -Root $Root | Out-Null
$files = @(Get-ProjectFiles $Root)
& (Join-Path $Root 'scripts/prepare_pds_project.ps1') -ValidateOnly

# Resolve every local Markdown link, including links to source files.
$markdown = @('README.md', 'AGENTS.md', 'CHANGELOG.md') +
    @($files | Where-Object { $_ -like 'docs/*.md' -or $_ -like 'sw/*/README.md' -or $_ -like 'prebuilt/*.md' })
foreach ($relative in $markdown) {
    $document = Join-Path $Root $relative
    $content = [IO.File]::ReadAllText($document)
    foreach ($match in [regex]::Matches($content, '\]\(([^)]+)\)')) {
        $target = $match.Groups[1].Value.Trim('<', '>')
        if ($target -match '^(https?:|mailto:|#)') { continue }
        $target = [Uri]::UnescapeDataString(($target -split '#', 2)[0])
        if (!$target) { continue }
        if ($target -match '^[A-Za-z]:') { throw "Machine-specific link in ${relative}: $target" }
        $resolved = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $document) $target))
        if (!$resolved.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase) -or
            !(Test-Path -LiteralPath $resolved)) { throw "Broken local link in ${relative}: $target" }
    }
}
$docxVersion = [IO.File]::ReadAllText((Join-Path $Root 'VERSION')).Trim()
$docx = Join-Path $Root "docs/SOC_linux_V$docxVersion.docx"
$docxInputs = Join-Path $Root "docs/SOC_linux_V$docxVersion.docx.inputs.json"
if (!(Test-Path -LiteralPath $docx -PathType Leaf) -or !(Test-Path -LiteralPath $docxInputs -PathType Leaf)) {
    throw "Regenerate the V$docxVersion DOCX from current Markdown before release"
}
$docxRecord = Get-Content -LiteralPath $docxInputs -Raw -Encoding UTF8 | ConvertFrom-Json
$consoleDoc = @(Get-ChildItem -LiteralPath (Join-Path $Root 'docs') -Filter 'console*.md' -File)
if ($consoleDoc.Count -ne 1) { throw 'Expected one current console command document' }
$docxSources = @('README.md','CHANGELOG.md','docs/ARCHITECTURE.md','docs/BUILD.md',
    'docs/COREMARK.md','docs/Validation.md','docs/SUPPORTED_HARDWARE.md',
    ('docs/' + $consoleDoc[0].Name))
if ($docxRecord.schema -ne 1 -or
    $docxRecord.generator_sha256 -cne (Get-FileHash -LiteralPath (Join-Path $Root 'scripts/export_release_docx.py') -Algorithm SHA256).Hash.ToLowerInvariant() -or
    $docxRecord.docx_sha256 -cne (Get-FileHash -LiteralPath $docx -Algorithm SHA256).Hash.ToLowerInvariant() -or
    @($docxRecord.source_sha256.PSObject.Properties).Count -ne $docxSources.Count) {
    throw "V$docxVersion DOCX generator, file or source inventory differs from its input record"
}
foreach ($relative in $docxSources) {
    if ($docxRecord.source_sha256.$relative -cne (Get-FileHash -LiteralPath (Join-Path $Root $relative) -Algorithm SHA256).Hash.ToLowerInvariant()) {
        throw "V$docxVersion DOCX is stale for $relative"
    }
}

$project = [IO.File]::ReadAllText((Join-Path $Root 'pds/soc.tcl'))
$postProject = [IO.File]::ReadAllText((Join-Path $Root 'pds/soc_post_synth.tcl'))
foreach ($match in [regex]::Matches($project, 'add_design\s+"([^"]+)"')) {
    $design = [IO.Path]::GetFullPath((Join-Path (Join-Path $Root 'pds') $match.Groups[1].Value))
    if (!$design.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase) -or
        !(Test-Path -LiteralPath $design) -or
        $design.Substring($Root.Length + 1).Replace('\', '/') -notin $files) {
        throw "Missing PDS source: $($match.Groups[1].Value)"
    }
}
foreach ($match in [regex]::Matches($project, '(?m)^source\s+"([^"]+)"')) {
    $relative = 'pds/' + $match.Groups[1].Value
    if ($relative -notin $files -or !(Test-Path -LiteralPath (Join-Path $Root $relative) -PathType Leaf)) {
        throw "Missing tracked/frozen PDS Tcl source: $relative"
    }
}
foreach ($command in @('compile', 'synthesize', 'dev_map', 'pnr', 'report_timing', 'gen_bit_stream')) {
    $preCount = [regex]::Matches($project, '(?m)^' + $command + '\b').Count
    $postCount = [regex]::Matches($postProject, '(?m)^' + $command + '\b').Count
    if ($preCount -ne $(if ($command -in @('compile','synthesize')) { 1 } else { 0 }) -or
        $postCount -ne $(if ($command -in @('compile','synthesize')) { 0 } else { 1 })) {
        throw "PDS two-stage source flow has wrong $command command count"
    }
}
if (!$postProject.Contains('dev_map -input_db_file "synthesize/soc_top_syn.adf"') -or
    !$postProject.Contains('report_timing -report_max_skew') -or
    [regex]::Matches($postProject, '(?m)^add_design\b').Count -ne 0) {
    throw 'Post-synthesis PDS stage must import only the audited ADS ADF'
}
# Delivery-only adapter: the original audit_project.ps1 is one of the459
# native inputs and remains byte-identical. Do not retrofit frozen snapshots.
$approvedSnapshot = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $Root 'artifacts/build_snapshot.json') | ConvertFrom-Json
$approvedConsent = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $Root 'docs/validation/cpu80-audio-service-20261022/board-repair/release-approval-20261022.json') | ConvertFrom-Json
if ($approvedSnapshot.run_id -cne '44aa982f752c4b7d91accea60292735f' -or
    $approvedConsent.run_id -cne $approvedSnapshot.run_id -or
    $approvedConsent.status -cne 'USER_APPROVED_CURRENT_VERSION_COMMIT_FINAL_PACKAGE_MEDIA_PENDING') {
    throw 'Inherited function adapter is restricted to the approved CPU80 run.'
}
$inheritedFunctionSources = @{
    'rtl/mac_accel/mac_conv_weight_dma.v' = 'ddfb2c60daabc4d0df80759a9f3bb95adc7a3de02619523c921e9504186a6f19'
    'sim/tb_conv_weight_fold.sv' = '8ea92f4da293bd4b8da7ece33b8536dbc1b1c832042d8201e29b0bb15a6b7c47'
}
foreach ($relative in $files | Where-Object {
    $_ -match '^(rtl|sim|ip/camera_line_buffer)/.*\.(v|sv)$'
}) {
    if ([IO.File]::ReadAllText((Join-Path $Root $relative)) -match '(?m)^\s*function\b') {
        # These two exact files belong to the inherited folded implementation
        # accepted on2026-10-22. Native affine/cycle proofs remain separate.
        # A modified helper or any newly introduced function is still refused.
        $actual = (Get-FileHash -LiteralPath (Join-Path $Root $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
        if (!$inheritedFunctionSources.ContainsKey($relative) -or $inheritedFunctionSources[$relative] -cne $actual) {
            throw "Prohibited new or modified Verilog function in $relative"
        }
    }
}
$dts = [IO.File]::ReadAllText((Join-Path $Root 'linux/soc.dts'))
foreach ($marker in @('PG2L100H SoC Linux HID+XQ', 'reserved-memory',
    'framebuffer-dma@1fe11000', 'framebuffer@1b200000')) {
    if (!$dts.Contains($marker)) { throw "Stable system DTS marker missing: $marker" }
}
$dtb = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes((Join-Path $Root 'linux/boot/soc.dtb')))
if (!$dtb.Contains('PG2L100H SoC Linux HID+XQ')) { throw 'Stable system model missing from DTB' }
if (!$postProject.Contains('-fix_hold_violation') -or $postProject.Contains('-fix_hold_violation TRUE')) {
    throw 'PDS hold repair must use the SP6.4 presence-only option'
}
if (!$postProject.Contains('-optimize_multi_corner_timing')) { throw 'PDS multi-corner optimization is missing' }

$evidence = [IO.File]::ReadAllText((Join-Path $Root 'artifacts/build_evidence.json')) | ConvertFrom-Json
if ($evidence.release -ne "V$script:ProjectVersion" -or $evidence.device -ne 'PG2L100H-6-FBG676' -or
    $evidence.timing -ne 'All Constraints Met' -or $evidence.timing_summary_source -ne 'final report_timing' -or
    $evidence.latches -ne 0 -or
    !$evidence.snapshot_registers_verified -or !$evidence.pins_verified -or
    !$evidence.sd_write_registers_verified -or !$evidence.sd_multiblock_registers_verified -or
    !$evidence.hud_registers_verified -or !$evidence.cpu_ads_controls_verified) {
    throw 'Current release build evidence is missing or incomplete'
}
Assert-FpgaReleaseEvidence $Root $evidence
foreach ($name in @('bootloader','mac_selftest','mac_benchmark',
    'xiangqi_sparse_eval_selftest','xiangqi_fb_demo')) {
    $manifest = Get-Content -LiteralPath (Join-Path $Root "artifacts/$name.build.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($entry in @(@('elf','elf_sha256'), @('bin','binary_sha256'))) {
        $path = Join-Path $Root "artifacts/$name.$($entry[0])"
        if ($manifest.($entry[1]) -cne (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()) {
            throw "Published $name $($entry[0]) differs from its build manifest"
        }
    }
}
$binaryText = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes((Join-Path $Root 'artifacts/bootloader.bin')))
foreach ($marker in @("SoC V$script:ProjectVersion bootloader", 'debug camera', 'debug camera_sd', 'Photo saved and verified on SD.', 'Camera busy;',
        'Photo saved by PC.', 'debug speaker', 'debug mic', 'SONG.PCM')) {
    if (!$binaryText.Contains($marker)) { throw "Bootloader release marker missing: $marker" }
}
if ($CheckHashes) {
    $hashed = New-Object 'Collections.Generic.HashSet[string]'
    foreach ($line in [IO.File]::ReadAllLines((Join-Path $Root 'SHA256SUMS.txt'))) {
        if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw "Invalid SHA256SUMS line: $line" }
        $expected = $Matches[1]; $relative = $Matches[2]
        if (!$hashed.Add($relative) -or $relative -notin $files) { throw "Unexpected hash entry: $relative" }
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Root $relative)).Hash.ToLowerInvariant() -ne $expected) {
            throw "Release hash mismatch: $relative"
        }
    }
    if ($hashed.Count -ne $files.Count) { throw 'SHA256SUMS does not cover the complete release inventory' }
}
Write-Output "SOC_CPU80_APPROVED_PROJECT_AUDIT_PASS files=$($files.Count) native_audit_unchanged=true"
