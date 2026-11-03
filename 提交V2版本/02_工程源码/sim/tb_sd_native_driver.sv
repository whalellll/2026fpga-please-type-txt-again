`timescale 1ns/1ps

module tb_sd_native_driver;
    reg clk = 1'b0;
    reg resetn = 1'b0;
    always #10.101 clk = ~clk;

    wire [3:0] arid, awid, wid;
    wire [31:0] araddr, awaddr, wdata;
    wire [7:0] arlen, awlen;
    wire [2:0] arsize, arprot, awsize, awprot;
    wire [1:0] arburst, arlock, awburst, awlock;
    wire [3:0] arcache, awcache, wstrb;
    wire arvalid, arready, rlast, rready;
    wire awvalid, awready, wlast, wvalid, wready, bready;
    reg [3:0] rid, bid;
    reg [31:0] rdata;
    reg [1:0] rresp, bresp;
    reg rvalid, bvalid;

    cpu_core_top #(.RESET_VECTOR(32'h0000_0000)) cpu (
        .cpu_clk(clk), .cpu_resetn(resetn),
        .sys_clk(clk), .sys_resetn(resetn), .external_interrupts(32'b0),
        .arid(arid), .araddr(araddr), .arlen(arlen), .arsize(arsize),
        .arburst(arburst), .arlock(arlock), .arcache(arcache), .arprot(arprot),
        .arvalid(arvalid), .arready(arready), .rid(rid), .rdata(rdata),
        .rresp(rresp), .rlast(rlast), .rvalid(rvalid), .rready(rready),
        .awid(awid), .awaddr(awaddr), .awlen(awlen), .awsize(awsize),
        .awburst(awburst), .awlock(awlock), .awcache(awcache), .awprot(awprot),
        .awvalid(awvalid), .awready(awready), .wid(wid), .wdata(wdata),
        .wstrb(wstrb), .wlast(wlast), .wvalid(wvalid), .wready(wready),
        .bid(bid), .bresp(bresp), .bvalid(bvalid), .bready(bready)
    );

    reg [31:0] memory [0:32767];
    integer memory_index;
    initial begin
        for (memory_index = 0; memory_index < 32768;
             memory_index = memory_index + 1)
            memory[memory_index] = 32'b0;
        $readmemh("artifacts/selftest/sd_native_driver_test.hex", memory);
    end

    reg write_pending = 1'b0;
    reg [31:0] saved_awaddr;
    reg [3:0] saved_awid;
    reg [7:0] saved_awleft;
    reg [2:0] saved_awsize;
    wire write_fire = wvalid && wready;
    wire [31:0] peripheral_addr = write_fire ? saved_awaddr : saved_araddr;
    wire peripheral_write = write_fire &&
                            (saved_awaddr >= 32'h1fe1_3000) &&
                            (saved_awaddr < 32'h1fe1_3500);

    wire [31:0] sd_rdata;
    wire sd_hit;
    wire sd_clk;
    reg card_cmd = 1'b1;
    wire sd_cmd_out;
    wire sd_cmd_oe;
    wire [3:0] sd_dat_out;wire sd_dat_oe;
    reg [3:0] card_dat = 4'hf;
    reg sd_detect_n = 1'b0;

    sd_native_mmio #(
        .BASE(32'h1fe1_3000),
        .RESET_DIV(16'd63),
        .DEBOUNCE_CYCLES(4),
        .CMD_TIMEOUT_CLOCKS(128),
        .DATA_TIMEOUT_CLOCKS(4096),
        .BUSY_TIMEOUT_CLOCKS(128),
        .WRITE_TIMEOUT_CLOCKS(4096),
        .TX_WAIT_TIMEOUT_CYCLES(131072)
    ) sd_host (
        .clk(clk), .resetn(resetn), .addr(peripheral_addr),
        .wr(peripheral_write), .wdata(wdata), .wstrb(wstrb),
        .rdata(sd_rdata), .hit(sd_hit), .sd_clk(sd_clk),
        .sd_cmd_in(card_cmd), .sd_cmd_out(sd_cmd_out),
        .sd_cmd_oe(sd_cmd_oe), .sd_dat_in(card_dat),.sd_dat_out(sd_dat_out),.sd_dat_oe(sd_dat_oe),
        .sd_detect_n(sd_detect_n)
    );

    // Keep a bounded in-memory retirement window; print only on timeout.
    reg [31:0] retire_window [0:31];
    integer retire_count = 0;
    integer retire_dump;
    always @(posedge clk) begin
        if (resetn && cpu.u_cpu.core.backend.u_commit.io_retire0Valid) begin
            retire_window[retire_count % 32] = cpu.u_cpu.core.backend.u_commit.io_retire0Pc;
            retire_count = retire_count + 1;
        end
        if (resetn && cpu.u_cpu.core.backend.u_commit.io_retire1Valid) begin
            retire_window[retire_count % 32] = cpu.u_cpu.core.backend.u_commit.io_retire1Pc;
            retire_count = retire_count + 1;
        end
    end

    // current CPU cache-line AXI responses stay stable until accepted.
    reg read_pending = 1'b0;
    reg [31:0] saved_araddr;
    reg [7:0] saved_arleft;
    reg [2:0] saved_arsize;
    // Match axi_boot_periph's one shared MMIO port: a write owns the port
    // until B, and an in-flight read keeps its address until the final R.
    assign arready = !read_pending && !rvalid && !write_pending && !bvalid && !awvalid;
    assign rlast = saved_arleft == 0;
    always @(posedge clk) begin
        if (!resetn) begin
            read_pending <= 0; rid <= 0; rdata <= 0; rresp <= 0; rvalid <= 0;
            saved_araddr <= 0; saved_arleft <= 0; saved_arsize <= 0;
        end else begin
            if (arvalid && arready) begin
                read_pending <= 1; rid <= arid;
                saved_araddr <= araddr; saved_arleft <= arlen; saved_arsize <= arsize;
                if (arlen > 7 || arsize > 2 || arburst != 1)
                    $fatal(1, "unsupported current CPU AXI read");
            end
            if (read_pending && !rvalid) begin
                rvalid <= 1;
                if (saved_araddr < 32'h00020000) begin
                    rdata <= memory[saved_araddr[16:2]]; rresp <= 0;
                end
                else if (saved_araddr == 32'h80000008) begin
                    rdata <= app_fault_mode; rresp <= 0;
                end else if (saved_araddr >= 32'h1fe13000 && saved_araddr < 32'h1fe13500) begin
                    rdata <= sd_rdata; rresp <= 0;
                end
                else begin rdata <= 0; rresp <= 2'b11; end
            end
            if (rvalid && rready) begin
                rvalid <= 0;
                if (saved_arleft == 0) read_pending <= 0;
                else begin
                    saved_arleft <= saved_arleft - 1'b1;
                    saved_araddr <= saved_araddr + (32'd1 << saved_arsize);
                end
            end
        end
    end

    assign awready = !write_pending && !bvalid && !read_pending && !rvalid;
    assign wready = write_pending && !bvalid;
    always @(posedge clk) begin
        if (!resetn) begin
            write_pending <= 1'b0;
            saved_awaddr <= 32'b0;
            saved_awid <= 4'b0; saved_awleft <= 0; saved_awsize <= 0;
            bid <= 4'b0;
            bresp <= 2'b0;
            bvalid <= 1'b0;
        end else begin
            if (awvalid && awready) begin
                write_pending <= 1'b1;
                saved_awaddr <= awaddr;
                saved_awid <= awid; saved_awleft <= awlen; saved_awsize <= awsize;
                if (awlen > 7 || awsize > 2 || awburst != 1)
                    $fatal(1, "unsupported current CPU AXI write");
            end
            if (write_fire) begin
                if (wlast != (saved_awleft == 0) || wid != saved_awid)
                    $fatal(1, "current CPU write burst WLAST/ID mismatch");
                if (wlast) begin
                    write_pending <= 0; bid <= saved_awid; bresp <= 0; bvalid <= 1;
                end else begin
                    saved_awleft <= saved_awleft - 1'b1;
                    saved_awaddr <= saved_awaddr + (32'd1 << saved_awsize);
                end
                if (saved_awaddr < 32'h0002_0000) begin
                    if (wstrb[0]) memory[saved_awaddr[16:2]][7:0] <= wdata[7:0];
                    if (wstrb[1]) memory[saved_awaddr[16:2]][15:8] <= wdata[15:8];
                    if (wstrb[2]) memory[saved_awaddr[16:2]][23:16] <= wdata[23:16];
                    if (wstrb[3]) memory[saved_awaddr[16:2]][31:24] <= wdata[31:24];
                end
                if (saved_awaddr == 32'h8000_0004) begin
                    $display("SD_NATIVE_DRIVER_FAIL code=%08x", wdata);
                    $fatal(1);
                end
                if (saved_awaddr == 32'h8000_0000) begin
                    if (wdata != 32'h4e44_534d || wstrb != 4'hf)
                        $fatal(1, "native SD driver result mismatch: %08x/%x",
                               wdata, wstrb);
                    if(app_fault_mode!=0)begin
                        if(sequence_errors||command_crc_errors||cmd55_count!=6||
                           cmd25_count||cmd24_count||cmd13_count||
                           acmd23_count!=(app_fault_mode==2?1:0))
                            $fatal(1,"missing APP_CMD did not reject before data/write");
                        $display("SD_NATIVE_DRIVER_APP_CMD_MISSING_REJECT_PASS mode=%0d",app_fault_mode);
                        $finish;
                    end else begin
                    if (sequence_errors != 0 || command_crc_errors != 0 ||
                        cmd0_count != 1 || cmd8_count != 1 ||
                        cmd55_count != (high_capacity_mode?8:5) || acmd41_count != 2 ||
                        cmd2_count != 1 || cmd3_count != 1 ||
                        cmd9_count != 1 || cmd7_count != 1 ||
                        acmd51_count != 1 || acmd42_count != 1 ||
                        acmd6_count != 1 || cmd17_count != (high_capacity_mode?9:4) ||
                        cmd24_count != (high_capacity_mode?5:0) || cmd13_count != (high_capacity_mode?8:0) ||
                        cmd25_count != (high_capacity_mode?3:0) || acmd23_count != (high_capacity_mode?3:0) ||
                        stream_blocks != (high_capacity_mode?16:0) ||
                        (high_capacity_mode && (cancel_blocks<1 || cancel_blocks>=8)) ||
                        cmd18_count != (high_capacity_mode?6:4) || cmd12_count != (high_capacity_mode?9:4) ||
                        manual_cmd12_count != 1 || auto_cmd12_count != (high_capacity_mode?8:3) ||
                        boundary_out_of_range_count != 1 ||
                        injected_crc_errors != 2 ||
                        injected_response_crc_errors != 2 ||
                        cmd17_data_crc_attempts != 2 ||
                        cmd17_data_crc_cmd12_errors != 0 ||
                        cmd17_response_crc_attempts != 2 ||
                        cmd17_response_crc_cmd12_errors != 0 ||
                        batch_cmd18_attempts != 2 ||
                        boundary_cmd18_attempts != 2 ||
                        auto_cmd12_duplicate_errors != 0 ||
                        (high_capacity_mode != 0 && cmd16_count != 0) ||
                        (high_capacity_mode == 0 && cmd16_count != 1)) begin
                        $display("SD_NATIVE_DRIVER_COUNTS mode=%0d seq=%0d crc=%0d",
                                 high_capacity_mode, sequence_errors,
                                 command_crc_errors);
                        $display("CMD 0=%0d 8=%0d 55=%0d 41=%0d 2=%0d 3=%0d 9=%0d 7=%0d 16=%0d",
                                 cmd0_count, cmd8_count, cmd55_count,
                                 acmd41_count, cmd2_count, cmd3_count,
                                 cmd9_count, cmd7_count, cmd16_count);
                        $display("CMD 51=%0d 42=%0d 6=%0d 17=%0d 18=%0d 12=%0d manual=%0d auto=%0d boundary_oor=%0d data_crc_inject=%0d response_crc_inject=%0d",
                                  acmd51_count, acmd42_count, acmd6_count,
                                  cmd17_count, cmd18_count, cmd12_count,
                                  manual_cmd12_count, auto_cmd12_count,
                                  boundary_out_of_range_count,
                                  injected_crc_errors,
                                  injected_response_crc_errors);
                        $display("RECOVERY cmd17_data_attempts=%0d stop_errors=%0d cmd17_response_attempts=%0d stop_errors=%0d batch18_attempts=%0d boundary18_attempts=%0d duplicate_stop_errors=%0d",
                                 cmd17_data_crc_attempts,
                                 cmd17_data_crc_cmd12_errors,
                                 cmd17_response_crc_attempts,
                                 cmd17_response_crc_cmd12_errors,
                                 batch_cmd18_attempts,
                                 boundary_cmd18_attempts,
                                 auto_cmd12_duplicate_errors);
                        $fatal(1);
                    end
                    if (high_capacity_mode != 0)
                        $display("SD_NATIVE_DRIVER_WRITE_ALIGNED_UNALIGNED_512_BYTES_CRC_BUSY_PASS");
                    if (high_capacity_mode != 0)
                        $display("SD_NATIVE_DRIVER_CMD25_EIGHT_SECTORS_REFILL_ALIGN_CANCEL_READY_PASS");
                    $display("SD_NATIVE_DRIVER_PASS mode=%s blocks=32 retry=1",
                             high_capacity_mode != 0 ? "SDHC" : "SDSC");
                    $finish;
                    end
                end
            end
            if (bvalid && bready)
                bvalid <= 1'b0;
        end
    end

    integer high_capacity_mode;
    integer app_fault_mode;
    integer idle_clock_count;
    integer sequence_errors;
    integer command_crc_errors;
    integer card_ready;
    integer card_selected;
    integer card_bus4;
    integer app_command;
    integer cmd0_count;
    integer cmd8_count;
    integer cmd55_count;
    integer acmd41_count;
    integer cmd2_count;
    integer cmd3_count;
    integer cmd9_count;
    integer cmd7_count;
    integer cmd16_count;
    integer acmd51_count;
    integer acmd42_count;
    integer acmd6_count;
    integer cmd17_count;
    integer cmd24_count,cmd13_count;
    reg [7:0] written_bytes [0:511];
    reg [7:0] written_multi [0:4095];
    integer cmd25_count,acmd23_count,stream_blocks,cancel_blocks;
    integer active_write_stream;
    integer cmd18_count;
    integer cmd12_count;
    integer manual_cmd12_count;
    integer auto_cmd12_count;
    integer boundary_out_of_range_count;
    integer injected_crc_errors;
    integer cmd17_data_crc_attempts;
    integer awaiting_cmd17_data_retry;
    integer cmd17_data_crc_cmd12_errors;
    integer cmd17_response_crc_attempts;
    integer awaiting_cmd17_response_retry;
    integer cmd17_response_crc_cmd12_errors;
    integer batch_cmd18_attempts;
    integer boundary_cmd18_attempts;
    integer active_boundary_read;
    integer awaiting_boundary_cmd18_retry;
    integer auto_cmd12_duplicate_errors;
    integer injected_response_crc_errors;
    integer card_data_active;
    reg [47:0] received_command;
    integer received_command_bits;

    task calculate_crc7;
        input [39:0] protected_bits;
        output [6:0] result;
        integer bit_number;
        reg [6:0] crc;
        begin
            crc = 7'd0;
            for (bit_number = 39; bit_number >= 0;
                 bit_number = bit_number - 1) begin
                if (crc[6] ^ protected_bits[bit_number])
                    crc = {crc[5:0], 1'b0} ^ 7'h09;
                else
                    crc = {crc[5:0], 1'b0};
            end
            result = crc;
        end
    endtask

    task build_r48;
        input [5:0] response_index;
        input [31:0] response_payload;
        output [47:0] frame;
        reg [39:0] protected_bits;
        reg [6:0] crc;
        begin
            protected_bits = {2'b00, response_index, response_payload};
            calculate_crc7(protected_bits, crc);
            frame = {protected_bits, crc, 1'b1};
        end
    endtask

    task drive_r48;
        input [5:0] response_index;
        input [31:0] response_payload;
        reg [47:0] frame;
        integer bit_number;
        begin
            build_r48(response_index, response_payload, frame);
            wait (sd_cmd_oe === 1'b1);
            wait (sd_cmd_oe === 1'b0);
            card_cmd = frame[47];
            for (bit_number = 47; bit_number >= 0;
                 bit_number = bit_number - 1) begin
                @(posedge sd_clk);
                if (bit_number != 0) begin
                    @(negedge sd_clk);
                    card_cmd = frame[bit_number - 1];
                end
            end
            @(negedge sd_clk);
            card_cmd = 1'b1;
        end
    endtask

    task drive_r48_corrupt_crc;
        input [5:0] response_index;
        input [31:0] response_payload;
        reg [47:0] frame;
        integer bit_number;
        begin
            build_r48(response_index, response_payload, frame);
            frame[1] = ~frame[1];
            injected_response_crc_errors = injected_response_crc_errors + 1;
            wait (sd_cmd_oe === 1'b1);
            wait (sd_cmd_oe === 1'b0);
            card_cmd = frame[47];
            for (bit_number = 47; bit_number >= 0;
                 bit_number = bit_number - 1) begin
                @(posedge sd_clk);
                if (bit_number != 0) begin
                    @(negedge sd_clk);
                    card_cmd = frame[bit_number - 1];
                end
            end
            @(negedge sd_clk);
            card_cmd = 1'b1;
        end
    endtask

    task drive_r48_busy;
        input [5:0] response_index;
        input [31:0] response_payload;
        begin
            drive_r48(response_index, response_payload);
            card_dat = 4'b1110;
            repeat (2) @(posedge sd_clk);
            @(negedge sd_clk);
            card_dat = 4'hf;
        end
    endtask

    task build_r136;
        input [119:0] register_top_bits;
        output [135:0] frame;
        reg [6:0] crc;
        integer bit_number;
        begin
            crc = 7'd0;
            for (bit_number = 119; bit_number >= 0;
                 bit_number = bit_number - 1) begin
                if (crc[6] ^ register_top_bits[bit_number])
                    crc = {crc[5:0], 1'b0} ^ 7'h09;
                else
                    crc = {crc[5:0], 1'b0};
            end
            frame = {8'b0011_1111, register_top_bits, crc, 1'b1};
        end
    endtask

    task drive_r136;
        input [119:0] register_top_bits;
        reg [135:0] frame;
        integer bit_number;
        begin
            build_r136(register_top_bits, frame);
            wait (sd_cmd_oe === 1'b1);
            wait (sd_cmd_oe === 1'b0);
            card_cmd = frame[135];
            for (bit_number = 135; bit_number >= 0;
                 bit_number = bit_number - 1) begin
                @(posedge sd_clk);
                if (bit_number != 0) begin
                    @(negedge sd_clk);
                    card_cmd = frame[bit_number - 1];
                end
            end
            @(negedge sd_clk);
            card_cmd = 1'b1;
        end
    endtask

    task drive_csd;
        reg [31:0] csd0;
        reg [31:0] csd1;
        reg [31:0] csd2;
        reg [31:0] csd3;
        reg [21:0] c_size_v2;
        reg [11:0] c_size_v1;
        reg [119:0] register_top_bits;
        begin
            csd0 = 32'd0;
            csd1 = 32'd0;
            csd2 = 32'd0;
            csd3 = 32'd0;
            if (high_capacity_mode != 0) begin
                /* (C_SIZE + 1) * 1024 = 1,048,576 sectors. */
                c_size_v2 = 22'd1023;
                csd3[31:30] = 2'b01;
                csd2[5:0] = c_size_v2[21:16];
                csd1[31:16] = c_size_v2[15:0];
            end else begin
                /* READ_BL_LEN=9, C_SIZE_MULT=7, C_SIZE=2047 gives the
                 * same 1,048,576-sector test capacity. */
                c_size_v1 = 12'd2047;
                csd2[19:16] = 4'd9;
                csd2[9:0] = c_size_v1[11:2];
                csd1[31:30] = c_size_v1[1:0];
                csd1[17:15] = 3'd7;
            end
            register_top_bits = {csd3, csd2, csd1, csd0[31:8]};
            drive_r136(register_top_bits);
        end
    endtask

    task drive_scr;
        reg [63:0] payload;
        reg [15:0] crc;
        integer bit_number;
        begin
            /* Independent real-card vector: SD_SPEC=2/3 and 1/4-bit buses.
             * The literal CRC prevents the model and RTL sharing a bad CRC
             * implementation while exercising response/data overlap. */
            payload = 64'h0235_8003_0000_0000;
            crc = 16'h957e;
            card_dat = 4'b1110;
            @(posedge sd_clk);
            for (bit_number = 63; bit_number >= 0;
                 bit_number = bit_number - 1) begin
                @(negedge sd_clk);
                card_dat[0] = payload[bit_number];
                @(posedge sd_clk);
            end
            for (bit_number = 15; bit_number >= 0;
                 bit_number = bit_number - 1) begin
                @(negedge sd_clk);
                card_dat[0] = crc[bit_number];
                @(posedge sd_clk);
            end
            @(negedge sd_clk);
            card_dat = 4'hf;
            @(posedge sd_clk);
        end
    endtask

    task drive_data_block;
        input [31:0] lba;
        input integer corrupt_crc;
        integer byte_number;
        integer bit_number;
        reg [7:0] value;
        reg [3:0] nibble;
        reg [15:0] crc0;
        reg [15:0] crc1;
        reg [15:0] crc2;
        reg [15:0] crc3;
        begin
            card_data_active = 1;
            card_dat = 4'b0000;
            @(posedge sd_clk);
            crc0 = 16'd0;
            crc1 = 16'd0;
            crc2 = 16'd0;
            crc3 = 16'd0;
            for (byte_number = 0; byte_number < 512;
                 byte_number = byte_number + 1) begin
                if(lba==96)value=written_bytes[byte_number];
                else if(lba>=128&&lba<136)value=written_multi[(lba-128)*512+byte_number];
                else value=lba * 17 + byte_number * 13 + 8'h5a;
                @(negedge sd_clk);
                nibble = value[7:4];
                card_dat = nibble;
                @(posedge sd_clk);
                if (crc0[15] ^ nibble[0])
                    crc0 = {crc0[14:0], 1'b0} ^ 16'h1021;
                else
                    crc0 = {crc0[14:0], 1'b0};
                if (crc1[15] ^ nibble[1])
                    crc1 = {crc1[14:0], 1'b0} ^ 16'h1021;
                else
                    crc1 = {crc1[14:0], 1'b0};
                if (crc2[15] ^ nibble[2])
                    crc2 = {crc2[14:0], 1'b0} ^ 16'h1021;
                else
                    crc2 = {crc2[14:0], 1'b0};
                if (crc3[15] ^ nibble[3])
                    crc3 = {crc3[14:0], 1'b0} ^ 16'h1021;
                else
                    crc3 = {crc3[14:0], 1'b0};

                @(negedge sd_clk);
                nibble = value[3:0];
                card_dat = nibble;
                @(posedge sd_clk);
                if (crc0[15] ^ nibble[0])
                    crc0 = {crc0[14:0], 1'b0} ^ 16'h1021;
                else
                    crc0 = {crc0[14:0], 1'b0};
                if (crc1[15] ^ nibble[1])
                    crc1 = {crc1[14:0], 1'b0} ^ 16'h1021;
                else
                    crc1 = {crc1[14:0], 1'b0};
                if (crc2[15] ^ nibble[2])
                    crc2 = {crc2[14:0], 1'b0} ^ 16'h1021;
                else
                    crc2 = {crc2[14:0], 1'b0};
                if (crc3[15] ^ nibble[3])
                    crc3 = {crc3[14:0], 1'b0} ^ 16'h1021;
                else
                    crc3 = {crc3[14:0], 1'b0};
            end
            for (bit_number = 15; bit_number >= 0;
                 bit_number = bit_number - 1) begin
                @(negedge sd_clk);
                card_dat = {crc3[bit_number], crc2[bit_number],
                            crc1[bit_number], crc0[bit_number]};
                if (corrupt_crc != 0 && bit_number == 15)
                    card_dat[2] = ~card_dat[2];
                @(posedge sd_clk);
            end
            if (corrupt_crc != 0)
                injected_crc_errors = injected_crc_errors + 1;
            @(negedge sd_clk);
            card_dat = 4'hf;
            @(posedge sd_clk);
            card_data_active = 0;
        end
    endtask

    task drive_multi_read;
        input [31:0] base_lba;
        input integer block_count;
        input integer corrupt_attempt;
        integer block_number;
        begin
            if (corrupt_attempt != 0) begin
                drive_data_block(base_lba, 0);
                drive_data_block(base_lba + 1, 0);
                drive_data_block(base_lba + 2, 1);
            end else begin
                for (block_number = 0; block_number < block_count;
                     block_number = block_number + 1)
                    drive_data_block(base_lba + block_number, 0);
            end
        end
    endtask

    task accept_write_block;
      input integer pattern_lba;
      input integer stream_index;
      integer byte_number,half,lane,bit_number;reg [3:0] nibble;
      reg [15:0] crc [0:3];reg [7:0] value;
      begin
        wait(sd_dat_oe);@(posedge sd_clk);
        if(sd_dat_out!=0)$fatal(1,"driver write start token");
        for(lane=0;lane<4;lane=lane+1)crc[lane]=0;
        for(byte_number=0;byte_number<512;byte_number=byte_number+1)begin
          for(half=0;half<2;half=half+1)begin
            @(posedge sd_clk);nibble=sd_dat_out;
            if(!sd_dat_oe)$fatal(1,"driver DAT released early");
            if(half==0)value[7:4]=nibble;else value[3:0]=nibble;
            for(lane=0;lane<4;lane=lane+1)
              if(crc[lane][15]^nibble[lane])crc[lane]={crc[lane][14:0],1'b0}^16'h1021;
              else crc[lane]={crc[lane][14:0],1'b0};
          end
          if(stream_index<0)written_bytes[byte_number]=value;
          else if(cmd25_count<3)written_multi[stream_index*512+byte_number]=value;
          if(value!==((pattern_lba*17+byte_number*13+8'h5a)&255))$fatal(1,"production driver write byte order/alignment lba=%0d byte=%0d got=%x",pattern_lba,byte_number,value);
        end
        for(bit_number=15;bit_number>=0;bit_number=bit_number-1)begin
          @(posedge sd_clk);
          if(sd_dat_out!={crc[3][bit_number],crc[2][bit_number],crc[1][bit_number],crc[0][bit_number]})$fatal(1,"driver write CRC");
        end
        @(posedge sd_clk);if(sd_dat_out!=15)$fatal(1,"driver write end token");
        wait(!sd_dat_oe);
        for(bit_number=4;bit_number>=0;bit_number=bit_number-1)begin
          @(negedge sd_clk);card_dat={3'b111,((5'b00101>>bit_number)&1'b1)};
          @(posedge sd_clk);
        end
        @(negedge sd_clk);card_dat=4'he;repeat(20)@(posedge sd_clk);
        @(negedge sd_clk);card_dat=4'hf;
      end
    endtask
    task accept_write;
      begin
        drive_r48(6'd24,32'd0);
        accept_write_block(96+cmd24_count-1,-1);
      end
    endtask
    task accept_write_stream;
      integer block_number;
      begin
        drive_r48(6'd25,32'd0);
        block_number=0;
        while(active_write_stream&&block_number<8)begin
          wait(sd_dat_oe||!active_write_stream);
          if(active_write_stream)begin
            accept_write_block(128+(cmd25_count-1)*16+block_number,block_number);
            block_number=block_number+1;
            if(cmd25_count<3)stream_blocks=stream_blocks+1;
            else cancel_blocks=cancel_blocks+1;
          end
        end
      end
    endtask
    task process_command;
        input [47:0] frame;
        reg [6:0] expected_crc;
        reg [5:0] command;
        reg [31:0] argument;
        reg [31:0] lba;
        integer was_app_command;
        begin
            command = frame[45:40];
            argument = frame[39:8];
            calculate_crc7(frame[47:8], expected_crc);
            if (frame[47:46] != 2'b01 || frame[0] != 1'b1 ||
                frame[7:1] != expected_crc)
                command_crc_errors = command_crc_errors + 1;
            was_app_command = app_command;
            app_command = 0;
            $display("SD_NATIVE_CARD_CMD%0d arg=%08x div=%0d bus4=%0d",
                     command, argument, sd_host.divider,
                     sd_host.bus4_latched);
            if (command == 6'd17 && card_data_active != 0) begin
                sequence_errors = sequence_errors + 1;
                $display("SD_NATIVE_RECOVERY_ASSERT_FAIL CMD17 retry before prior data block drained");
            end
            case (command)
                6'd23: begin
                  acmd23_count=acmd23_count+1;
                  if(!was_app_command||argument!=(app_fault_mode?2:8)||!high_capacity_mode||app_fault_mode==1)$fatal(1,"ACMD23 descriptor/APP_CMD gate");
                  // A strictly ILLEGAL_COMMAND hint is optional; the real
                  // driver must still safely write/cancel that third burst.
                  fork drive_r48(6'd23,app_fault_mode==2?32'd0:
                                   acmd23_count==3?32'h00400000:32'h00000020);join_none
                end
                6'd25: begin
                  cmd25_count=cmd25_count+1;
                  if(!high_capacity_mode||argument!=(cmd25_count==3?160:128)||
                     !sd_host.cmd_write_latched||!sd_host.cmd_multi_latched||
                     sd_host.block_count_latched!=8||acmd23_count!=cmd25_count||
                     active_write_stream)$fatal(1,"CMD25 descriptor/uncertain retry");
                  active_boundary_read=0;active_write_stream=1;
                  fork accept_write_stream();join_none
                end
                6'd24: begin
                  cmd24_count=cmd24_count+1;
                  if(!high_capacity_mode||argument!=96||card_data_active||!sd_host.cmd_write_latched)$fatal(1,"CMD24 descriptor");
                  fork accept_write();join_none
                end
                6'd13:begin
                  cmd13_count=cmd13_count+1;
                  if(argument!=32'h12340000||card_dat!=15||sd_dat_oe)$fatal(1,"CMD13 before programming drain");
                  fork drive_r48(6'd13,32'h00000900);join_none
                end
                6'd0: begin
                    cmd0_count = cmd0_count + 1;
                    if (idle_clock_count < 74 || cmd0_count != 1)
                        sequence_errors = sequence_errors + 1;
                    card_ready = 0;
                    card_selected = 0;
                    card_bus4 = 0;
                    app_command = 0;
                end
                6'd8: begin
                    cmd8_count = cmd8_count + 1;
                    if (cmd0_count != 1 || argument != 32'h0000_01aa ||
                        sd_host.divider != 16'd62)
                        sequence_errors = sequence_errors + 1;
                    fork
                        drive_r48(6'd8,
                                  high_capacity_mode != 0 ?
                                  32'h0000_01aa : 32'h0040_0000);
                    join_none
                end
                6'd55: begin
                    cmd55_count = cmd55_count + 1;
                    if ((!card_ready && argument != 32'd0) ||
                        (card_ready && argument != 32'h1234_0000))
                        sequence_errors = sequence_errors + 1;
                    app_command = 1;
                    fork
                        drive_r48(6'd55,(app_fault_mode==1&&cmd55_count==6)?32'd0:32'h00000020);
                    join_none
                end
                6'd41: begin
                    acmd41_count = acmd41_count + 1;
                    if (was_app_command == 0 ||
                        argument != (high_capacity_mode != 0 ?
                                     32'h40ff_8000 : 32'h00ff_8000) ||
                        card_ready != 0 || acmd41_count > 2)
                        sequence_errors = sequence_errors + 1;
                    if (acmd41_count == 2)
                        card_ready = 1;
                    fork
                        drive_r48(6'h3f,
                                  acmd41_count == 2 ?
                                  (high_capacity_mode != 0 ?
                                   32'hc0ff_8000 : 32'h80ff_8000) :
                                  32'h00ff_8000);
                    join_none
                end
                6'd2: begin
                    cmd2_count = cmd2_count + 1;
                    if (!card_ready || acmd41_count != 2)
                        sequence_errors = sequence_errors + 1;
                    fork
                        drive_r136(120'h0123_4567_89ab_cdef_1020_3040_5060_70);
                    join_none
                end
                6'd3: begin
                    cmd3_count = cmd3_count + 1;
                    if (cmd2_count != 1 || argument != 0)
                        sequence_errors = sequence_errors + 1;
                    fork
                        drive_r48(6'd3, 32'h1234_0000);
                    join_none
                end
                6'd9: begin
                    cmd9_count = cmd9_count + 1;
                    if (cmd3_count != 1 || argument != 32'h1234_0000)
                        sequence_errors = sequence_errors + 1;
                    fork
                        drive_csd();
                    join_none
                end
                6'd7: begin
                    cmd7_count = cmd7_count + 1;
                    if (cmd9_count != 1 || argument != 32'h1234_0000)
                        sequence_errors = sequence_errors + 1;
                    card_selected = 1;
                    fork
                        drive_r48_busy(6'd7, 32'd0);
                    join_none
                end
                6'd16: begin
                    cmd16_count = cmd16_count + 1;
                    if (high_capacity_mode != 0 || !card_selected ||
                        argument != 512)
                        sequence_errors = sequence_errors + 1;
                    fork
                        drive_r48(6'd16, 32'd0);
                    join_none
                end
                6'd51: begin
                    acmd51_count = acmd51_count + 1;
                    if (was_app_command == 0 || !card_selected ||
                        argument != 0 || card_bus4 != 0 ||
                        sd_host.bus4_latched != 0 ||
                        sd_host.block_size_latched != 8 ||
                        sd_host.block_count_latched != 1 ||
                        sd_host.divider != 16'd62)
                        sequence_errors = sequence_errors + 1;
                    fork
                        drive_r48(6'd51, 32'd0);
                        begin
                            wait (sd_cmd_oe === 1'b1);
                            wait (sd_cmd_oe === 1'b0);
                            repeat (25) @(posedge sd_clk);
                            drive_scr();
                        end
                    join_none
                end
                6'd42: begin
                    acmd42_count = acmd42_count + 1;
                    if (was_app_command == 0 || !card_selected || argument != 0)
                        sequence_errors = sequence_errors + 1;
                    fork
                        drive_r48(6'd42, 32'd0);
                    join_none
                end
                6'd6: begin
                    acmd6_count = acmd6_count + 1;
                    if (was_app_command == 0 || !card_selected || argument != 2)
                        sequence_errors = sequence_errors + 1;
                    card_bus4 = 1;
                    fork
                        drive_r48(6'd6, 32'd0);
                    join_none
                end
                6'd17: begin
                    cmd17_count = cmd17_count + 1;
                    if (!card_selected || !card_bus4 ||
                        sd_host.bus4_latched != 1 ||
                        sd_host.block_size_latched != 512 ||
                        sd_host.block_count_latched != 1 ||
                        sd_host.divider != 0)
                        sequence_errors = sequence_errors + 1;
                    if (high_capacity_mode != 0)
                        lba = argument;
                    else begin
                        if (argument[8:0] != 0)
                            sequence_errors = sequence_errors + 1;
                        lba = argument >> 9;
                    end
                    if (lba == 7) begin
                        cmd17_data_crc_attempts =
                            cmd17_data_crc_attempts + 1;
                        if (cmd17_data_crc_attempts == 1) begin
                            awaiting_cmd17_data_retry = 1;
                            fork
                                begin
                                    drive_r48(6'd17, 32'd0);
                                    drive_data_block(lba, 1);
                                end
                            join_none
                        end else if (cmd17_data_crc_attempts == 2) begin
                            awaiting_cmd17_data_retry = 0;
                            fork
                                begin
                                    drive_r48(6'd17, 32'd0);
                                    drive_data_block(lba, 0);
                                end
                            join_none
                        end else begin
                            sequence_errors = sequence_errors + 1;
                            fork
                                begin
                                    drive_r48(6'd17, 32'd0);
                                    drive_data_block(lba, 0);
                                end
                            join_none
                        end
                    end else if (lba == 8) begin
                        cmd17_response_crc_attempts =
                            cmd17_response_crc_attempts + 1;
                        if (cmd17_response_crc_attempts == 1) begin
                            awaiting_cmd17_response_retry = 1;
                            fork
                                drive_r48_corrupt_crc(6'd17, 32'd0);
                                begin
                                    /* A card may already be transmitting DAT
                                     * while the host detects bad R1 CRC.  The
                                     * host must drain this single block before
                                     * retrying CMD17. */
                                    wait (sd_cmd_oe === 1'b1);
                                    wait (sd_cmd_oe === 1'b0);
                                    repeat (25) @(posedge sd_clk);
                                    drive_data_block(lba, 0);
                                end
                            join_none
                        end else if (cmd17_response_crc_attempts == 2) begin
                            awaiting_cmd17_response_retry = 0;
                            fork
                                drive_r48(6'd17, 32'd0);
                                begin
                                    wait (sd_cmd_oe === 1'b1);
                                    wait (sd_cmd_oe === 1'b0);
                                    repeat (25) @(posedge sd_clk);
                                    drive_data_block(lba, 0);
                                end
                            join_none
                        end else begin
                            sequence_errors = sequence_errors + 1;
                            fork
                                begin
                                    drive_r48(6'd17, 32'd0);
                                    drive_data_block(lba, 0);
                                end
                            join_none
                        end
                    end else if(lba==96&&cmd24_count>=1&&cmd24_count<=5)begin
                        fork begin drive_r48(6'd17,32'd0);drive_data_block(lba,0);end join_none
                    end else begin
                        sequence_errors = sequence_errors + 1;
                        fork
                            begin
                                drive_r48(6'd17, 32'd0);
                                drive_data_block(lba, 0);
                            end
                        join_none
                    end
                end
                6'd18: begin
                    cmd18_count = cmd18_count + 1;
                    if (!card_selected || !card_bus4 ||
                        sd_host.bus4_latched != 1 ||
                        sd_host.block_size_latched != 512 ||
                        sd_host.divider != 0)
                        sequence_errors = sequence_errors + 1;
                    if (high_capacity_mode != 0)
                        lba = argument;
                    else begin
                        if (argument[8:0] != 0)
                            sequence_errors = sequence_errors + 1;
                        lba = argument >> 9;
                    end
                    if(lba==128&&cmd25_count>=1&&cmd25_count<=2)begin
                        active_boundary_read=0;
                        if(sd_host.block_count_latched!=8)$fatal(1,"CMD25 independent read size");
                        fork begin drive_r48(6'd18,32'd0);drive_multi_read(lba,8,0);end join_none
                    end else if (lba == 64) begin
                        active_boundary_read = 0;
                        batch_cmd18_attempts = batch_cmd18_attempts + 1;
                        if (sd_host.block_count_latched != 32 ||
                            batch_cmd18_attempts > 2)
                            sequence_errors = sequence_errors + 1;
                        fork
                            begin
                                drive_r48(6'd18, 32'd0);
                                drive_multi_read(lba,
                                                 sd_host.block_count_latched,
                                                 batch_cmd18_attempts == 1);
                            end
                        join_none
                    end else if (lba == 1048574) begin
                        active_boundary_read = 1;
                        boundary_cmd18_attempts =
                            boundary_cmd18_attempts + 1;
                        if (sd_host.block_count_latched != 2 ||
                            boundary_cmd18_attempts > 2)
                            sequence_errors = sequence_errors + 1;
                        if (boundary_cmd18_attempts == 2) begin
                            if (awaiting_boundary_cmd18_retry == 0)
                                sequence_errors = sequence_errors + 1;
                            awaiting_boundary_cmd18_retry = 0;
                        end
                        fork
                            begin
                                drive_r48(6'd18, 32'd0);
                                drive_multi_read(lba,
                                                 sd_host.block_count_latched,
                                                 0);
                            end
                        join_none
                    end else begin
                        sequence_errors = sequence_errors + 1;
                        fork
                            drive_r48(6'd18, 32'd0);
                        join_none
                    end
                end
                6'd12: begin
                    cmd12_count = cmd12_count + 1;
                    if (argument != 0 || !card_bus4)
                        sequence_errors = sequence_errors + 1;
                    if(active_write_stream)begin
                        active_write_stream=0;
                        auto_cmd12_count=auto_cmd12_count+1;
                        if(sd_host.cmd_resp_latched!=4||sd_dat_oe||card_dat!=15)$fatal(1,"CMD25 stop before programming drain");
                        fork drive_r48_busy(6'd12,32'h00000900);join_none
                    end else if (sd_host.auto_stop_active != 0) begin
                        auto_cmd12_count = auto_cmd12_count + 1;
                        if (active_boundary_read != 0 &&
                            boundary_cmd18_attempts == 1) begin
                            awaiting_boundary_cmd18_retry = 1;
                            fork
                                drive_r48_corrupt_crc(6'd12,
                                                      32'h8000_0000);
                            join_none
                        end else if (active_boundary_read != 0 &&
                                     boundary_cmd18_attempts == 2) begin
                            boundary_out_of_range_count =
                                boundary_out_of_range_count + 1;
                            fork
                                drive_r48_busy(6'd12, 32'h8000_0000);
                            join_none
                        end else begin
                            fork
                                drive_r48_busy(6'd12, 32'd0);
                            join_none
                        end
                    end else begin
                        manual_cmd12_count = manual_cmd12_count + 1;
                        if (awaiting_cmd17_data_retry != 0) begin
                            cmd17_data_crc_cmd12_errors =
                                cmd17_data_crc_cmd12_errors + 1;
                            $display("SD_NATIVE_RECOVERY_ASSERT_FAIL CMD12 between CMD17 data-CRC attempt and retry");
                        end
                        if (awaiting_cmd17_response_retry != 0) begin
                            cmd17_response_crc_cmd12_errors =
                                cmd17_response_crc_cmd12_errors + 1;
                            $display("SD_NATIVE_RECOVERY_ASSERT_FAIL CMD12 between CMD17 response-CRC attempt and retry");
                        end
                        if (awaiting_boundary_cmd18_retry != 0) begin
                            auto_cmd12_duplicate_errors =
                                auto_cmd12_duplicate_errors + 1;
                            $display("SD_NATIVE_RECOVERY_ASSERT_FAIL duplicate CMD12 after automatic CMD12 response-CRC failure");
                        end
                        fork
                            drive_r48_busy(6'd12, 32'd0);
                        join_none
                    end
                end
                default: begin
                    sequence_errors = sequence_errors + 1;
                    fork
                        drive_r48(command, 32'h0040_0000);
                    join_none
                end
            endcase
        end
    endtask

    always @(posedge sd_clk) begin
        reg [47:0] next_command;
        if (!sd_cmd_oe && cmd0_count == 0)
            idle_clock_count = idle_clock_count + 1;
        if (sd_cmd_oe) begin
            next_command = {received_command[46:0], sd_cmd_out};
            received_command = next_command;
            if (received_command_bits == 47) begin
                received_command_bits = 0;
                process_command(next_command);
            end else begin
                received_command_bits = received_command_bits + 1;
            end
        end else begin
            received_command_bits = 0;
        end
    end

    integer max_cycles;
    initial begin
        high_capacity_mode = 1;
        app_fault_mode=0;
        if($test$plusargs("missing_cmd55_app"))app_fault_mode=1;
        if($test$plusargs("missing_acmd23_app"))app_fault_mode=2;
        if ($test$plusargs("sdsc"))
            high_capacity_mode = 0;
        idle_clock_count = 0;
        sequence_errors = 0;
        command_crc_errors = 0;
        card_ready = 0;
        card_selected = 0;
        card_bus4 = 0;
        app_command = 0;
        cmd0_count = 0;
        cmd8_count = 0;
        cmd55_count = 0;
        acmd41_count = 0;
        cmd2_count = 0;
        cmd3_count = 0;
        cmd9_count = 0;
        cmd7_count = 0;
        cmd16_count = 0;
        acmd51_count = 0;
        acmd42_count = 0;
        acmd6_count = 0;
        cmd17_count = 0;
        cmd24_count = 0;cmd13_count=0;
        cmd25_count=0;acmd23_count=0;stream_blocks=0;cancel_blocks=0;active_write_stream=0;
        cmd18_count = 0;
        cmd12_count = 0;
        manual_cmd12_count = 0;
        auto_cmd12_count = 0;
        boundary_out_of_range_count = 0;
        injected_crc_errors = 0;
        cmd17_data_crc_attempts = 0;
        awaiting_cmd17_data_retry = 0;
        cmd17_data_crc_cmd12_errors = 0;
        cmd17_response_crc_attempts = 0;
        awaiting_cmd17_response_retry = 0;
        cmd17_response_crc_cmd12_errors = 0;
        batch_cmd18_attempts = 0;
        boundary_cmd18_attempts = 0;
        active_boundary_read = 0;
        awaiting_boundary_cmd18_retry = 0;
        auto_cmd12_duplicate_errors = 0;
        injected_response_crc_errors = 0;
        card_data_active = 0;
        received_command = 48'd0;
        received_command_bits = 0;
        if (!$value$plusargs("max_cycles=%d", max_cycles))
            max_cycles = 10000000;
        repeat (20) @(posedge clk);
        resetn <= 1'b1;
        repeat (max_cycles) @(posedge clk);
        $display("SD_NATIVE_DRIVER_TIMEOUT mode=%0d state=%0d busy=%b error=%02x",
                 high_capacity_mode, sd_host.state, sd_host.busy,
                 sd_host.error_sticky);
        $display("command_bits=%0d cmd18=%0d cmd12=%0d buffers=%b%b blocks=%0d",
                 received_command_bits, cmd18_count, cmd12_count,
                 sd_host.buffer1_ready, sd_host.buffer0_ready,
                 sd_host.blocks_done);
        $display("CPU pc=%h fatal=%b mcause=%h mepc=%h AR=%h/%b/%b saved=%h R=%b/%b pending=%b AW=%h/%b/%b W=%b/%b B=%b/%b",
                 cpu.u_cpu.core.frontend.pfPc[31:0], cpu.fatal_memory_error,
                 cpu.u_cpu.core.backend.u_csr_trap.mcause,
                 cpu.u_cpu.core.backend.u_csr_trap.mepc,
                 araddr, arvalid, arready, saved_araddr, rvalid, rready, read_pending,
                 awaddr, awvalid, awready, wvalid, wready, bvalid, bready);
        $display("ROB head0=%08x/%b/%b head1=%08x/%b/%b SB count=%0d inflight=%b drain=%b addr=%08x DC state=%0d AXI ic=%0d dc=%0d wr=%0d",
                 cpu.u_cpu.core.backend.u_commit.io_c_0_pc,
                 cpu.u_cpu.core.backend.u_commit.io_c_0_valid,
                 cpu.u_cpu.core.backend.u_commit.io_c_0_complete,
                 cpu.u_cpu.core.backend.u_commit.io_c_1_pc,
                 cpu.u_cpu.core.backend.u_commit.io_c_1_valid,
                 cpu.u_cpu.core.backend.u_commit.io_c_1_complete,
                 cpu.u_cpu.core.memory.u_store_buffer.count,
                 cpu.u_cpu.core.memory.u_store_buffer.inflight,
                 cpu.u_cpu.core.memory.u_store_buffer.drainValid,
                 cpu.u_cpu.core.memory.u_store_buffer.drainPaddr,
                 cpu.u_cpu.core.memory.u_dcache.state,
                 cpu.u_cpu.core.memory.u_axi_line_bridge.icState,
                 cpu.u_cpu.core.memory.u_axi_line_bridge.dcState,
                 cpu.u_cpu.core.memory.u_axi_line_bridge.wrState);
        $display("LSU a=%b/%0d/%08x d=%b/%0d/%08x uncached=%b dcReq=%b dcAddrOk=%b tokens=%b misses=%b",
                 cpu.u_cpu.core.memory.u_lsu.aValid,
                 cpu.u_cpu.core.memory.u_lsu.aRobid,
                 cpu.u_cpu.core.memory.u_lsu.io_pmaDVaddr,
                 cpu.u_cpu.core.memory.u_lsu.dValid,
                 cpu.u_cpu.core.memory.u_lsu.dRobid,
                 cpu.u_cpu.core.memory.u_lsu.dPaddr,
                 cpu.u_cpu.core.memory.u_lsu.io_uncachedLdInflight,
                 cpu.u_cpu.core.memory.u_lsu.io_dcReq,
                 cpu.u_cpu.core.memory.u_lsu.io_dcAddrOk,
                 cpu.u_cpu.core.memory.u_lsu.io_pendingLoadValid,
                 cpu.u_cpu.core.memory.u_lsu.io_missWaitValid);
        $display("LSU head=%0d/%b aGo=%b aBaseReady=%b dAtHead=%b dYield=%b u=%b/%0d/%08x q=%b/%0d/%08x RS count=%0d issue=%b/%0d",
                 cpu.u_cpu.core.memory.u_lsu.io_robHeadRobid,
                 cpu.u_cpu.core.memory.u_lsu.io_robHeadValid,
                 cpu.u_cpu.core.memory.u_lsu.aGo,
                 cpu.u_cpu.core.memory.u_lsu.aBaseReady,
                 cpu.u_cpu.core.memory.u_lsu.dAtHead,
                 cpu.u_cpu.core.memory.u_lsu.dUcYield,
                 cpu.u_cpu.core.memory.u_lsu.uValid,
                 cpu.u_cpu.core.memory.u_lsu.uRobid,
                 cpu.u_cpu.core.memory.u_lsu.uPaddr,
                 cpu.u_cpu.core.memory.u_lsu.qValid,
                 cpu.u_cpu.core.memory.u_lsu.qRobid,
                 cpu.u_cpu.core.memory.u_lsu.qBase,
                 cpu.u_cpu.core.backend.u_rs_mem.count,
                 cpu.u_cpu.core.backend.u_rs_mem.io_issueValid,
                 cpu.u_cpu.core.backend.u_rs_mem.io_issueRobid);
        for (retire_dump = 0; retire_dump < 32; retire_dump = retire_dump + 1)
            $display("last_retire[%0d]=%08x", retire_dump,
                     retire_window[(retire_count + retire_dump) % 32]);
        $fatal(1);
    end

    wire unused = &{1'b0, arburst, arlock, arcache, arprot,
                    awlen, awsize, awburst, awlock, awcache, awprot,
                    wid, wlast, sd_hit};
endmodule
