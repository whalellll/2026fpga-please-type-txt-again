`timescale 1ns/1ps

module tb_sd_native_mmio;
    localparam [31:0] BASE = 32'h1fe1_3000;

    reg         clk = 1'b0;
    reg         resetn = 1'b0;
    reg  [31:0] addr = 32'd0;
    reg         wr = 1'b0;
    reg  [31:0] wdata = 32'd0;
    reg  [3:0]  wstrb = 4'd0;
    wire [31:0] rdata;
    wire        hit;
    wire        sd_clk;
    reg         card_cmd = 1'b1;
    wire        sd_cmd_out;
    wire        sd_cmd_oe;
    reg  [3:0]  card_dat = 4'hf;
    reg         sd_detect_n = 1'b0;

    reg [47:0] host_command;
    integer host_command_bits;
    integer sd_rising_edges;

    reg [47:0] response_frame;
    reg [47:0] stop_response_frame;
    reg [135:0] response136_frame;
    reg [127:0] response136_raw;
    reg [63:0] data_pattern;
    reg [6:0]  ram_write_addr = 7'd0;
    reg [31:0] ram_write_data = 32'd0;
    reg [3:0]  ram_write_strobe = 4'd0;
    reg [6:0]  ram_cpu_addr = 7'd0;
    reg [6:0]  ram_tx_addr = 7'd0;
    wire [31:0] ram_cpu_data;
    wire [31:0] ram_tx_data;
    integer short_length;

    always #5 clk = ~clk;

    sd_native_mmio #(
        .BASE(BASE),
        .RESET_DIV(16'd0),
        .DEBOUNCE_CYCLES(2),
        .CMD_TIMEOUT_CLOCKS(64),
        .DATA_TIMEOUT_CLOCKS(256),
        .BUSY_TIMEOUT_CLOCKS(64)
    ) dut (
        .clk(clk),
        .resetn(resetn),
        .addr(addr),
        .wr(wr),
        .wdata(wdata),
        .wstrb(wstrb),
        .rdata(rdata),
        .hit(hit),
        .sd_clk(sd_clk),
        .sd_cmd_in(card_cmd),
        .sd_cmd_out(sd_cmd_out),
        .sd_cmd_oe(sd_cmd_oe),
        .sd_dat_in(card_dat),
        .sd_detect_n(sd_detect_n)
    );

    // Exercise both physical read mirrors independently of SD transaction
    // timing. Each RAM word has four independently enabled byte lanes.
    sd_native_sector_bank u_sector_ram (
        .clk(clk), .write_addr(ram_write_addr),
        .write_data(ram_write_data), .write_strobe(ram_write_strobe),
        .cpu_read_addr(ram_cpu_addr), .tx_read_addr(ram_tx_addr),
        .cpu_read_data(ram_cpu_data), .tx_read_data(ram_tx_data)
    );

    task ram_write_word;
        input [6:0] word_addr;
        input [31:0] word_data;
        input [3:0] byte_strobe;
        begin
            @(negedge clk);
            ram_write_addr = word_addr;
            ram_write_data = word_data;
            ram_write_strobe = byte_strobe;
            @(posedge clk);
            #1;
            ram_write_strobe = 4'd0;
        end
    endtask

    task ram_check_views;
        input [6:0] cpu_word_addr;
        input [6:0] tx_word_addr;
        input [31:0] expected_cpu;
        input [31:0] expected_tx;
        begin
            @(negedge clk);
            ram_cpu_addr = cpu_word_addr;
            ram_tx_addr = tx_word_addr;
            #1;
            if (ram_cpu_data !== expected_cpu ||
                ram_tx_data !== expected_tx)
                $fatal(1, "sector RAM mirror mismatch CPU[%0d]=%h TX[%0d]=%h",
                       cpu_word_addr, ram_cpu_data, tx_word_addr,
                       ram_tx_data);
        end
    endtask

    task check_reset_rx_collision;
        input [31:0] control_word;
        input [31:0] protected_word;
        begin
            mmio_write(BASE + 32'h100, protected_word, 4'hf);
            // Put the receive engine at its final nibble. Its other write
            // qualifications are true on the same edge as a software reset
            // or abort. Neither control pulse may commit this synthetic byte.
            @(negedge clk);
            dut.data_state = 3'd2;
            dut.data_byte_count = 10'd0;
            dut.data_nibble_phase = 1'b1;
            dut.data_byte_shift = 8'ha0;
            dut.data_buffer_select = 1'b0;
            dut.bus4_latched = 1'b1;
            dut.divider_count = dut.divider;
            card_dat = 4'h5;
            addr = BASE + 32'h008;
            wdata = control_word;
            wstrb = 4'h1;
            wr = 1'b1;
            #1;
            if (!dut.clock_should_run || sd_clk ||
                dut.data_state !== 3'd2 ||
                dut.rx_byte_write !== 1'b0 ||
                dut.buffer0_write_strobe !== 4'd0)
                $fatal(1, "RX/control collision was not suppressed");
            @(posedge clk);
            #1;
            @(negedge clk);
            wr = 1'b0;
            wstrb = 4'd0;
            card_dat = 4'hf;
            select_addr(BASE + 32'h100);
            if (rdata !== protected_word ||
                dut.buffer0_tx_word !== protected_word)
                $fatal(1, "RX/control collision changed CPU or TX mirror");
        end
    endtask

    always @(posedge sd_clk) begin
        sd_rising_edges = sd_rising_edges + 1;
        if (sd_cmd_oe) begin
            host_command = {host_command[46:0], sd_cmd_out};
            host_command_bits = host_command_bits + 1;
        end
    end

    task mmio_write;
        input [31:0] write_addr;
        input [31:0] write_data;
        input [3:0] write_strobe;
        begin
            @(negedge clk);
            addr = write_addr;
            wdata = write_data;
            wstrb = write_strobe;
            wr = 1'b1;
            @(posedge clk);
            #1;
            @(negedge clk);
            wr = 1'b0;
            wstrb = 4'd0;
            wdata = 32'd0;
        end
    endtask

    task select_addr;
        input [31:0] read_addr;
        begin
            @(negedge clk);
            addr = read_addr;
            #1;
        end
    endtask

    task wait_done;
        integer guard;
        begin
            guard = 0;
            while ((dut.busy !== 1'b0) && (guard < 20000)) begin
                @(posedge clk);
                guard = guard + 1;
            end
            if (guard >= 20000)
                $fatal(1, "operation did not finish");
            if (dut.done !== 1'b1)
                $fatal(1, "DONE was not set");
        end
    endtask

    task build_r48;
        input [5:0] response_index;
        input [31:0] response_payload;
        output [47:0] frame;
        reg [39:0] protected_bits;
        reg [6:0] crc;
        integer bit_number;
        begin
            protected_bits = {2'b00, response_index, response_payload};
            crc = 7'd0;
            for (bit_number = 39; bit_number >= 0;
                 bit_number = bit_number - 1) begin
                if (crc[6] ^ protected_bits[bit_number])
                    crc = {crc[5:0], 1'b0} ^ 7'h09;
                else
                    crc = {crc[5:0], 1'b0};
            end
            frame = {protected_bits, crc, 1'b1};
        end
    endtask

    task send_r48;
        input [47:0] frame;
        integer bit_number;
        begin
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

    task send_r136;
        input [135:0] frame;
        integer bit_number;
        begin
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

    task send_data_1bit;
        input [63:0] payload;
        reg [15:0] crc;
        integer bit_number;
        begin
            card_dat = 4'b1110;
            @(posedge sd_clk);
            crc = 16'd0;
            for (bit_number = 63; bit_number >= 0;
                 bit_number = bit_number - 1) begin
                @(negedge sd_clk);
                card_dat[0] = payload[bit_number];
                @(posedge sd_clk);
                if (crc[15] ^ payload[bit_number])
                    crc = {crc[14:0], 1'b0} ^ 16'h1021;
                else
                    crc = {crc[14:0], 1'b0};
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

    task send_scr_overlap_fixed;
        integer bit_number;
        reg [63:0] payload;
        reg [15:0] crc;
        begin
            /* Independent board-captured vector.  Keep the CRC literal so
             * this regression cannot agree with a broken host CRC equation. */
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

    task send_data_4bit;
        input [63:0] payload;
        input corrupt_crc;
        input integer byte_count;
        reg [15:0] crc0;
        reg [15:0] crc1;
        reg [15:0] crc2;
        reg [15:0] crc3;
        reg [3:0] nibble;
        integer nibble_number;
        integer bit_number;
        begin
            card_dat = 4'b0000;
            @(posedge sd_clk);
            crc0 = 16'd0;
            crc1 = 16'd0;
            crc2 = 16'd0;
            crc3 = 16'd0;
            for (nibble_number = byte_count * 2 - 1; nibble_number >= 0;
                 nibble_number = nibble_number - 1) begin
                @(negedge sd_clk);
                nibble = payload[nibble_number * 4 +: 4];
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
                if (corrupt_crc && (bit_number == 15))
                    card_dat[0] = ~card_dat[0];
                @(posedge sd_clk);
            end
            @(negedge sd_clk);
            card_dat = 4'hf;
            @(posedge sd_clk);
        end
    endtask

    initial begin
        host_command = 48'd0;
        host_command_bits = 0;
        sd_rising_edges = 0;
        data_pattern = 64'h0102_0304_0506_0708;

        repeat (4) @(posedge clk);
        #1;
        if (sd_clk !== 1'b0 || sd_cmd_oe !== 1'b0 ||
            sd_cmd_out !== 1'b1)
            $fatal(1, "native SD reset pins mismatch");

        resetn = 1'b1;
        repeat (6) @(posedge clk);

        // Boundary word indices 0, 1 and 127 exercise every byte lane and
        // simultaneous, independently addressed CPU/TX mirror reads.
        ram_write_word(7'd0,   32'h4433_2211, 4'hf);
        ram_write_word(7'd1,   32'h8877_6655, 4'hf);
        ram_write_word(7'd127, 32'h0f1e_2d3c, 4'hf);
        ram_write_word(7'd0,   32'haabb_ccdd, 4'b1010);
        ram_write_word(7'd1,   32'h1234_5678, 4'b0101);
        ram_write_word(7'd127, 32'hfedc_ba98, 4'b1001);
        ram_check_views(7'd0, 7'd127, 32'haa33_cc11,
                        32'hfe1e_2d98);
        ram_check_views(7'd127, 7'd1, 32'hfe1e_2d98,
                        32'h8834_6678);
        ram_check_views(7'd1, 7'd0, 32'h8834_6678,
                        32'haa33_cc11);
        // During a same-address write the read ports are steered to an
        // already initialized neighbor; after the edge both mirrors expose
        // the newly committed word, with no split-byte view.
        @(negedge clk);
        ram_cpu_addr = 7'd0;
        ram_tx_addr = 7'd0;
        ram_write_addr = 7'd0;
        ram_write_data = 32'h9988_7766;
        ram_write_strobe = 4'hf;
        #1;
        if (ram_cpu_data !== 32'h8834_6678 ||
            ram_tx_data !== 32'h8834_6678)
            $fatal(1, "same-address RAM read was not isolated");
        @(posedge clk);
        #1;
        ram_write_strobe = 4'd0;
        ram_check_views(7'd0, 7'd0, 32'h9988_7766,
                        32'h9988_7766);

        select_addr(BASE + 32'h000);
        if (!hit || rdata !== 32'h5344_4e32)
            $fatal(1, "ID mismatch: %h", rdata);
        select_addr(BASE + 32'h004);
        if (rdata !== 32'h0005_0401)
            $fatal(1, "version mismatch: %h", rdata);
        select_addr(BASE + 32'h00c);
        if (rdata[4:3] !== 2'b11)
            $fatal(1, "card detect mismatch: %h", rdata);
        select_addr(BASE + 32'h500);
        if (hit || rdata !== 32'd0)
            $fatal(1, "MMIO end decode mismatch");

        // The CPU MMIO view uses the same byte strobes and maps its last
        // sector word to +0x2fc / +0x4fc, one word before the bank boundary.
        mmio_write(BASE + 32'h100, 32'h4433_2211, 4'hf);
        mmio_write(BASE + 32'h100, 32'haabb_ccdd, 4'b1010);
        mmio_write(BASE + 32'h104, 32'h8877_6655, 4'hf);
        mmio_write(BASE + 32'h104, 32'h1234_5678, 4'b0101);
        mmio_write(BASE + 32'h2fc, 32'h0f1e_2d3c, 4'hf);
        mmio_write(BASE + 32'h2fc, 32'hfedc_ba98, 4'b1001);
        mmio_write(BASE + 32'h4fc, 32'h5a4b_3c2d, 4'hf);
        select_addr(BASE + 32'h100);
        if (rdata !== 32'haa33_cc11) $fatal(1, "bank0 word0 byte lanes");
        select_addr(BASE + 32'h104);
        if (rdata !== 32'h8834_6678) $fatal(1, "bank0 word1 byte lanes");
        select_addr(BASE + 32'h2fc);
        if (rdata !== 32'hfe1e_2d98) $fatal(1, "bank0 word127 byte lanes");
        select_addr(BASE + 32'h4fc);
        if (rdata !== 32'h5a4b_3c2d) $fatal(1, "bank1 word127 boundary");

        // Clock-only operation generates exactly the requested rising edges.
        sd_rising_edges = 0;
        mmio_write(BASE + 32'h048, 32'd5, 4'hf);
        wait_done();
        if (sd_rising_edges != 5 || sd_clk !== 1'b0)
            $fatal(1, "idle clocks mismatch: %0d", sd_rising_edges);

        // CMD0 has a normative CRC vector: 0x400000000095.
        mmio_write(BASE + 32'h008, 32'h0000_0004, 4'h1);
        host_command = 48'd0;
        host_command_bits = 0;
        mmio_write(BASE + 32'h014, 32'd0, 4'hf);
        mmio_write(BASE + 32'h018, 32'h0000_0800, 4'hf);
        wait_done();
        if (host_command_bits != 48 ||
            host_command !== 48'h4000_0000_0095)
            $fatal(1, "CMD0 frame mismatch: bits=%0d frame=%h",
                   host_command_bits, host_command);
        if (dut.error_sticky !== 8'd0)
            $fatal(1, "CMD0 reported error %h", dut.error_sticky);

        // Capture a complete CRC-protected R7 response as a raw 48-bit frame.
        mmio_write(BASE + 32'h008, 32'h0000_0004, 4'h1);
        build_r48(6'd8, 32'h0000_01aa, response_frame);
        host_command = 48'd0;
        host_command_bits = 0;
        fork
            send_r48(response_frame);
            begin
                mmio_write(BASE + 32'h014, 32'h0000_01aa, 4'hf);
                mmio_write(BASE + 32'h018,
                           32'h0000_0800 | (32'd1 << 6) | 32'd8,
                           4'hf);
            end
        join
        wait_done();
        select_addr(BASE + 32'h01c);
        if (rdata !== response_frame[31:0])
            $fatal(1, "R48 RESP0 mismatch: %h", rdata);
        select_addr(BASE + 32'h020);
        if (rdata[15:0] !== response_frame[47:32])
            $fatal(1, "R48 RESP1 mismatch: %h", rdata);
        if (dut.error_sticky !== 8'd0)
            $fatal(1, "valid R48 reported error %h", dut.error_sticky);

        // Initialization data path: an eight-byte SCR arrives on DAT0 only.
        mmio_write(BASE + 32'h008, 32'h0000_0004, 4'h1);
        mmio_write(BASE + 32'h030, 32'd8, 4'hf);
        mmio_write(BASE + 32'h034, 32'd1, 4'hf);
        build_r48(6'd51, 32'd0, response_frame);
        fork
            send_r48(response_frame);
            begin
                /* A native-SD read data token may overlap the R1 response.
                 * Start early enough that the first 22 payload bits arrive
                 * before the host has sampled the R1 end bit. */
                wait (sd_cmd_oe === 1'b1);
                wait (sd_cmd_oe === 1'b0);
                repeat (25) @(posedge sd_clk);
                send_scr_overlap_fixed();
            end
            begin
                mmio_write(BASE + 32'h014, 32'd0, 4'hf);
                mmio_write(BASE + 32'h018,
                           32'h0000_0800 | 32'h0000_0200 |
                           (32'd1 << 6) | 32'd51,
                           4'hf);
            end
        join
        wait_done();
        select_addr(BASE + 32'h03c);
        if (rdata[1:0] !== 2'b01)
            $fatal(1, "1-bit buffer ready mismatch: %h", rdata);
        select_addr(BASE + 32'h100);
        if (rdata !== 32'h0380_3502)
            $fatal(1, "1-bit buffer word0 mismatch: %h", rdata);
        select_addr(BASE + 32'h104);
        if (rdata !== 32'h0000_0000)
            $fatal(1, "1-bit buffer word1 mismatch: %h", rdata);
        if (dut.error_sticky !== 8'd0)
            $fatal(1, "1-bit read reported error %h", dut.error_sticky);

        // Release buffer 0, switch width, and repeat over all four DAT lanes.
        mmio_write(BASE + 32'h03c, 32'h0000_0001, 4'h1);
        mmio_write(BASE + 32'h008, 32'h0000_0006, 4'h1);
        build_r48(6'd17, 32'd0, response_frame);
        fork
            begin
                send_r48(response_frame);
                send_data_4bit(data_pattern, 1'b0, 8);
            end
            begin
                mmio_write(BASE + 32'h014, 32'd0, 4'hf);
                mmio_write(BASE + 32'h018,
                           32'h0000_0800 | 32'h0000_0200 |
                           (32'd1 << 6) | 32'd17,
                           4'hf);
            end
        join
        wait_done();
        select_addr(BASE + 32'h03c);
        if (rdata[1:0] !== 2'b01)
            $fatal(1, "4-bit buffer ready mismatch: %h", rdata);
        select_addr(BASE + 32'h100);
        if (rdata !== 32'h0403_0201)
            $fatal(1, "4-bit buffer word0 mismatch: %h", rdata);
        select_addr(BASE + 32'h104);
        if (rdata !== 32'h0807_0605)
            $fatal(1, "4-bit buffer word1 mismatch: %h", rdata);
        if (dut.error_sticky !== 8'd0)
            $fatal(1, "4-bit read reported error %h", dut.error_sticky);

        // A short transfer must replace the entire destination word after
        // each completed byte. Lengths 5..7 also cross into the next word,
        // where stale high bytes from the previous eight-byte read exist.
        for (short_length = 1; short_length <= 7;
             short_length = short_length + 1) begin
            mmio_write(BASE + 32'h03c, 32'h0000_0001, 4'h1);
            mmio_write(BASE + 32'h008, 32'h0000_0006, 4'h1);
            mmio_write(BASE + 32'h030, short_length, 4'hf);
            mmio_write(BASE + 32'h034, 32'd1, 4'hf);
            build_r48(6'd17, 32'd0, response_frame);
            fork
                begin
                    send_r48(response_frame);
                    send_data_4bit(64'h0102_0304_0506_0708,
                                   1'b0, short_length);
                end
                begin
                    mmio_write(BASE + 32'h014, 32'd0, 4'hf);
                    mmio_write(BASE + 32'h018,
                               32'h0000_0800 | 32'h0000_0200 |
                               (32'd1 << 6) | 32'd17, 4'hf);
                end
            join
            wait_done();
            select_addr(BASE + 32'h03c);
            if (rdata[1:0] !== 2'b01)
                $fatal(1, "short RX block not ready at %0d bytes",
                       short_length);
            select_addr(BASE + 32'h100);
            case (short_length)
                1: if (rdata !== 32'h0000_0008)
                       $fatal(1, "one-byte RX zero fill %h", rdata);
                2: if (rdata !== 32'h0000_0807)
                       $fatal(1, "two-byte RX zero fill %h", rdata);
                3: if (rdata !== 32'h0008_0706)
                       $fatal(1, "three-byte RX zero fill %h", rdata);
                4: if (rdata !== 32'h0807_0605)
                       $fatal(1, "four-byte RX order %h", rdata);
                5: if (rdata !== 32'h0706_0504)
                       $fatal(1, "five-byte RX first word %h", rdata);
                6: if (rdata !== 32'h0605_0403)
                       $fatal(1, "six-byte RX first word %h", rdata);
                7: if (rdata !== 32'h0504_0302)
                       $fatal(1, "seven-byte RX first word %h", rdata);
            endcase
            if (short_length >= 5) begin
                select_addr(BASE + 32'h104);
                case (short_length)
                    5: if (rdata !== 32'h0000_0008)
                           $fatal(1, "five-byte RX zero fill %h", rdata);
                    6: if (rdata !== 32'h0000_0807)
                           $fatal(1, "six-byte RX zero fill %h", rdata);
                    7: if (rdata !== 32'h0008_0706)
                           $fatal(1, "seven-byte RX zero fill %h", rdata);
                endcase
            end
            if (dut.error_sticky !== 8'd0)
                $fatal(1, "short RX error at %0d bytes: %h",
                       short_length, dut.error_sticky);
        end
        mmio_write(BASE + 32'h03c, 32'h0000_0001, 4'h1);
        mmio_write(BASE + 32'h030, 32'd8, 4'hf);

        // R2 has an eight-bit unprotected header.  The following 120 register
        // bits use their own CRC7 and the returned registers drop the header.
        mmio_write(BASE + 32'h03c, 32'h0000_0001, 4'h1);
        mmio_write(BASE + 32'h008, 32'h0000_0006, 4'h1);
        build_r136(120'h0123_4567_89ab_cdef_1020_3040_5060_70,
                   response136_frame);
        response136_raw = response136_frame[127:0];
        fork
            send_r136(response136_frame);
            begin
                mmio_write(BASE + 32'h014, 32'd0, 4'hf);
                mmio_write(BASE + 32'h018,
                           32'h0000_0800 | (32'd3 << 6) | 32'd2,
                           4'hf);
            end
        join
        wait_done();
        select_addr(BASE + 32'h01c);
        if (rdata !== response136_raw[31:0])
            $fatal(1, "R136 RESP0 mismatch: %h", rdata);
        select_addr(BASE + 32'h020);
        if (rdata !== response136_raw[63:32])
            $fatal(1, "R136 RESP1 mismatch: %h", rdata);
        select_addr(BASE + 32'h024);
        if (rdata !== response136_raw[95:64])
            $fatal(1, "R136 RESP2 mismatch: %h", rdata);
        select_addr(BASE + 32'h028);
        if (rdata !== response136_raw[127:96])
            $fatal(1, "R136 RESP3 mismatch: %h", rdata);
        if (dut.error_sticky !== 8'd0)
            $fatal(1, "valid R136 reported error %h", dut.error_sticky);

        // Three blocks exercise both buffers.  Holding the first two buffers
        // forces a safe low-clock pause; releasing buffer 0 resumes block 2.
        mmio_write(BASE + 32'h008, 32'h0000_0006, 4'h1);
        mmio_write(BASE + 32'h030, 32'd8, 4'hf);
        mmio_write(BASE + 32'h034, 32'd3, 4'hf);
        build_r48(6'd18, 32'd0, response_frame);
        build_r48(6'd12, 32'd0, stop_response_frame);
        host_command = 48'd0;
        host_command_bits = 0;
        fork
            begin
                send_r48(response_frame);
                send_data_4bit(64'h0102_0304_0506_0708, 1'b0, 8);
                send_data_4bit(64'h1112_1314_1516_1718, 1'b0, 8);
                send_data_4bit(64'h2122_2324_2526_2728, 1'b0, 8);
                send_r48(stop_response_frame);
            end
            begin
                mmio_write(BASE + 32'h014, 32'd0, 4'hf);
                mmio_write(BASE + 32'h018,
                           32'h0000_0800 | 32'h0000_0400 |
                           32'h0000_0200 | (32'd1 << 6) | 32'd18,
                           4'hf);
                wait (dut.buffer0_ready && dut.buffer1_ready &&
                      (sd_clk == 1'b0));
                repeat (6) begin
                    @(posedge clk);
                    if (sd_clk !== 1'b0)
                        $fatal(1, "clock did not remain low while full");
                end
                select_addr(BASE + 32'h040);
                if (rdata[5:0] !== 6'd0)
                    $fatal(1, "buffer0 first index mismatch: %h", rdata);
                select_addr(BASE + 32'h100);
                if (rdata !== 32'h0403_0201)
                    $fatal(1, "multi block0 data mismatch: %h", rdata);
                select_addr(BASE + 32'h044);
                if (rdata[5:0] !== 6'd1)
                    $fatal(1, "buffer1 index mismatch: %h", rdata);
                select_addr(BASE + 32'h300);
                if (rdata !== 32'h1413_1211)
                    $fatal(1, "multi block1 data mismatch: %h", rdata);
                mmio_write(BASE + 32'h03c, 32'h0000_0001, 4'h1);
                mmio_write(BASE + 32'h03c, 32'h0000_0002, 4'h1);
                wait (dut.buffer0_ready &&
                      (dut.buffer0_block_index == 6'd2));
                select_addr(BASE + 32'h100);
                if (rdata !== 32'h2423_2221)
                    $fatal(1, "multi block2 data mismatch: %h", rdata);
                mmio_write(BASE + 32'h03c, 32'h0000_0001, 4'h1);
            end
        join
        wait_done();
        if (dut.blocks_done !== 6'd3)
            $fatal(1, "multi block count mismatch: %0d", dut.blocks_done);
        if (host_command_bits != 96 ||
            host_command !== 48'h4c00_0000_0061)
            $fatal(1, "automatic CMD12 missing: bits=%0d frame=%h",
                   host_command_bits, host_command);
        if (dut.error_sticky !== 8'd0)
            $fatal(1, "multi read reported error %h", dut.error_sticky);

        // A CRC-damaged R48b can still have been accepted by the card.  Keep
        // clocking until DAT0 busy releases, then publish the response error.
        mmio_write(BASE + 32'h008, 32'h0000_0006, 4'h1);
        build_r48(6'd12, 32'd0, stop_response_frame);
        stop_response_frame[1] = ~stop_response_frame[1];
        fork
            begin
                send_r48(stop_response_frame);
                card_dat = 4'b1110;
                repeat (40) begin
                    @(posedge clk);
                    #1;
                    if (dut.busy !== 1'b1)
                        $fatal(1, "bad R48b stopped before DAT0 busy release");
                    if (dut.error_sticky[1] !== 1'b0)
                        $fatal(1, "bad R48b CRC published before DAT0 busy release");
                end
                card_dat = 4'hf;
            end
            begin
                mmio_write(BASE + 32'h014, 32'd0, 4'hf);
                mmio_write(BASE + 32'h018,
                           32'h0000_0800 | (32'd4 << 6) | 32'd12,
                           4'hf);
            end
        join
        wait_done();
        select_addr(BASE + 32'h02c);
        if (rdata[1] !== 1'b1 || sd_clk !== 1'b0)
            $fatal(1, "bad R48b CRC/busy termination mismatch: %h", rdata);

        // A bad per-lane CRC must never publish the partially written block.
        mmio_write(BASE + 32'h008, 32'h0000_0006, 4'h1);
        mmio_write(BASE + 32'h034, 32'd1, 4'hf);
        build_r48(6'd17, 32'd0, response_frame);
        fork
            begin
                send_r48(response_frame);
                send_data_4bit(data_pattern, 1'b1, 8);
            end
            begin
                mmio_write(BASE + 32'h014, 32'd0, 4'hf);
                mmio_write(BASE + 32'h018,
                           32'h0000_0800 | 32'h0000_0200 |
                           (32'd1 << 6) | 32'd17,
                           4'hf);
            end
        join
        wait_done();
        select_addr(BASE + 32'h02c);
        if (rdata[4] !== 1'b1)
            $fatal(1, "bad DAT CRC was not reported: %h", rdata);
        select_addr(BASE + 32'h03c);
        if (rdata[1:0] !== 2'b00)
            $fatal(1, "bad DAT CRC published a buffer: %h", rdata);

        // Missing response, hot removal, and explicit abort all return the
        // externally visible pins to a deterministic low-clock/released-CMD
        // state.
        mmio_write(BASE + 32'h008, 32'h0000_0006, 4'h1);
        mmio_write(BASE + 32'h014, 32'd0, 4'hf);
        mmio_write(BASE + 32'h018,
                   32'h0000_0800 | (32'd1 << 6) | 32'd13, 4'hf);
        wait_done();
        select_addr(BASE + 32'h02c);
        if (rdata !== 32'h0000_0001 || sd_clk !== 1'b0 ||
            sd_cmd_oe !== 1'b0)
            $fatal(1, "command timeout termination mismatch: %h", rdata);

        mmio_write(BASE + 32'h008, 32'h0000_0006, 4'h1);
        mmio_write(BASE + 32'h018,
                   32'h0000_0800 | (32'd1 << 6) | 32'd13, 4'hf);
        wait (dut.state == 5'd3);
        @(negedge clk);
        sd_detect_n = 1'b1;
        wait (dut.busy == 1'b0);
        select_addr(BASE + 32'h02c);
        if (rdata[6] !== 1'b1 || sd_clk !== 1'b0 ||
            sd_cmd_oe !== 1'b0)
            $fatal(1, "removal termination mismatch: %h", rdata);
        @(negedge clk);
        sd_detect_n = 1'b0;
        repeat (6) @(posedge clk);

        mmio_write(BASE + 32'h008, 32'h0000_0006, 4'h1);
        mmio_write(BASE + 32'h018,
                   32'h0000_0800 | (32'd1 << 6) | 32'd13, 4'hf);
        wait (dut.state == 5'd3);
        mmio_write(BASE + 32'h008, 32'h0000_000a, 4'h1);
        select_addr(BASE + 32'h00c);
        if (rdata[10] !== 1'b1 || rdata[0] !== 1'b0 ||
            sd_clk !== 1'b0 || sd_cmd_oe !== 1'b0)
            $fatal(1, "abort did not retain bus4/quiesce: %h", rdata);

        check_reset_rx_collision(32'h0000_0001, 32'hf0e1_d2c3);
        check_reset_rx_collision(32'h0000_0008, 32'h1021_3243);

        $display("SD_NATIVE_MMIO_PASS");
        $finish;
    end
endmodule
