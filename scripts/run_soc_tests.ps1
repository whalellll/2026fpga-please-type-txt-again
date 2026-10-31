param([string]$IcarusBin = 'D:\LJL\WORK\iverilog\bin')

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$iverilog = Join-Path $IcarusBin 'iverilog.exe'
$vvp = Join-Path $IcarusBin 'vvp.exe'
if (!(Test-Path -LiteralPath $iverilog)) { throw "Icarus not found: $iverilog" }
$bootrom = Join-Path $root 'pds\bootrom.hex'
if (!(Test-Path -LiteralPath $bootrom -PathType Leaf)) {
    throw 'Boot ROM is missing; run scripts/build_bootloader.ps1 before run_soc_tests.ps1'
}

function Invoke-SocSimulation {
    param([string]$Image)
    # Icarus can report a missing $readmemh input and still exit 0 after a
    # bench prints PASS. Runtime errors invalidate the whole simulation.
    $output = @(& $script:vvp $Image 2>&1)
    $nativeExitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Output $_ }
    if ($nativeExitCode -ne 0) { throw "Simulation failed: $Image (exit $nativeExitCode)" }
    if ($output | Where-Object { [string]$_ -match '^\s*(?:ERROR:|FATAL:)' }) {
        throw "Simulation reported a runtime error: $Image"
    }
}

function Assert-SocSourcePattern {
    param(
        [string]$Text,
        [string]$Pattern,
        [string]$Description
    )
    if (![regex]::IsMatch($Text, $Pattern)) {
        throw "SoC integration check failed: $Description"
    }
}

function Get-SocInstance {
    param(
        [string]$Text,
        [string]$ModuleName,
        [string]$InstanceName
    )
    $pattern = [regex]::Escape($ModuleName) + `
        '(?:#\((?<Parameters>.*?)\))?' + [regex]::Escape($InstanceName) + `
        '\((?<Ports>.*?)\);'
    $instance = [regex]::Match($Text, $pattern)
    if (!$instance.Success) {
        throw "SoC integration check failed: missing $ModuleName $InstanceName"
    }
    return $instance
}

