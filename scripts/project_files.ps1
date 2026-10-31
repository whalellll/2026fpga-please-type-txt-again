# Shared release inventory. Generated PDS databases are never release inputs.
$script:ProjectRoot = Split-Path -Parent $PSScriptRoot
$script:ProjectVersion = ([IO.File]::ReadAllText((Join-Path $script:ProjectRoot 'VERSION'))).Trim()
$script:ReleaseArtifacts = @(
    'soc_top.sbit', 'soc_top.bin', 'bootloader.elf', 'bootloader.bin', 'bootrom.hex',
    'SONG.PCM', 'mac_selftest.elf', 'mac_selftest.bin',
    'mac_benchmark.elf', 'mac_benchmark.bin',
    'xiangqi_sparse_eval_selftest.elf', 'xiangqi_sparse_eval_selftest.bin',
    'xiangqi_fb_demo.elf', 'xiangqi_fb_demo.bin',
    'bootloader.build.json', 'mac_selftest.build.json', 'mac_benchmark.build.json',
    'xiangqi_sparse_eval_selftest.build.json', 'xiangqi_fb_demo.build.json',
    'timing_summary.txt', 'build_snapshot.json', 'build_evidence.json', 'cpu_ads_controls.json',
    'icache_pad_ads.json', 'preflight_gate.json', 'cpu_sys_cdc_ads_pre.json', 'cpu_sys_cdc_ads.json',
    'pds_synth_history.txt', 'pds_post_history.txt',
    'pds_synth_project.txt', 'pds_post_project.txt',
    'pds_synth_parse_stdout.txt', 'pds_synth_parse_stderr.txt',
    'pds_post_parse_stdout.txt', 'pds_post_parse_stderr.txt',
    'pds_synth_stdout.txt', 'pds_synth_stderr.txt', 'pds_post_stdout.txt', 'pds_post_stderr.txt',
    'pds_synth_constraints.txt', 'pds_post_constraints.txt', 'pds_synth_flow.txt',
    'pds_post_map_constraints.txt',
    'synth_resource_report.txt', 'final_timing_report.txt', 'final_timing_xml.xml', 'SHA256SUMS.txt'
)

function Get-ProjectFiles([string]$Root, [switch]$SourceOnly) {
    $paths = New-Object 'Collections.Generic.List[string]'
    foreach ($name in @('README.md', 'AGENTS.md', 'VERSION', 'CHANGELOG.md', '.gitignore', '.gitattributes', 'SKILLS_DELIVERY.json')) {
        if (!(Test-Path -LiteralPath (Join-Path $Root $name) -PathType Leaf)) {
            throw "Missing project entry: $name"
        }
        $paths.Add($name)
    }
    foreach ($directory in @('config', 'docs', 'rtl', 'sw', 'sim', 'scripts', 'ip', 'linux', 'prebuilt', 'skills')) {
        foreach ($file in Get-ChildItem -LiteralPath (Join-Path $Root $directory) -Recurse -File -Force) {
            $relative = $file.FullName.Substring($Root.Length + 1).Replace('\', '/')
            if ($file.Extension -in @('.log', '.vvp', '.o', '.obj', '.elf', '.pyc', '.lock', '.tmp', '.bak') -or
                $relative -match '(^|/)(__pycache__|logbackup)(/|$)|(^|/)\.settings/|^ip/ddr3_test/pnr/' -or
                $file.Name -match '^(CMOS2_|(?:IMG|JSN)[0-9]{5}\.|\.camera_|pds_.*_run\.tcl$)' -or
                $file.Name -eq '.last_generated' -or
                $relative -eq 'sim/linux_capability.hex') { continue }
            $paths.Add($relative)
        }
    }
    foreach ($name in @('soc.tcl', 'soc_post_synth.tcl', 'soc.fdc', 'ddr3_test.rcf',
        'soc_gui.pds', 'audit_cpu_sys_cdc_ads.py')) {
        $paths.Add("pds/$name")
    }
    # R29 uses engineering sources and immutable native packs below artifacts/.
    # Include those explicit inputs, without collecting training data or caches.
    foreach ($relative in @(
        'artifacts/vision-model-20261020/geometry/geometry_reference.c',
        'artifacts/main70_20261027/model-source/native_int8/board.xqm',
        'artifacts/main70_20261027/model-source/native_int8/detector.xqm',
        'artifacts/main70_20261027/model-source/native_int8/classifier.xqm')) {
        $paths.Add($relative)
    }
    foreach ($directory in @(
        'artifacts/vision-model-20261020-adapter/runtime',
        'artifacts/vision-model-20261020-adapter/geometry_fallback/c_ref')) {
        foreach ($file in Get-ChildItem -LiteralPath (Join-Path $Root $directory) -File) {
            if ($file.Extension -in @('.c', '.h')) {
                $paths.Add($file.FullName.Substring($Root.Length + 1).Replace('\', '/'))
            }
        }
    }
    if (!$SourceOnly) {
        foreach ($name in $script:ReleaseArtifacts) { $paths.Add("artifacts/$name") }
    }
    foreach ($relative in $paths) {
        $path = Join-Path $Root $relative
        if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing release file: $relative" }
        if ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Release files must be regular files: $relative"
        }
    }
    return @($paths | Sort-Object -Unique)
}

function Write-ProjectHashes([string]$Root) {
    $lines = foreach ($relative in Get-ProjectFiles $Root) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Root $relative)).Hash.ToLowerInvariant()
        "$hash  $relative"
    }
    [IO.File]::WriteAllLines((Join-Path $Root 'SHA256SUMS.txt'), [string[]]$lines,
        [Text.UTF8Encoding]::new($false))
}
