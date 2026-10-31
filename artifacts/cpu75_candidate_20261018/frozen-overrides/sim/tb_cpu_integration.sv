`timescale 1ns/1fs
// Real generated CPU + production AXI crossbar, boot RAM and UART.
// DDR and other external MMIO are bounded models; this is not board evidence.
module tb_cpu_integration;
    reg clk = 0, resetn = 0, uart_rx = 1;
    reg cpu_clk = 0, cpu_resetn = 0;
    integer coremark_cpu_hz = 75000000;
    localparam [63:0] COREMARK_SYS_HALF_FS = 64'd10101010;
    reg [63:0] coremark_cpu_half_fs = 0;
    // SYS is fixed at 49.5 MHz; CPU uses an independent waveform and phase.
    always #10.101010 clk = ~clk;
    initial begin
        #3.173;
        forever #(500000000.0 / coremark_cpu_hz) cpu_clk = ~cpu_clk;
    end
    wire [3:0]  c_arid;
    wire [31:0] c_araddr;
    wire [7:0]  c_arlen;
    wire [2:0]  c_arsize;
    wire [1:0]  c_arburst;
    wire [1:0]  c_arlock;
    wire [3:0]  c_arcache;
    wire [2:0]  c_arprot;
    wire        c_arvalid;
    wire        c_arready;
    wire [3:0]  c_rid;
    wire [31:0] c_rdata;
    wire [1:0]  c_rresp;
    wire        c_rlast;
    wire        c_rvalid;
    wire        c_rready;
    wire [3:0]  c_awid;
    wire [31:0] c_awaddr;
    wire [7:0]  c_awlen;
    wire [2:0]  c_awsize;
    wire [1:0]  c_awburst;
    wire [1:0]  c_awlock;
    wire [3:0]  c_awcache;
    wire [2:0]  c_awprot;
    wire        c_awvalid;
    wire        c_awready;
    wire [3:0]  c_wid;
    wire [31:0] c_wdata;
    wire [3:0]  c_wstrb;
    wire        c_wlast;
    wire        c_wvalid;
    wire        c_wready;
    wire [3:0]  c_bid;
    wire [1:0]  c_bresp;
    wire        c_bvalid;
    wire        c_bready;
    wire [3:0]  d_arid;
    wire [31:0] d_araddr;
    wire [7:0]  d_arlen;
    wire [2:0]  d_arsize;
    wire [1:0]  d_arburst;
    wire [1:0]  d_arlock;
    wire [3:0]  d_arcache;
    wire [2:0]  d_arprot;
    wire        d_arvalid;
    wire        d_arready;
    wire [3:0]  d_rid;
    wire [31:0] d_rdata;
    wire [1:0]  d_rresp;
    wire        d_rlast;
    wire        d_rvalid;
    wire        d_rready;
    wire [3:0]  d_awid;
    wire [31:0] d_awaddr;
    wire [7:0]  d_awlen;
    wire [2:0]  d_awsize;
    wire [1:0]  d_awburst;
    wire [1:0]  d_awlock;
    wire [3:0]  d_awcache;
    wire [2:0]  d_awprot;
    wire        d_awvalid;
    wire        d_awready;
    wire [3:0]  d_wid;
    wire [31:0] d_wdata;
    wire [3:0]  d_wstrb;
    wire        d_wlast;
    wire        d_wvalid;
    wire        d_wready;
    wire [3:0]  d_bid;
    wire [1:0]  d_bresp;
    wire        d_bvalid;
    wire        d_bready;
    wire [3:0]  l_arid;
    wire [31:0] l_araddr;
    wire [7:0]  l_arlen;
    wire [2:0]  l_arsize;
    wire [1:0]  l_arburst;
    wire [1:0]  l_arlock;
    wire [3:0]  l_arcache;
    wire [2:0]  l_arprot;
    wire        l_arvalid;
    wire        l_arready;
    wire [3:0]  l_rid;
    wire [31:0] l_rdata;
    wire [1:0]  l_rresp;
    wire        l_rlast;
    wire        l_rvalid;
    wire        l_rready;
    wire [3:0]  l_awid;
    wire [31:0] l_awaddr;
    wire [7:0]  l_awlen;
    wire [2:0]  l_awsize;
    wire [1:0]  l_awburst;
    wire [1:0]  l_awlock;
    wire [3:0]  l_awcache;
    wire [2:0]  l_awprot;
    wire        l_awvalid;
    wire        l_awready;
    wire [3:0]  l_wid;
    wire [31:0] l_wdata;
    wire [3:0]  l_wstrb;
    wire        l_wlast;
    wire        l_wvalid;
    wire        l_wready;
    wire [3:0]  l_bid;
    wire [1:0]  l_bresp;
    wire        l_bvalid;
    wire        l_bready;
    core_top cpu(.cpu_clk(cpu_clk), .cpu_resetn(cpu_resetn),
        .sys_clk(clk), .sys_resetn(resetn),
        .arid(c_arid),
        .araddr(c_araddr),
        .arlen(c_arlen),
        .arsize(c_arsize),
        .arburst(c_arburst),
        .arlock(c_arlock),
        .arcache(c_arcache),
        .arprot(c_arprot),
        .arvalid(c_arvalid),
        .arready(c_arready),
        .rid(c_rid),
        .rdata(c_rdata),
        .rresp(c_rresp),
        .rlast(c_rlast),
        .rvalid(c_rvalid),
        .rready(c_rready),
        .awid(c_awid),
        .awaddr(c_awaddr),
        .awlen(c_awlen),
        .awsize(c_awsize),
        .awburst(c_awburst),
        .awlock(c_awlock),
        .awcache(c_awcache),
        .awprot(c_awprot),
        .awvalid(c_awvalid),
        .awready(c_awready),
        .wid(c_wid),
        .wdata(c_wdata),
        .wstrb(c_wstrb),
        .wlast(c_wlast),
        .wvalid(c_wvalid),
        .wready(c_wready),
        .bid(c_bid),
        .bresp(c_bresp),
        .bvalid(c_bvalid),
        .bready(c_bready)
    );
    axi_1x2 xbar(.clk(clk), .resetn(resetn),
        .s_arid(c_arid),
        .s_araddr(c_araddr),
        .s_arlen(c_arlen),
        .s_arsize(c_arsize),
        .s_arburst(c_arburst),
        .s_arlock(c_arlock),
        .s_arcache(c_arcache),
        .s_arprot(c_arprot),
        .s_arvalid(c_arvalid),
        .s_arready(c_arready),
        .s_rid(c_rid),
        .s_rdata(c_rdata),
        .s_rresp(c_rresp),
        .s_rlast(c_rlast),
        .s_rvalid(c_rvalid),
        .s_rready(c_rready),
        .s_awid(c_awid),
        .s_awaddr(c_awaddr),
        .s_awlen(c_awlen),
        .s_awsize(c_awsize),
        .s_awburst(c_awburst),
        .s_awlock(c_awlock),
        .s_awcache(c_awcache),
        .s_awprot(c_awprot),
        .s_awvalid(c_awvalid),
        .s_awready(c_awready),
        .s_wid(c_wid),
        .s_wdata(c_wdata),
        .s_wstrb(c_wstrb),
        .s_wlast(c_wlast),
        .s_wvalid(c_wvalid),
        .s_wready(c_wready),
        .s_bid(c_bid),
        .s_bresp(c_bresp),
        .s_bvalid(c_bvalid),
        .s_bready(c_bready),
        .m0_arid(d_arid),
        .m0_araddr(d_araddr),
        .m0_arlen(d_arlen),
        .m0_arsize(d_arsize),
        .m0_arburst(d_arburst),
        .m0_arvalid(d_arvalid),
        .m0_arready(d_arready),
        .m0_rid(d_rid),
        .m0_rdata(d_rdata),
        .m0_rresp(d_rresp),
        .m0_rlast(d_rlast),
        .m0_rvalid(d_rvalid),
        .m0_rready(d_rready),
        .m0_awid(d_awid),
        .m0_awaddr(d_awaddr),
        .m0_awlen(d_awlen),
        .m0_awsize(d_awsize),
        .m0_awburst(d_awburst),
        .m0_awvalid(d_awvalid),
        .m0_awready(d_awready),
        .m0_wid(d_wid),
        .m0_wdata(d_wdata),
        .m0_wstrb(d_wstrb),
        .m0_wlast(d_wlast),
        .m0_wvalid(d_wvalid),
        .m0_wready(d_wready),
        .m0_bid(d_bid),
        .m0_bresp(d_bresp),
        .m0_bvalid(d_bvalid),
        .m0_bready(d_bready),
        .m1_arid(l_arid),
        .m1_araddr(l_araddr),
        .m1_arlen(l_arlen),
        .m1_arsize(l_arsize),
        .m1_arburst(l_arburst),
        .m1_arvalid(l_arvalid),
        .m1_arready(l_arready),
        .m1_rid(l_rid),
        .m1_rdata(l_rdata),
        .m1_rresp(l_rresp),
        .m1_rlast(l_rlast),
        .m1_rvalid(l_rvalid),
        .m1_rready(l_rready),
        .m1_awid(l_awid),
        .m1_awaddr(l_awaddr),
        .m1_awlen(l_awlen),
        .m1_awsize(l_awsize),
        .m1_awburst(l_awburst),
        .m1_awvalid(l_awvalid),
        .m1_awready(l_awready),
        .m1_wid(l_wid),
        .m1_wdata(l_wdata),
        .m1_wstrb(l_wstrb),
        .m1_wlast(l_wlast),
        .m1_wvalid(l_wvalid),
        .m1_wready(l_wready),
        .m1_bid(l_bid),
        .m1_bresp(l_bresp),
        .m1_bvalid(l_bvalid),
        .m1_bready(l_bready)
    );
    wire uart_tx, console_valid;
    wire [7:0] console_data;
    wire [31:0] mmio_addr, mmio_wdata;
    wire [3:0] mmio_wstrb;
    wire mmio_wr;
    reg [31:0] mmio_rdata;
    axi_boot_periph #(.INIT_FILE("artifacts/bootrom.hex"),
                      .UART_BAUD_DIV(8)) local_bus(
        .clk(clk), .resetn(resetn),
        .arid(l_arid),
        .araddr(l_araddr),
        .arlen(l_arlen),
        .arsize(l_arsize),
        .arburst(l_arburst),
        .arvalid(l_arvalid),
        .arready(l_arready),
        .rid(l_rid),
        .rdata(l_rdata),
        .rresp(l_rresp),
        .rlast(l_rlast),
        .rvalid(l_rvalid),
        .rready(l_rready),
        .awid(l_awid),
        .awaddr(l_awaddr),
        .awlen(l_awlen),
        .awsize(l_awsize),
        .awburst(l_awburst),
        .awvalid(l_awvalid),
        .awready(l_awready),
        .wid(l_wid),
        .wdata(l_wdata),
        .wstrb(l_wstrb),
        .wlast(l_wlast),
        .wvalid(l_wvalid),
        .wready(l_wready),
        .bid(l_bid),
        .bresp(l_bresp),
        .bvalid(l_bvalid),
        .bready(l_bready),
        .uart_rx(uart_rx), .uart_tx(uart_tx),
        .hid_key_valid(1'b0), .hid_key_data(8'b0), .hid_key_ready(),
        .console_char_valid(console_valid), .console_char_data(console_data),
        .mmio_addr(mmio_addr), .mmio_wr(mmio_wr),
        .mmio_wdata(mmio_wdata), .mmio_wstrb(mmio_wstrb),
        .mmio_rdata(mmio_rdata), .mmio_valid(1'b1)
    );
    // Bounded, read-only SPI transaction model for four startup paths only.
    // It does not model erase/program, physical SPI pins or device timing.
    reg [7:0] flash_bytes[0:255];
    reg [7:0] spi_reply = 8'hff;
    reg [23:0] spi_address = 0;
    integer spi_phase = 0, flash_payload_reads = 0;
    reg spi_selected = 0;
    string flash_case;
    reg got_autoboot = 0, got_cancel = 0, got_flash_error = 0;
    reg [63:0] flash_countdown_tick = 0;
    always @(posedge clk) if (resetn && mmio_wr) begin
        if (mmio_addr == 32'h1fe00204) begin
            spi_selected <= !mmio_wdata[0]; spi_phase <= 0; spi_reply <= 8'hff;
        end
        if (mmio_addr == 32'h1fe0020c && spi_selected) begin
            case (spi_phase)
                0: begin
                    if (mmio_wdata[7:0] != 8'h03 && mmio_wdata[7:0] != 8'h9f)
                        $fatal(1, "Startup must only issue SPI read, command=%02x", mmio_wdata[7:0]);
                    spi_phase <= mmio_wdata[7:0] == 8'h03 ? 1 : 5;
                end
                1: begin spi_address[23:16] <= mmio_wdata[7:0]; spi_phase <= 2; end
                2: begin spi_address[15:8] <= mmio_wdata[7:0]; spi_phase <= 3; end
                3: begin spi_address[7:0] <= mmio_wdata[7:0]; spi_phase <= 4; end
                4: begin
                    spi_reply <= 8'hff;
                    if (flash_case != "none") begin
                        if (spi_address >= 24'h800000 && spi_address < 24'h800020)
                            spi_reply <= flash_bytes[spi_address - 24'h800000];
                        else if (spi_address >= 24'h801000 && spi_address < 24'h8010e0) begin
                            if (!got_autoboot || console_time < flash_countdown_tick + 64'd3 * 49500000)
                                $fatal(1, "Flash payload loaded before the three-second cancellation window");
                            if (flash_case == "cancel") $fatal(1, "Cancelled startup read payload");
                            spi_reply <= flash_bytes[32 + spi_address - 24'h801000];
                            flash_payload_reads <= flash_payload_reads + 1;
                        end else $fatal(1, "Flash read escaped the bounded fixture");
                    end
                    spi_address <= spi_address + 1;
                end
                5: begin spi_reply <= 8'h20; spi_phase <= 6; end
                6: begin spi_reply <= 8'hba; spi_phase <= 7; end
                7: begin spi_reply <= 8'h18; spi_phase <= 8; end
                default: $fatal(1, "Invalid SPI test state");
            endcase
        end
        if (mmio_addr == 32'h1fe003f0) begin
            if (flash_case != "valid" || mmio_wdata != 32'hf1a5b007 ||
                flash_payload_reads == 0 || !got_autoboot || prompts != 0)
                $fatal(1, "Unexpected Flash payload jump or arguments");
            $display("CPU_FLASH_AUTOBOOT_PASS case=valid cycles=%0d payload_bytes=%0d timer_stimulus_scale=4096", cycle, flash_payload_reads);
            $finish;
        end
    end
    always @(*) begin
        case (mmio_addr)
            32'h1fe0020c: mmio_rdata = {24'd0, spi_reply};
            32'h1fe00300: mmio_rdata = 32'h53563300;
            32'h1fe00304: mmio_rdata = 1;
            32'h1fe00308: mmio_rdata = 49500000;
            32'h1fe0030c: mmio_rdata = 31;
            32'h1fe00314: mmio_rdata = coremark_cpu_hz;
            32'h1fe00318: mmio_rdata = 49500000;
            default: mmio_rdata = 0;
        endcase
    end

    // Independent AXI R/W backpressure and full 8-beat cache lines.
    reg [31:0] memory[0:16383];
    integer i;
    reg [31:0] cycle = 0, rd_addr = 0, wr_addr = 0;
    reg [63:0] cpu_cycles = 0;
    always @(posedge cpu_clk) if (cpu_resetn) cpu_cycles <= cpu_cycles + 64'd1;
    reg [7:0] rd_left = 0, wr_left = 0;
    reg [3:0] rd_id = 0, wr_id = 0;
    reg rd_pending = 0, wr_pending = 0;
    reg [31:0] d_rdata_reg = 0;
    reg d_rvalid_reg = 0, d_rlast_reg = 0, d_bvalid_reg = 0;
    reg [3:0] d_rid_reg = 0, d_bid_reg = 0;
    integer burst_reads = 0, burst_writes = 0, alias_reads = 0, alias_writes = 0;
    assign d_arready = !rd_pending && !d_rvalid_reg && cycle[1:0] != 0;
    assign d_awready = !wr_pending && !d_bvalid_reg && cycle[1:0] == 1;
    assign d_wready = wr_pending && !d_bvalid_reg && cycle[1:0] != 2;
    assign d_rdata = d_rdata_reg;
    assign d_rid = d_rid_reg;
    assign d_rresp = 0;
    assign d_rlast = d_rlast_reg;
    assign d_rvalid = d_rvalid_reg;
    assign d_bid = d_bid_reg;
    assign d_bresp = 0;
    assign d_bvalid = d_bvalid_reg;
    always @(posedge clk) begin
        if (resetn) begin
            cycle <= cycle + 1;
            if (cpu.u_cpu_wrapper.fatal_memory_error) $fatal(1, "CPU_FATAL_MEMORY_ERROR");
            if (c_arvalid && c_arready && c_araddr[31:16] == 16'h0200)
                $fatal(1, "CLINT escaped the CPU wrapper");
            if (c_arvalid && c_arready && c_araddr[31:30] == 2'b10) begin
                alias_reads <= alias_reads + 1;
                if (c_arlen != 0) $fatal(1, "DDR alias read was cached");
            end
            if (c_awvalid && c_awready && c_awaddr[31:30] == 2'b10) begin
                alias_writes <= alias_writes + 1;
                if (c_awlen != 0) $fatal(1, "DDR alias write was cached");
            end
            if (d_arvalid && d_arready) begin
                if (d_araddr[31] || d_arlen > 7 || d_arsize > 2)
                    $fatal(1, "bad DDR AR mapping");
                rd_pending <= 1; rd_addr <= d_araddr; rd_id <= d_arid;
                rd_left <= d_arlen;
                if (d_arlen == 7) burst_reads <= burst_reads + 1;
            end
            if (rd_pending && !d_rvalid_reg && cycle[1:0] != 0) begin
                d_rdata_reg <= memory[rd_addr[15:2]];
                d_rvalid_reg <= 1; d_rlast_reg <= rd_left == 0; d_rid_reg <= rd_id;
            end
            if (d_rvalid_reg && d_rready) begin
                d_rvalid_reg <= 0;
                if (rd_left == 0) rd_pending <= 0;
                else begin rd_left <= rd_left - 1'b1; rd_addr <= rd_addr + 4; end
            end
            if (d_awvalid && d_awready) begin
                if (d_awaddr[31] || d_awlen > 7 || d_awsize > 2)
                    $fatal(1, "bad DDR AW mapping");
                wr_pending <= 1; wr_addr <= d_awaddr; wr_id <= d_awid;
                wr_left <= d_awlen;
                if (d_awlen == 7) burst_writes <= burst_writes + 1;
            end
            if (d_wvalid && d_wready) begin
                if (d_wlast != (wr_left == 0) || d_wid != wr_id)
                    $fatal(1, "bad DDR WLAST/ID");
                if (d_wstrb[0]) memory[wr_addr[15:2]][7:0] <= d_wdata[7:0];
                if (d_wstrb[1]) memory[wr_addr[15:2]][15:8] <= d_wdata[15:8];
                if (d_wstrb[2]) memory[wr_addr[15:2]][23:16] <= d_wdata[23:16];
                if (d_wstrb[3]) memory[wr_addr[15:2]][31:24] <= d_wdata[31:24];
                if (wr_left == 0) begin
                    wr_pending <= 0; d_bvalid_reg <= 1; d_bid_reg <= wr_id;
                end else begin wr_left <= wr_left - 1'b1; wr_addr <= wr_addr + 4; end
            end
            if (d_bvalid_reg && d_bready) d_bvalid_reg <= 0;
        end
    end

    reg production_mode, coremark_short_mode, production_coremark_mode;
    reg coremark_pilot_mode, coremark_validation_mode;
    string coremark_rom;
    string coremark_mode;
    reg [63:0] previous_mtime = 0;
    reg [63:0] integration_mtime = 0;
    reg integration_mtime_valid = 0;
    integer integration_mtime_checks = 0;
    always @(negedge clk) begin
        if (!resetn) begin
            integration_mtime_valid = 0;
            integration_mtime_checks = 0;
        end else if (!production_mode && !coremark_short_mode &&
                     integration_mtime_checks < 256) begin
            // The integration firmware intentionally rewrites mtime later.
            if (integration_mtime_valid &&
                cpu.u_cpu_wrapper.u_clint.mtime !== integration_mtime + 64'd1)
                $fatal(1, "Integration CLINT mtime did not advance once per SYS edge");
            integration_mtime = cpu.u_cpu_wrapper.u_clint.mtime;
            integration_mtime_valid = 1;
            integration_mtime_checks = integration_mtime_checks + 1;
        end
    end
    always @(posedge clk) if (resetn && coremark_short_mode) begin
        if (cycle != 0 && cpu.u_cpu_wrapper.u_clint.mtime != previous_mtime + 64'd1)
            $fatal(1, "CoreMark CLINT must advance exactly once per SYS clock");
        previous_mtime <= cpu.u_cpu_wrapper.u_clint.mtime;
    end
    reg coremark_timer_released = 0;
    reg coremark_done = 0;
    reg [63:0] cpu_cycles_start = 0;
    reg [63:0] clock_ratio_delta = 0;
    integer coremark_real_timer_cycles = 0;
    integer coremark_max_cycles = 1200000000;
    always @(negedge clk) if (resetn && coremark_timer_released) begin
        if (cpu.u_cpu_wrapper.u_clint.mtime !== previous_mtime + 64'd1)
            $fatal(1, "Production CoreMark CLINT did not advance exactly once per SYS cycle");
        previous_mtime = cpu.u_cpu_wrapper.u_clint.mtime;
        coremark_real_timer_cycles = coremark_real_timer_cycles + 1;
    end
    reg [63:0] previous_mcycle = 0;
    integer mcycle_checks = 0;
    reg mcycle_armed = 0;
    always @(negedge cpu_clk) begin
        if (!cpu_resetn) begin
            mcycle_checks = 0;
            mcycle_armed = 0;
        end else if (mcycle_checks < 1024) begin
            // CoreTop's internal reset can outlast the wrapper reset edge.
            // Arm on the first nonzero cycle, then require every CPU edge.
            if (!mcycle_armed) begin
                if (cpu.u_cpu_wrapper.u_cpu.core.backend.u_csr_trap.cycle != 0) begin
                    previous_mcycle = cpu.u_cpu_wrapper.u_cpu.core.backend.u_csr_trap.cycle;
                    mcycle_armed = 1;
                    mcycle_checks = 1;
                end
            end else begin
                if (cpu.u_cpu_wrapper.u_cpu.core.backend.u_csr_trap.cycle !== previous_mcycle + 64'd1)
                $fatal(1, "CPU mcycle did not advance once per CPU cycle sample=%0d previous=%0d current=%0d",
                       mcycle_checks, previous_mcycle,
                       cpu.u_cpu_wrapper.u_cpu.core.backend.u_csr_trap.cycle);
                previous_mcycle = cpu.u_cpu_wrapper.u_cpu.core.backend.u_csr_trap.cycle;
                mcycle_checks = mcycle_checks + 1;
            end
        end
    end
    // The production PHY reset waits four real seconds. Only this console
    // mode accelerates the timer stimulus; firmware and its timeout constants
    // remain unchanged. The separate integration program checks real CLINT
    // tick/register/interrupt behavior with this force disabled.
    reg [63:0] console_time = 0;
    always @(posedge clk) if (resetn && production_mode)
        console_time <= console_time + 64'd4096;
    reg [511:0] console_tail = 0;
    integer prompts = 0, tx_count = 0;
    integer rejected_entries = 0, rejected_addresses = 0;
    reg got_debug = 0, got_info = 0, got_help = 0, got_uart_echo = 0;
    reg got_banner = 0;
    reg [31:0] test_stage = 0, fail_cause = 0;
    always @(posedge clk) if (resetn && mmio_wr) begin
        if (mmio_addr == 32'h1fe003f8) test_stage <= mmio_wdata;
        if (mmio_addr == 32'h1fe003f4) fail_cause <= mmio_wdata;
    end
    always @(posedge clk) if (resetn && console_valid) begin
        if (coremark_short_mode || production_coremark_mode) $write("%c", console_data);
        console_tail <= {console_tail[503:0], console_data};
        tx_count <= tx_count + 1;
        if ({console_tail[31:0], console_data} == "soc> ") prompts <= prompts + 1;
        if ({console_tail[95:0], console_data} == "COREMARK_DONE") coremark_done <= 1;
        if ({console_tail[111:0], console_data} == "debug camera_sd") got_debug <= 1;
        if ({console_tail[127:0], console_data} == "SYS_ID=0x53563300") got_info <= 1;
        if ({console_tail[183:0], console_data} == "help | info | debug help") got_help <= 1;
        if ({console_tail[15:0], console_data} == "V3Z") got_uart_echo <= 1;
        if ({console_tail[143:0], console_data} == "SoC V2.1 bootloader") got_banner <= 1;
        if ({console_tail[87:0], console_data} == "key cancels.") begin
            got_autoboot <= 1; flash_countdown_tick <= console_time;
        end
        if ({console_tail[127:0], console_data} == "Autoboot stopped.") got_cancel <= 1;
        if ({console_tail[143:0], console_data} == "Flash image invalid") got_flash_error <= 1;
        if ({console_tail[63:0], console_data} == "DDR entry") rejected_entries <= rejected_entries + 1;
        if ({console_tail[79:0], console_data} == "DDR address") rejected_addresses <= rejected_addresses + 1;
    end
    always @(posedge clk) if (resetn && mmio_wr && mmio_addr == 32'h1fe003fc) begin
        if (coremark_short_mode) begin
            if (mmio_wdata != 32'hc04e0001)
                $fatal(1, "CoreMark short run failed to enforce the production ten-second minimum: %08x", mmio_wdata);
            $display("CPU_COREMARK_SHORT_EXECUTED cycles=%0d clint_ticks=%0d timer_stimulus_scale=1", cycle, cpu.u_cpu_wrapper.u_clint.mtime);
            $finish;
        end else begin
        if (production_mode || mmio_wdata != 32'h600dbeef)
            $fatal(1, "CPU_INTEGRATION_FAIL result=%08x stage=%0d mcause=%08x", mmio_wdata, test_stage, fail_cause);
        if (burst_reads < 1 || burst_writes < 1 || alias_reads < 2 ||
            alias_writes < 2 || !got_uart_echo)
            $fatal(1, "missing integration coverage R=%0d W=%0d aliasR=%0d aliasW=%0d echo=%0d",
                burst_reads, burst_writes, alias_reads, alias_writes, got_uart_echo);
        $display("CPU_AXI_CLINT_UART_DDR_PASS cycles=%0d", cycle);
        $finish;
        end
    end

    task send_byte(input [7:0] value);
        integer bit_index;
        begin
            @(negedge clk); uart_rx = 0; repeat (8) @(negedge clk);
            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
                uart_rx = value[bit_index]; repeat (8) @(negedge clk);
            end
            uart_rx = 1; repeat (24) @(negedge clk);
        end
    endtask
    task send_command(input string command);
        integer index;
        begin
            for (index = 0; index < command.len(); index = index + 1)
                send_byte(command[index]);
            send_byte(8'h0d);
        end
    endtask
    initial begin
        production_coremark_mode = $test$plusargs("production_coremark");
        production_mode = $test$plusargs("production_bootloader") || production_coremark_mode;
        coremark_short_mode = $test$plusargs("coremark_short");
        coremark_pilot_mode = $test$plusargs("coremark_pilot");
        if ($value$plusargs("cpu_hz=%d", coremark_cpu_hz)) begin end
        if (coremark_cpu_hz <= 0) $fatal(1, "Invalid simulated CPU frequency");
        // The 1 fs simulator precision rounds each half-period independently.
        coremark_cpu_half_fs = (64'd500000000000000 +
                                (64'd1 * coremark_cpu_hz) / 2) / coremark_cpu_hz;
        if (production_coremark_mode)
            $display("SIM_CLOCK_QUANTIZATION cpu_half_fs=%0d sys_half_fs=%0d",
                     coremark_cpu_half_fs, COREMARK_SYS_HALF_FS);
        coremark_mode = "performance";
        if ($value$plusargs("coremark_mode=%s", coremark_mode)) begin end
        if (production_coremark_mode && coremark_mode != "performance" && coremark_mode != "validation")
            $fatal(1, "Unsupported production CoreMark mode");
        coremark_validation_mode = coremark_mode == "validation";
        if (coremark_pilot_mode && !production_coremark_mode)
            $fatal(1, "Pilot mode requires production CoreMark mode");
        if ($value$plusargs("max_cycles=%d", coremark_max_cycles)) begin end
        if (coremark_max_cycles < 1000 || coremark_max_cycles > 1500000000)
            $fatal(1, "Invalid CoreMark cycle bound");
        flash_case = "none";
        if ($value$plusargs("flash_case=%s", flash_case)) begin
            if (!production_mode || (flash_case != "valid" && flash_case != "cancel" && flash_case != "badcrc"))
                $fatal(1, "Unsupported Flash startup case");
        end
        for (i = 0; i < 256; i = i + 1) flash_bytes[i] = 8'hff;
        if (flash_case != "none") begin
            $readmemh("artifacts/selftest/flash_autoboot.hex", flash_bytes);
            if (flash_case == "badcrc") flash_bytes[32] = flash_bytes[32] ^ 8'h01;
        end
        if (production_mode && coremark_short_mode)
            $fatal(1, "Choose production console or isolated CoreMark, not both");
        for (i = 0; i < 16384; i = i + 1) memory[i] = 0;
        #1;
        if (coremark_short_mode) begin
            if (!$value$plusargs("coremark_rom=%s", coremark_rom))
                $fatal(1, "Missing isolated CoreMark ROM path");
            $readmemh(coremark_rom, local_bus.memory);
        end else if (production_mode) begin
            if (production_coremark_mode && $value$plusargs("coremark_rom=%s", coremark_rom))
                $readmemh(coremark_rom, local_bus.memory);
            else
                $readmemh("artifacts/bootrom.hex", local_bus.memory);
            force cpu.u_cpu_wrapper.u_clint.mtime = console_time;
        end else begin
            $readmemh("artifacts/selftest/cpu_integration.hex", local_bus.memory);
        end
        repeat (20) @(negedge clk);
        resetn = 1;
        repeat (3) @(negedge cpu_clk);
        cpu_resetn = 1;
        if (coremark_short_mode) begin
            // The test firmware reports its production-port return value.
            // The host also checks the official CRCs and actual CLINT ticks.
        end else if (!production_mode) begin
            wait (tx_count >= 2);
            send_byte("Z");
        end else begin
            if (flash_case == "cancel") begin
                wait (got_autoboot); send_byte("X");
            end
            if (flash_case == "valid") wait (1'b0); // Payload emits the success marker.
            wait (prompts == 1);
            if (production_coremark_mode) begin
                if (prompts != 1)
                    $fatal(1, "Production CoreMark did not reach the bootloader console");
                send_command("info");
                wait (prompts == 2);
                if (!got_info) $fatal(1, "Production hardware info command did not report SYS_ID");
                @(negedge clk);
                release cpu.u_cpu_wrapper.u_clint.mtime;
                previous_mtime = cpu.u_cpu_wrapper.u_clint.mtime;
                @(posedge clk);
                cpu_cycles_start = cpu_cycles;
                coremark_timer_released = 1;
                if (coremark_validation_mode) send_command("coremark validate");
                else send_command("coremark");
                wait (prompts == 3);
                if (!coremark_done || coremark_real_timer_cycles < 1000)
                    $fatal(1, "CoreMark report or unaccelerated timer coverage missing");
                // Compare the actual quantized waveforms. The two asynchronous
                // sample boundaries may differ by up to three CPU cycles.
                if ((cpu_cycles - cpu_cycles_start) * coremark_cpu_half_fs >=
                    64'd1 * coremark_real_timer_cycles * COREMARK_SYS_HALF_FS)
                    clock_ratio_delta = (cpu_cycles - cpu_cycles_start) * coremark_cpu_half_fs -
                                        64'd1 * coremark_real_timer_cycles * COREMARK_SYS_HALF_FS;
                else
                    clock_ratio_delta = 64'd1 * coremark_real_timer_cycles * COREMARK_SYS_HALF_FS -
                                        (cpu_cycles - cpu_cycles_start) * coremark_cpu_half_fs;
                if (clock_ratio_delta > 64'd6 * coremark_cpu_half_fs)
                    $fatal(1, "CPU/SYS clock ratio did not match simulated cpu_hz");
                $display("\nCPU_PRODUCTION_COREMARK_DONE mode=%s pilot=%0d cycles=%0d real_timer_cycles=%0d cpu_hz=%0d timer_stimulus_scale=1 observed_cpu_cycles_timer_release_to_prompt=%0d",
                         coremark_mode, coremark_pilot_mode, cycle, coremark_real_timer_cycles, coremark_cpu_hz,
                         cpu_cycles - cpu_cycles_start);
                $finish;
            end
            if (flash_case == "cancel" || flash_case == "badcrc") begin
                if (!got_autoboot ||
                    (flash_case == "cancel" && (!got_cancel || got_flash_error || flash_payload_reads != 0)) ||
                    (flash_case == "badcrc" && (!got_flash_error || got_cancel || flash_payload_reads == 0)))
                    $fatal(1, "Flash startup did not return directly to console");
                $display("CPU_FLASH_AUTOBOOT_PASS case=%s cycles=%0d payload_bytes=%0d timer_stimulus_scale=4096", flash_case, cycle, flash_payload_reads);
                $finish;
            end
            if (got_autoboot || flash_payload_reads != 0)
                $fatal(1, "Missing Flash image must enter console without autoboot");
            send_command("help");
            wait (prompts == 2);
            send_command("debug help");
            wait (prompts == 3);
            send_command("info");
            wait (prompts == 4);
            send_command("boot 0x02000000");
            wait (prompts == 5);
            send_command("boot 0x00100002");
            wait (prompts == 6);
            send_command("loadx 0x02000000");
            wait (prompts == 7);
            if (!got_help || !got_debug || !got_info || !got_banner)
                $fatal(1, "production console response missing help=%0d debug=%0d info=%0d banner=%0d",
                       got_help, got_debug, got_info, got_banner);
            if (rejected_entries != 2 || rejected_addresses != 1)
                $fatal(1, "production console failed CLINT/alignment address rejection");
            $display("CPU_PRODUCTION_CONSOLE_PASS cycles=%0d timer_stimulus_scale=4096", cycle);
            $finish;
        end
    end
    initial begin
        #2;
        if (production_coremark_mode) repeat (coremark_max_cycles) @(posedge clk);
        else if (coremark_short_mode) repeat (20000000) @(posedge clk);
        else repeat (2000000) @(posedge clk);
        $fatal(1, "CPU_INTEGRATION_TIMEOUT cycles=%0d prompts=%0d tail=%s",
            cycle, prompts, console_tail);
    end
endmodule
