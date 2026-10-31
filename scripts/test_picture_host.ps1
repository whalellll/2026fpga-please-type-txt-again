param([Parameter(Mandatory=$true)][string]$HostCompiler,
      [Parameter(Mandatory=$true)][string]$PythonPath,
      [string]$EvidencePath='')
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$out=Join-Path $repo 'build/picture-host-tests'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$tests=@(
 @{name='picture-fat-write';forcedHeader='linux/boot/v2_1_sd/source/picture_fat_write/fat_camera.h';includes=@('linux/boot/v2_1_sd/source/picture_fat_write','sw/bootloader');sources=@('linux/boot/v2_1_sd/source/picture_fat_write/test_picture_fat_write.c','linux/boot/v2_1_sd/source/picture_fat_write/fat_camera.c','linux/boot/v2_1_sd/source/picture_fat_write/fat_boot_prefix.c','sw/bootloader/fat_ro.c','sw/bootloader/camera_sd.c','sw/bootloader/png_rgb565.c','sw/bootloader/crc32_fast.c');extra=@((Join-Path $out 'picture-fat-synthetic.png'))},
 @{name='picture-state';includes=@('linux/vision','sw/xiangqi');sources=@('linux/vision/test_picture.c','linux/vision/xq_picture.c','linux/vision/xq_vision.c','sw/xiangqi/xiangqi_pikafish_link.c','sw/xiangqi/xiangqi_search.c')},
 @{name='picture-hid';includes=@('linux/vision','sw/xiangqi');sources=@('linux/vision/test_picture_hid.c','linux/vision/xq_picture.c','linux/vision/xq_vision.c','sw/xiangqi/xiangqi_pikafish_link.c','sw/xiangqi/xiangqi_search.c')},
 @{name='picture-grid';includes=@('linux/vision','sw/xiangqi');sources=@('linux/vision/test_grid.c','linux/vision/xq_grid.c','linux/vision/xq_vision.c','sw/xiangqi/xiangqi_pikafish_link.c','sw/xiangqi/xiangqi_search.c')},
 @{name='picture-geometry';includes=@('linux/vision','sw/xiangqi');sources=@('linux/vision/test_geometry.c','linux/vision/xq_geometry.c')},
 @{name='picture-roi';includes=@('linux/vision','sw/xiangqi');sources=@('linux/vision/test_roi.c','linux/vision/xq_roi.c','linux/vision/xq_grid.c','linux/vision/xq_vision.c','sw/xiangqi/xiangqi_pikafish_link.c','sw/xiangqi/xiangqi_search.c')},
 @{name='picture-roi-pipeline';includes=@('linux/vision','sw/xiangqi');sources=@('linux/vision/test_roi_pipeline.c','linux/vision/xq_roi_pipeline.c','linux/vision/xq_roi.c','linux/vision/xq_grid.c','linux/vision/xq_vision.c','sw/xiangqi/xiangqi_pikafish_link.c','sw/xiangqi/xiangqi_search.c')},
 @{name='picture-speech';includes=@('linux/vision','sw/xiangqi');sources=@('linux/vision/test_speech.c','linux/vision/xq_speech.c','linux/vision/xq_vision.c','sw/xiangqi/xiangqi_pikafish_link.c','sw/xiangqi/xiangqi_search.c')},
 @{name='camera';includes=@('linux/vision','sw/xiangqi','sw/bootloader');sources=@('linux/vision/test_camera.c','linux/vision/xq_camera.c')},
 @{name='capture-recovery';includes=@('linux/vision','sw/xiangqi','sw/bootloader');sources=@('linux/vision/test_capture_recovery.c','linux/vision/xq_camera.c','linux/vision/xq_camera_capture_retry.c')},
 @{name='boot-preinit';includes=@('linux/vision','sw/bootloader','sw/xiangqi');sources=@('linux/vision/test_boot_preinit.c','sw/bootloader/crc32_fast.c')},
 @{name='camera-retry';includes=@('linux/vision','sw/bootloader','sw/xiangqi');sources=@('linux/vision/test_camera_retry.c','linux/vision/xq_camera_retry.c')},
 @{name='picture-png';includes=@('sw/bootloader');sources=@('linux/vision/test_picture_png.c','sw/bootloader/png_rgb565.c','sw/bootloader/crc32_fast.c');extra=@((Join-Path $out 'synthetic.png'))},
 @{name='picture-renderer';includes=@('sw/video','sw/xiangqi','linux/voice');sources=@('linux/vision/test_picture_renderer.c','linux/voice/xqvoice_protocol.c')},
 @{name='picture-gui';includes=@('linux/vision','sw/video','sw/xiangqi','sw/bootloader');sources=@('linux/vision/test_picture_gui.c','linux/vision/xq_camera_capture_retry.c','linux/vision/xq_roi.c','linux/vision/xq_picture.c','linux/vision/xq_vision.c','linux/vision/xq_grid.c','linux/vision/xq_speech.c','sw/bootloader/crc32_fast.c','sw/xiangqi/xiangqi_mouse_input.c','sw/xiangqi/xiangqi_pikafish_link.c','sw/xiangqi/xiangqi_search.c');extra=@((Join-Path $out 'gui-test.stub'))}
)
$results=[Collections.Generic.List[object]]::new()
Push-Location $repo
try {
 foreach($test in $tests) {
  $watch=[Diagnostics.Stopwatch]::StartNew()
  $exe=Join-Path $out ($test.name+'.exe')
  $args=@('-std=gnu11','-O2','-pthread','-Wall','-Wextra','-Werror')
  if($test.forcedHeader) { $args+=@('-include',(Join-Path $repo $test.forcedHeader)) }
  foreach($include in $test.includes) { $args+=('-I'+$include) }
  $args+=$test.sources
  $args+=@('-o',$exe)
  & $HostCompiler @args
  if($LASTEXITCODE) { throw "Host compilation failed: $($test.name)" }
  $runArguments=@()
  if($test.extra) { $runArguments=$test.extra }
  & $exe @runArguments
  if($LASTEXITCODE) { throw "Host execution failed: $($test.name)" }
  $results.Add(@{name=$test.name;pass=$true;elapsed_ms=$watch.ElapsedMilliseconds})
 }
 foreach($name in @('test_picture_candidate.py','test_picture_model.py','test_picture_three_model.py','test_picture_speech_assets.py','test_picture_sd_candidate.py')) {
  & $PythonPath -B (Join-Path $PSScriptRoot $name)
  if($LASTEXITCODE) { throw "Host Python test failed: $name" }
  $results.Add(@{name=$name;pass=$true})
 }
 & $PythonPath -B (Join-Path $PSScriptRoot 'test_picture_png.py') (Join-Path $out 'synthetic.png')
 if($LASTEXITCODE) { throw 'Synthetic RGB565/PNG pixel verification failed' }
 $results.Add(@{name='test_picture_png.py';pass=$true})
 $pythonVersion=(& $PythonPath --version | Out-String).Trim()
 $files=@(Get-ChildItem (Join-Path $repo 'linux/vision') -File -Recurse)
 $files+=@('sw/bootloader/camera.c','sw/bootloader/camera.h','sw/bootloader/main.c',
  'linux/pikafish/xiangqi_fb_gui_linux.c','linux/pikafish/xiangqi_pikafish_gui.c',
  'linux/soc.dts','linux/boot/v2_1_sd/source/loader.c') | ForEach-Object { Get-Item (Join-Path $repo $_) }
 $files+=@('scripts/test_picture_host.ps1','scripts/prepare_picture_candidate.py',
  'scripts/test_picture_candidate.py','scripts/verify_picture_model.py','scripts/verify_picture_three_model.py','scripts/test_picture_model.py','scripts/test_picture_three_model.py','scripts/test_picture_png.py',
  'scripts/build_picture_loader.ps1','scripts/make_picture_rootfs.ps1','scripts/generate_picture_font.ps1',
  'scripts/generate_picture_speech.ps1','scripts/test_picture_speech_assets.py') |
  ForEach-Object { Get-Item (Join-Path $repo $_) }
 $files+=@('scripts/prepare_picture_engine.py','scripts/package_picture_linux_handoff.py') |
  ForEach-Object { Get-Item (Join-Path $repo $_) }
 $files+=@(Get-ChildItem (Join-Path $repo 'linux/boot/v2_1_sd/rootfs_payloads/picture') -File -Recurse)
 $hashes=[ordered]@{}
 foreach($file in $files | Sort-Object FullName) {
  $relative=$file.FullName.Substring($repo.Length+1).Replace([char]92,[char]47)
  $hashes[$relative]=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
 }
 $record=[ordered]@{scope='Host C / simulated MMIO only; no target build or board acceptance';
  tested_at_utc=[DateTime]::UtcNow.ToString('o');
  host_compiler_version=(& $HostCompiler --version | Out-String).Trim();
  host_compiler_target=(& $HostCompiler -dumpmachine | Out-String).Trim();
  compiler_flags=@('-std=gnu11','-O2','-pthread','-Wall','-Wextra','-Werror');
  python=$pythonVersion;host_compiler_sha256=(Get-FileHash -LiteralPath $HostCompiler -Algorithm SHA256).Hash.ToLowerInvariant();
  tests=$results;source_sha256=$hashes;board_validated=$false;full_regression_pass=$false}
 if($EvidencePath) { [IO.File]::WriteAllText([IO.Path]::GetFullPath($EvidencePath),($record|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false)) }
 Write-Output 'PICTURE_HOST_TEST_PASS board_validated=false'
} finally { Pop-Location }