Push-Location $root
try {
    # Check the top-level integration as source structure rather than merely
    # compiling its leaf blocks.  Strip comments and whitespace first so the
    # checks survive harmless formatting changes and cannot pass on comments.
    $socSource = Get-Content -LiteralPath 'rtl\soc\soc_top.v' -Raw
    $socSource = [regex]::Replace($socSource, '(?s)/\*.*?\*/', '')
    $socSource = [regex]::Replace($socSource, '(?m)//.*$', '')
    $socSource = [regex]::Replace($socSource, '\s+', '')

    # The SCCB engines intentionally retain the official demo's fabric-divided
    # clock.  Keep both generated clocks explicit so PDS does not silently
    # leave the sensor initialization state machines outside STA.
    $fdcSource = Get-Content -LiteralPath 'pds\soc.fdc' -Raw
    foreach ($cameraIndex in 1, 2) {
        Assert-SocSourcePattern $fdcSource `
            ("create_generated_clock\s+-name\s+\{camera${cameraIndex}_sccb_clk\}" +
             ".*?-divide_by\s+\{4950\}") `
            "camera$cameraIndex SCCB generated-clock constraint is missing"
        Assert-SocSourcePattern $fdcSource `
            ("set_clock_groups\s+-name\s+\{sys_to_camera${cameraIndex}_sccb\}" +
             ".*?\{sys_clk\}.*?\{camera${cameraIndex}_sccb_clk\}") `
            "camera$cameraIndex SCCB CDC asynchronous clock group is missing"
    }
    foreach ($sdPin in @(
        @('sd_clk', 'F19'),
        @('sd_cmd', 'H14'),
        @('sd_data0', 'F18'),
        @('sd_data1', 'F20'),
        @('sd_data2', 'H17'),
        @('sd_data3', 'H15'),
        @('sd_detect_n', 'G19')
    )) {
        Assert-SocSourcePattern $fdcSource `
            ("define_attribute\s+\{p:" + $sdPin[0] +
             "\}\s+\{PAP_IO_LOC\}\s+\{" + $sdPin[1] + "\}") `
            "MicroSD pin $($sdPin[0]) is not on $($sdPin[1])"
        Assert-SocSourcePattern $fdcSource `
            ("define_attribute\s+\{p:" + $sdPin[0] +
             "\}\s+\{PAP_IO_STANDARD\}\s+\{LVCMOS33\}") `
            "MicroSD pin $($sdPin[0]) is not LVCMOS33"
    }
    foreach ($audioPin in @(
        @('audio_bclk', 'V26'),
        @('audio_ws', 'W26'),
        @('microphone_sd', 'U16'),
        @('spk_din', 'U15')
    )) {
        Assert-SocSourcePattern $fdcSource `
            ("define_attribute\s+\{p:" + $audioPin[0] +
             "\}\s+\{PAP_IO_LOC\}\s+\{" + $audioPin[1] + "\}") `
            "audio pin $($audioPin[0]) is not on $($audioPin[1])"
        Assert-SocSourcePattern $fdcSource `
            ("define_attribute\s+\{p:" + $audioPin[0] +
             "\}\s+\{PAP_IO_STANDARD\}\s+\{LVCMOS33\}") `
            "audio pin $($audioPin[0]) is not LVCMOS33"
    }

    $audioRegs = Get-SocInstance $socSource 'audio_mmio' 'u_audio_regs'
    $audioI2s = Get-SocInstance $socSource 'i2s_audio_duplex' 'u_audio_i2s'
    foreach ($port in @('microphone_sample','microphone_count','playback_underflows',
            'microphone_read','microphone_fifo_data','microphone_fifo_empty',
            'microphone_fifo_full','microphone_fifo_level','microphone_overflows')) {
        Assert-SocSourcePattern $audioRegs.Groups['Ports'].Value `
            ("\.${port}\(audio_${port}\)(?:,|$)") "audio MMIO $port is disconnected"
        Assert-SocSourcePattern $audioI2s.Groups['Ports'].Value `
            ("\.${port}\(audio_${port}\)(?:,|$)") "I2S $port is disconnected"
    }

    $ch9350 = Get-SocInstance $socSource 'ch9350_hid_core' 'u_ch9350'
    Assert-SocSourcePattern $ch9350.Groups['Parameters'].Value `
        '\.UART_BAUD_DIV\(430\)(?:,|$)' 'CH9350 UART divisor is not 430'
    Assert-SocSourcePattern $ch9350.Groups['Parameters'].Value `
        '\.REPEAT_DELAY_CYCLES\(24_750_000\)(?:,|$)' `
        'CH9350 repeat delay is not 24_750_000 cycles'
    Assert-SocSourcePattern $ch9350.Groups['Parameters'].Value `
        '\.REPEAT_PERIOD_CYCLES\(1_980_000\)(?:,|$)' `
        'CH9350 repeat period is not 1_980_000 cycles'

    $videoSelections = @(
        @('selected_vs', 'fb_vs', 'video_vs'),
        @('selected_hs', 'fb_hs', 'video_hs'),
        @('selected_de', 'fb_de', 'video_de'),
        @('selected_r',  'fb_r',  'video_r'),
        @('selected_g',  'fb_g',  'video_g'),
        @('selected_b',  'fb_b',  'video_b')
    )
    foreach ($selection in $videoSelections) {
        $pattern = [regex]::Escape($selection[0] + '=fb_active_enable_pix?' + `
            $selection[1] + ':' + $selection[2] + ';')
        Assert-SocSourcePattern $socSource $pattern `
            "missing framebuffer/text selection for $($selection[0])"
    }

    $overlay = Get-SocInstance $socSource 'hid_gui_overlay' 'u_hid_gui'
    foreach ($port in @('hs', 'vs', 'de', 'r', 'g', 'b')) {
        Assert-SocSourcePattern $overlay.Groups['Ports'].Value `
            ("\.${port}_in\(selected_${port}\)(?:,|$)") `
            "selected_$port does not feed the HID overlay"
        Assert-SocSourcePattern $overlay.Groups['Ports'].Value `
            ("\.${port}_out\(gui_${port}\)(?:,|$)") `
            "HID overlay does not drive gui_$port"
        $cameraHud = Get-SocInstance $socSource 'camera_sd_hud' 'u_camera_sd_hud'
        Assert-SocSourcePattern $cameraHud.Groups['Ports'].Value `
            ("\.${port}_in\(fb_${port}\)") "camera HUD source is not the raw framebuffer"
        Assert-SocSourcePattern $cameraHud.Groups['Ports'].Value `
            ("\.${port}_out\(camera_fb_${port}\)") "camera HUD output is disconnected"
        Assert-SocSourcePattern $socSource `
            ("hdmi_source_${port}=camera_video_selected_pix\?camera_fb_${port}:gui_${port};") `
            "camera/text selection is missing for HDMI $port"
        Assert-SocSourcePattern $socSource `
            ("hdmi_${port}_q<=hdmi_source_${port};") `
            "selected HDMI $port does not feed the output register"
        Assert-SocSourcePattern $socSource `
            ("assign${port}_out=hdmi_init_d\?hdmi_${port}_q:") `
            "HDMI output $($port)_out does not use the overlaid video"
    }

    Assert-SocSourcePattern $socSource `
        "0:sys_rdata=32'h5356_?3300;" 'V3 SYS ID is not 0x53563300'
    Assert-SocSourcePattern $socSource `
        "3:sys_rdata=32'h0000_?001f;" `
        'SYS capability bits do not advertise camera and MicroSD support'
    Assert-SocSourcePattern $socSource `
        "wirehid_hit=\(io_addr>=32'h1fe0_?0400\)&&\(io_addr<32'h1fe0_?042c\);" `
        'HID MMIO decode is missing'
    Assert-SocSourcePattern $socSource `
        "wiremac_hit=\(io_addr>=32'h1fe1_?0000\)&&\(io_addr<32'h1fe1_?0200\);" `
        'MAC MMIO decode is missing'

    $fbRegisters = Get-SocInstance $socSource 'video_fb_mmio' 'u_fb_regs'
    Assert-SocSourcePattern $fbRegisters.Groups['Ports'].Value `
        '\.rdata\(fb_reg_rdata\)(?:,|$)' 'framebuffer MMIO read data is disconnected'
    Assert-SocSourcePattern $fbRegisters.Groups['Ports'].Value `
        '\.hit\(fb_hit\)(?:,|$)' 'framebuffer MMIO hit is disconnected'

    $cameraRegisters = Get-SocInstance $socSource 'camera_mmio' 'u_camera_regs'
    Assert-SocSourcePattern $cameraRegisters.Groups['Ports'].Value `
        '\.rdata\(camera_reg_rdata\)(?:,|$)' 'camera MMIO read data is disconnected'
    Assert-SocSourcePattern $cameraRegisters.Groups['Ports'].Value `
        '\.hit\(camera_hit\)(?:,|$)' 'camera MMIO hit is disconnected'
    Assert-SocSourcePattern $cameraRegisters.Groups['Ports'].Value `
        '\.enable\(camera_control_enable_cpu\)(?:,|$)' `
        'camera MMIO enable control is disconnected'
    Assert-SocSourcePattern $cameraRegisters.Groups['Ports'].Value `
        '\.stop_request\(camera_stop_request_cpu\)(?:,|$)' `
        'camera MMIO stop request is disconnected'

    $sdRegisters = Get-SocInstance $socSource 'sd_native_mmio' 'u_sd'
    foreach ($portMapping in @(
        @('rdata', 'sd_rdata'),
        @('hit', 'sd_hit'),
        @('sd_clk', 'sd_clk'),
        @('sd_cmd_in', 'sd_cmd'),
        @('sd_cmd_out', 'sd_cmd_out'),
        @('sd_cmd_oe', 'sd_cmd_oe'),
        @('sd_dat_in', 'sd_dat_in'),
        @('sd_dat_out', 'sd_dat_out'),
        @('sd_dat_oe', 'sd_dat_oe'),
        @('sd_detect_n', 'sd_detect_n')
    )) {
        Assert-SocSourcePattern $sdRegisters.Groups['Ports'].Value `
            ([regex]::Escape('.' + $portMapping[0] + '(' + $portMapping[1] + ')')) `
            "MicroSD controller port $($portMapping[0]) is disconnected"
    }

    Assert-SocSourcePattern $socSource `
        'fb_dma_enable_sys=camera_scanout_enable_sys\?1''b1:fb_enable_sys;' `
        'camera mode does not enable the existing framebuffer DMA'
    Assert-SocSourcePattern $socSource `
        'fb_dma_requested_buffer_sys=camera_scanout_enable_sys\?camera_published_buffer_sys:fb_requested_buffer_sys;' `
        'camera mode does not select the published framebuffer'
    Assert-SocSourcePattern $socSource `
        'if\(!camera_fb_vs_d&&camera_fb_vs\)camera_mode_active_pix<=camera_mode_p2&&fb_active_enable_pix;' `
        'camera HDMI selection is not latched on framebuffer VSYNC'
    Assert-SocSourcePattern $socSource `
        'camera_video_selected_pix=camera_mode_active_pix;' `
        'camera HDMI selection does not use the frame-boundary mode latch'

    $nativeWriteArbiter = Get-SocInstance $socSource `
        'ddr_native_write_arbiter' 'u_native_write_arbiter'
    foreach ($portMapping in @(
        @('s1_awaddr', 'camera_awaddr'),
        @('s1_awvalid', 'camera_awvalid'),
        @('s1_awready', 'camera_awready'),
        @('s1_wdata', 'camera_wdata'),
        @('s1_wready', 'camera_wready'),
        @('m_awaddr', 'n_awaddr'),
        @('m_wdata', 'n_wdata')
    )) {
        Assert-SocSourcePattern $nativeWriteArbiter.Groups['Ports'].Value `
            ([regex]::Escape('.' + $portMapping[0] + '(' + $portMapping[1] + ')')) `
            "native DDR write arbiter port $($portMapping[0]) is disconnected"
    }

    $cameraSensor = Get-SocInstance $socSource `
        'dual_ov5640_sensor' 'u_dual_ov5640'
    foreach ($portMapping in @(
        @('camera_enable', 'camera_sensor_enable_c2'),
        @('camera1_resetn', 'cmos1_reset'),
        @('camera2_resetn', 'cmos2_reset'),
        @('camera2_scl', 'cmos2_scl'),
        @('camera2_sda', 'cmos2_sda')
    )) {
        Assert-SocSourcePattern $cameraSensor.Groups['Ports'].Value `
            ([regex]::Escape('.' + $portMapping[0] + '(' + $portMapping[1] + ')')) `
            "dual-camera sensor port $($portMapping[0]) is disconnected"
    }

    $cameraCapture = Get-SocInstance $socSource `
        'ov5640_cmos2_capture' 'u_cmos2_capture'
    foreach ($portMapping in @(
        @('camera_vsync', 'cmos2_vsync'),
        @('camera_href', 'cmos2_href'),
        @('camera_data', 'cmos2_data'),
        @('pixel_valid', 'camera_pixel_valid_pclk'),
        @('pixel_rgb565', 'camera_pixel_rgb565_pclk')
    )) {
        Assert-SocSourcePattern $cameraCapture.Groups['Ports'].Value `
            ([regex]::Escape('.' + $portMapping[0] + '(' + $portMapping[1] + ')')) `
            "CMOS2 capture port $($portMapping[0]) is disconnected"
    }

    $cameraBuffers = Get-SocInstance $socSource `
        'camera_buffer_control' 'u_camera_buffer_control'
    foreach ($portMapping in @(
        @('stop_request', 'camera_stop_request_d2'),
        @('snapshot_hold', 'camera_snapshot_hold_d2'),
        @('snapshot_ready', 'camera_snapshot_ready_ddr'),
        @('snapshot_buffer', 'camera_snapshot_buffer_ddr'),
        @('snapshot_frame_count', 'camera_snapshot_frame_count_ddr'),
        @('writer_complete', 'camera_writer_complete_ddr'),
        @('writer_idle', 'camera_writer_idle_ddr'),
        @('frame_valid', 'camera_frame_valid_ddr'),
        @('published_buffer', 'camera_published_buffer_ddr'),
        @('idle', 'camera_buffer_idle_ddr')
    )) {
        Assert-SocSourcePattern $cameraBuffers.Groups['Ports'].Value `
            ([regex]::Escape('.' + $portMapping[0] + '(' + $portMapping[1] + ')')) `
            "camera buffer-control port $($portMapping[0]) is disconnected"
    }

    $cameraWriter = Get-SocInstance $socSource `
        'camera_frame_writer' 'u_camera_frame_writer'
    foreach ($portMapping in @(
        @('pixel_clk', 'cmos2_pclk'),
        @('pixel_resetn', 'camera_writer_pixel_resetn'),
        @('pixel_vsync', 'camera_frame_vsync_pclk'),
        @('pixel_line_active', 'camera_line_active_pclk'),
        @('pixel_valid', 'camera_pixel_valid_pclk'),
        @('frame_accept_enable', 'camera_frame_accept_ddr'),
        @('write_buffer', 'camera_write_buffer_ddr'),
        @('cam_awaddr', 'camera_awaddr'),
        @('cam_wdata', 'camera_wdata'),
        @('frame_complete', 'camera_writer_complete_ddr'),
        @('idle', 'camera_writer_idle_ddr')
    )) {
        Assert-SocSourcePattern $cameraWriter.Groups['Ports'].Value `
            ([regex]::Escape('.' + $portMapping[0] + '(' + $portMapping[1] + ')')) `
            "camera frame-writer port $($portMapping[0]) is disconnected"
    }
    Assert-SocSourcePattern $cameraWriter.Groups['Ports'].Value `
        ([regex]::Escape('.stop_request(camera_stop_request_d2||!camera_control_enable_d2)')) `
        'camera frame writer does not drain/stop with the command lifecycle'
    Assert-SocSourcePattern $socSource `
        'camera_scanout_enable_sys=camera_control_enable_cpu&&camera_frame_valid_cpu;' `
        'camera scanout can replace the text screen before the first valid frame'
    Assert-SocSourcePattern $socSource `
        'camera_frame_valid_c1<=camera_frame_valid_ddr;camera_frame_valid_c2<=camera_frame_valid_c1;camera_frame_valid_c3<=camera_frame_valid_c2;camera_frame_valid_cpu<=camera_frame_valid_c3;' `
        'camera frame-valid delay does not let the published buffer settle first'

    $macRegisters = Get-SocInstance $socSource 'mac_accel_ddr_kernel_top' 'u_mac_accel'
    Assert-SocSourcePattern $macRegisters.Groups['Ports'].Value `
        '\.reg_wr_en\(io_wr&&mac_hit\)(?:,|$)' 'MAC MMIO write decode is disconnected'
    Assert-SocSourcePattern $macRegisters.Groups['Ports'].Value `
        '\.reg_rd_data\(mac_reg_rdata\)(?:,|$)' 'MAC MMIO read data is disconnected'

    $ioValid = [regex]::Match($socSource, 'assignio_valid=(?<Expression>[^;]+);')
    if (!$ioValid.Success) {
        throw 'SoC integration check failed: io_valid assignment is missing'
    }
    foreach ($hit in @('sd_hit', 'audio_hit', 'hid_hit', 'mac_hit', 'fb_hit', 'camera_hit')) {
        Assert-SocSourcePattern $ioValid.Groups['Expression'].Value `
            ("(?:^|\|\|)${hit}(?:\|\||$)") `
            "$hit is absent from the combined MMIO valid response"
    }

    $ioRead = [regex]::Match($socSource, 'assignio_rdata=(?<Expression>[^;]+);')
    if (!$ioRead.Success) {
        throw 'SoC integration check failed: io_rdata assignment is missing'
    }
    foreach ($mapping in @(
        @('sd_hit', 'sd_rdata'),
        @('audio_hit', 'audio_rdata'),
        @('hid_hit', 'hid_rdata'),
        @('mac_hit', 'mac_reg_rdata'),
        @('fb_hit', 'fb_reg_rdata'),
        @('camera_hit', 'camera_reg_rdata')
    )) {
        Assert-SocSourcePattern $ioRead.Groups['Expression'].Value `
            ([regex]::Escape($mapping[0] + '?' + $mapping[1])) `
            "$($mapping[0]) is absent from the combined MMIO read mux"
    }
    Write-Output 'SOC_INTEGRATION_SOURCE_PASS'

    & $iverilog -g2012 -s tb_axi_1x2 -o (Join-Path $env:TEMP 'soc_xbar.vvp') `
        'rtl\soc\axi_1x2.v' 'sim\tb_axi_1x2.v'
    if ($LASTEXITCODE -ne 0) { throw 'AXI crossbar test compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_xbar.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'AXI crossbar test failed' }

    & $iverilog -g2012 -s tb_axi_2x1_arbiter `
        -o (Join-Path $env:TEMP 'soc_ddr_arbiter.vvp') `
        'rtl\soc\axi_2x1_arbiter.v' 'sim\tb_axi_2x1_arbiter.v'
    if ($LASTEXITCODE -ne 0) { throw 'DDR arbiter test compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_ddr_arbiter.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'DDR arbiter test failed' }

    & $iverilog -g2012 -s tb_axi_boot_periph -o (Join-Path $env:TEMP 'soc_local.vvp') `
        'rtl\soc\uart_tx_fifo.v' 'rtl\soc\axi_boot_periph.v' 'sim\tb_axi_boot_periph.v'
    if ($LASTEXITCODE -ne 0) { throw 'Local AXI test compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_local.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'Local AXI test failed' }

    & $iverilog -g2012 -Wall -s tb_sd_native_mmio `
        -o (Join-Path $env:TEMP 'soc_sd_native.vvp') `
        'rtl\soc\sd_native_mmio.v' 'sim\tb_sd_native_mmio.sv'
    if ($LASTEXITCODE -ne 0) { throw 'MicroSD native controller compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_sd_native.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'MicroSD native controller test failed' }

    & $iverilog -g2012 -Wall -s tb_sd_native_write `
        -o (Join-Path $env:TEMP 'soc_sd_write.vvp') `
        'rtl\soc\sd_native_mmio.v' 'sim\tb_sd_native_write.sv'
    if ($LASTEXITCODE) { throw 'MicroSD write RTL compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_sd_write.vvp')
    if ($LASTEXITCODE) { throw 'MicroSD write RTL test failed' }

    & $iverilog -g2012 -Wall -s tb_sd_native_multiblock `
        -o (Join-Path $env:TEMP 'soc_sd_multiblock.vvp') `
        rtl/soc/sd_native_mmio.v sim/tb_sd_native_multiblock.sv
    if ($LASTEXITCODE) { throw 'MicroSD CMD25 RTL compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_sd_multiblock.vvp')
    if ($LASTEXITCODE) { throw 'MicroSD CMD25 RTL test failed' }

    & $iverilog -g2012 -Wall -s tb_audio_mmio `
        -o (Join-Path $env:TEMP 'soc_audio_mmio.vvp') `
        'rtl\audio\audio_mmio.v' 'sim\tb_audio_mmio.v'
    if ($LASTEXITCODE -ne 0) { throw 'Audio MMIO compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_audio_mmio.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'Audio MMIO test failed' }

    & $iverilog -g2012 -Wall -s tb_i2s_audio `
        -o (Join-Path $env:TEMP 'soc_i2s_audio.vvp') `
        'rtl\audio\i2s_audio_duplex.v' 'sim\tb_i2s_audio.v'
    if ($LASTEXITCODE -ne 0) { throw 'I2S audio compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_i2s_audio.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'I2S audio test failed' }

    & $iverilog -g2012 -Wall -s tb_audio_fifo_order `
        -o (Join-Path $env:TEMP 'soc_audio_fifo_order.vvp') `
        'rtl\audio\i2s_audio_duplex.v' 'sim\tb_audio_fifo_order.sv'
    if ($LASTEXITCODE -ne 0) { throw 'Audio capture FIFO compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_audio_fifo_order.vvp')

    & $iverilog -g2012 -s tb_ch9350_hid -o (Join-Path $env:TEMP 'soc_hid.vvp') `
        'rtl\soc\ch9350_hid_core.v' 'sim\tb_ch9350_hid.v'
    if ($LASTEXITCODE -ne 0) { throw 'CH9350 HID test compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_hid.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'CH9350 HID test failed' }

    & $iverilog -g2012 -s tb_ch9350_linux_no_toolbar `
        -o (Join-Path $env:TEMP 'soc_hid_no_toolbar.vvp') `
        'rtl\soc\ch9350_hid_core.v' 'sim\tb_ch9350_linux_no_toolbar.v'
    if ($LASTEXITCODE -ne 0) { throw 'CH9350 Linux toolbar test compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_hid_no_toolbar.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'CH9350 Linux toolbar test failed' }

    & $iverilog -g2012 -s tb_axi_ddr_cdc -o (Join-Path $env:TEMP 'soc_ddr.vvp') `
        'rtl\soc\axi_ddr_cdc.v' 'sim\tb_axi_ddr_cdc.v'
    if ($LASTEXITCODE -ne 0) { throw 'DDR test compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_ddr.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'DDR test failed' }

    & $iverilog -g2012 -s tb_ddr_native_read_arbiter `
        -o (Join-Path $env:TEMP 'soc_native_read_arbiter.vvp') `
        'rtl\soc\ddr_native_read_arbiter.v' `
        'sim\tb_ddr_native_read_arbiter.sv'
    if ($LASTEXITCODE -ne 0) { throw 'Native DDR read arbiter compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_native_read_arbiter.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'Native DDR read arbiter test failed' }

    & $iverilog -g2012 -s tb_ddr_native_write_arbiter `
        -o (Join-Path $env:TEMP 'soc_native_write_arbiter.vvp') `
        'rtl\soc\ddr_native_write_arbiter.v' `
        'sim\tb_ddr_native_write_arbiter.sv'
    if ($LASTEXITCODE -ne 0) { throw 'Native DDR write arbiter compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_native_write_arbiter.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'Native DDR write arbiter test failed' }

    & $iverilog -g2012 -s tb_camera_mmio `
        -o (Join-Path $env:TEMP 'soc_camera_mmio.vvp') `
        'rtl\camera\camera_mmio.v' 'sim\tb_camera_mmio.sv'
    if ($LASTEXITCODE -ne 0) { throw 'Camera MMIO compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_camera_mmio.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'Camera MMIO test failed' }

    & $iverilog -g2012 -s tb_camera_buffer_control `
        -o (Join-Path $env:TEMP 'soc_camera_buffer_control.vvp') `
        'rtl\camera\camera_buffer_control.v' `
        'sim\tb_camera_buffer_control.sv'
    if ($LASTEXITCODE -ne 0) { throw 'Camera buffer control compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_camera_buffer_control.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'Camera buffer control test failed' }

    & $iverilog -g2012 -s tb_ov5640_register_table `
        -o (Join-Path $env:TEMP 'soc_ov5640_register_table.vvp') `
        'rtl\camera\ov5640_register_table.v' `
        'sim\tb_ov5640_register_table.sv'
    if ($LASTEXITCODE -ne 0) { throw 'OV5640 register table compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_ov5640_register_table.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'OV5640 register table test failed' }

    & $iverilog -g2012 -s tb_ov5640_cmos2_capture `
        -o (Join-Path $env:TEMP 'soc_ov5640_cmos2_capture.vvp') `
        'rtl\camera\ov5640_cmos2_capture.v' `
        'sim\tb_ov5640_cmos2_capture.sv'
    if ($LASTEXITCODE -ne 0) { throw 'OV5640 CMOS2 capture compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_ov5640_cmos2_capture.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'OV5640 CMOS2 capture test failed' }

    & $iverilog -g2012 -s tb_dual_ov5640_sensor_reentry `
        -o (Join-Path $env:TEMP 'soc_dual_ov5640_reentry.vvp') `
        'rtl\camera\ov5640_power_on_delay.v' `
        'rtl\camera\ov5640_sccb_write.v' `
        'rtl\camera\ov5640_register_table.v' `
        'rtl\camera\ov5640_register_init.v' `
        'rtl\camera\dual_ov5640_sensor.v' `
        'sim\tb_dual_ov5640_sensor_reentry.sv'
    if ($LASTEXITCODE -ne 0) { throw 'Dual OV5640 re-entry compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_dual_ov5640_reentry.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'Dual OV5640 re-entry test failed' }

    & $iverilog -g2012 -s tb_camera_frame_writer `
        -o (Join-Path $env:TEMP 'soc_camera_frame_writer.vvp') `
        'sim\camera_line_buffer_model.sv' `
        'rtl\camera\camera_frame_writer.v' `
        'sim\tb_camera_frame_writer.sv'
    if ($LASTEXITCODE -ne 0) { throw 'Camera frame writer compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_camera_frame_writer.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'Camera frame writer test failed' }

    & $iverilog -g2012 -s tb_video_fb_dma `
        -o (Join-Path $env:TEMP 'soc_video_fb_dma.vvp') `
        'rtl\video\video_fb_dma.v' 'sim\tb_video_fb_dma.sv'
    if ($LASTEXITCODE -ne 0) { throw 'Framebuffer DMA compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_video_fb_dma.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'Framebuffer DMA test failed' }

    & $iverilog -g2012 -s tb_xiangqi_sparse_eval `
        -o (Join-Path $env:TEMP 'soc_xiangqi_sparse_eval.vvp') `
        'rtl\mac_accel\xiangqi_sparse_eval.v' `
        'sim\tb_xiangqi_sparse_eval.sv'
    if ($LASTEXITCODE -ne 0) { throw 'Xiangqi sparse evaluator compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_xiangqi_sparse_eval.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'Xiangqi sparse evaluator test failed' }

    & $iverilog -g2012 -s tb_fp8_e4m3_q8_exhaustive `
        -o (Join-Path $env:TEMP 'cpuv2_fp8_e4m3_q8_exhaustive.vvp') `
        'rtl\mac_accel\MacAccelCore.v' `
        'sim\tb_fp8_e4m3_q8_exhaustive.v'
    if ($LASTEXITCODE -ne 0) { throw 'FP8 converter compile failed' }
    & $vvp (Join-Path $env:TEMP 'cpuv2_fp8_e4m3_q8_exhaustive.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'FP8 converter exhaustive test failed' }

    & $iverilog -g2012 -s tb_soc_mac_accel `
        -o (Join-Path $env:TEMP 'soc_mac_soc.vvp') `
        'rtl\soc\axi_2x1_arbiter.v' `
        'rtl\mac_accel\mac_accel_dma_kernel.v' `
        'rtl\mac_accel\mac_accel_axi_master32.v' `
        'rtl\mac_accel\xiangqi_sparse_eval.v' `
        'rtl\mac_accel\mac_accel_ddr_kernel_top.v' `
        'rtl\mac_accel\pff1_stagea_gather.v' `
        'rtl\mac_accel\mac_conv_descriptor_guard.v' `
        'rtl\mac_accel\mac_conv_window.v' `
        'rtl\mac_accel\mac_conv_input_dma.v' `
        'rtl\mac_accel\mac_weight_double_buffer.v' `
        'rtl\mac_accel\mac_conv_weight_dma.v' `
        'rtl\mac_accel\mac_conv_read_arbiter2.v' `
        'rtl\mac_accel\mac_conv_compute_core.v' `
        'rtl\mac_accel\mac_conv_compact_packer.v' `
        'rtl\mac_accel\mac_conv_compact_writer.v' `
        'rtl\mac_accel\mac_conv_rw_arbiter2.v' `
        'rtl\mac_accel\mac_conv_mmio_frontend.v' `
        'rtl\mac_accel\MacAccelCore.v' `
        'sim\gtp_apm_e2_perf_sim.v' 'sim\axi_shared_ram.sv' `
        'sim\tb_soc_mac_accel.sv'
    if ($LASTEXITCODE -ne 0) { throw 'MAC SoC integration compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_mac_soc.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'MAC SoC integration failed' }

    & $iverilog -g2012 -s tb_eth_mac_mmio -o (Join-Path $env:TEMP 'soc_eth.vvp') `
        'rtl\eth\eth_mac_mmio.v' 'sim\tb_eth_mac_mmio.v'
    if ($LASTEXITCODE -ne 0) { throw 'Ethernet test compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_eth.vvp')
    if ($LASTEXITCODE -ne 0) { throw 'Ethernet test failed' }

    & $iverilog -g2012 -s tb_rgmii_100m -o (Join-Path $env:TEMP 'soc_rgmii100.vvp') `
        'rtl\eth\rgmii_interface.v' 'sim\tb_rgmii_100m.v'
    if ($LASTEXITCODE -ne 0) { throw '100M RGMII test compile failed' }
    Invoke-SocSimulation (Join-Path $env:TEMP 'soc_rgmii100.vvp')
    if ($LASTEXITCODE -ne 0) { throw '100M RGMII test failed' }

    $videoSources = @(
        (Join-Path $root 'rtl\video\font_rom.v'),
        (Join-Path $root 'rtl\video\header_bitmap_rom.v'),
        (Join-Path $root 'rtl\video\header_logo_rom.v'),
        (Join-Path $root 'rtl\video\uart_console_text.v'),
        (Join-Path $root 'rtl\video\video_linux_console.v'),
        (Join-Path $root 'rtl\video\hid_gui_overlay.v'),
        (Join-Path $root 'sim\tb_hdmi_console.v')
    )
    # The ROM initialization files are source assets in rtl/video.  Running
    # from that directory keeps the regression self-contained in a delivery
    # archive; build_fpga.ps1 separately stages them into pds for synthesis.
    Push-Location (Join-Path $root 'rtl\video')
    try {
        & $iverilog -g2012 -s tb_camera_sd_hud `
            -o (Join-Path $env:TEMP 'soc_camera_sd_hud.vvp') `
            (Join-Path $root 'rtl\video\font_rom.v') `
            (Join-Path $root 'rtl\camera\camera_mmio.v') `
            (Join-Path $root 'rtl\camera\camera_sd_hud.v') `
            (Join-Path $root 'sim\tb_camera_sd_hud.sv')
        if ($LASTEXITCODE) { throw 'Camera HUD compile failed' }
        Invoke-SocSimulation (Join-Path $env:TEMP 'soc_camera_sd_hud.vvp')
        if ($LASTEXITCODE) { throw 'Camera HUD test failed' }
        & $iverilog -g2012 -s tb_hdmi_console `
            -o (Join-Path $env:TEMP 'soc_hdmi.vvp') $videoSources
        if ($LASTEXITCODE -ne 0) { throw 'HDMI console test compile failed' }
        Invoke-SocSimulation (Join-Path $env:TEMP 'soc_hdmi.vvp')
        if ($LASTEXITCODE -ne 0) { throw 'HDMI console test failed' }

        & $iverilog -g2012 -s tb_hid_gui_overlay_linux `
            -o (Join-Path $env:TEMP 'soc_hid_overlay.vvp') `
            (Join-Path $root 'rtl\video\font_rom.v') `
            (Join-Path $root 'rtl\video\hid_gui_overlay.v') `
            (Join-Path $root 'sim\tb_hid_gui_overlay_linux.v')
        if ($LASTEXITCODE -ne 0) { throw 'Linux HID overlay test compile failed' }
        Invoke-SocSimulation (Join-Path $env:TEMP 'soc_hid_overlay.vvp')
        if ($LASTEXITCODE -ne 0) { throw 'Linux HID overlay test failed' }
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}
Write-Output 'SOC_SOC_TESTS_PASS'
