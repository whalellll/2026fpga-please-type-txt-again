`timescale 1ns / 1ps

module tb_mac_weight_double_buffer;
    reg clk = 0;
    always #5 clk = ~clk;
    reg resetn = 0;
    reg load_start = 0, load_valid = 0, load_last = 0, load_abort = 0;
    reg [2:0] load_lines = 0;
    reg [63:0] load_model_id = 0;
    reg [31:0] load_generation = 0, load_tile_id = 0;
    reg [1023:0] load_data = 0;
    wire load_start_ready, load_ready, load_error;
    reg activate = 0, compute_idle = 0, window_done = 0;
    wire activate_ready, active_valid, pending_valid;
    wire [63:0] active_model_id;
    wire [31:0] active_generation, active_tile_id, reuse_count;
    wire [2:0] active_lines;
    reg read_en = 0;
    reg [1:0] read_addr = 0;
    wire read_valid;
    wire [1023:0] read_data;

    mac_weight_double_buffer #(.DEPTH(4), .ADDR_WIDTH(2)) dut (.*);

    task tick;
        begin @(posedge clk); #1; end
    endtask

    task check;
        input condition;
        input [255:0] message;
        begin if (!condition) $fatal(1, "FAIL weight double buffer: %0s", message); end
    endtask

    task start_tile;
        input [2:0] lines;
        input [31:0] generation;
        input [31:0] tile_id;
        begin
            @(negedge clk);
            check(load_start_ready, "start not ready");
            load_lines = lines;
            load_model_id = 64'h1234_5678_9abc_def0;
            load_generation = generation;
            load_tile_id = tile_id;
            load_start = 1;
            tick();
            @(negedge clk); load_start = 0;
        end
    endtask

    task send_line;
        input [31:0] word;
        input last;
        begin
            @(negedge clk);
            check(load_ready, "line not ready");
            load_data = {32{word}};
            load_last = last;
            load_valid = 1;
            tick();
            @(negedge clk); load_valid = 0; load_last = 0;
        end
    endtask

    task read_line;
        input [1:0] address;
        input [31:0] expected;
        begin
            @(negedge clk); read_addr = address; read_en = 1;
            tick();
            check(read_valid, "read valid missing");
            check(read_data === {32{expected}}, "wrong active weight line");
            @(negedge clk); read_en = 0;
        end
    endtask

    initial begin
        repeat (3) tick();
        @(negedge clk); resetn = 1;

        start_tile(0, 1, 1);
        check(load_error && !load_ready && !pending_valid, "zero length accepted");
        start_tile(5, 1, 1);
        check(load_error && !load_ready && !pending_valid, "oversize accepted");

        start_tile(2, 1, 7);
        send_line(32'h01020304, 1);
        check(load_error && !pending_valid && !active_valid,
              "early last published a partial tile");

        start_tile(2, 1, 7);
        send_line(32'h01020304, 0);
        repeat (3) begin
            tick();
            check(load_ready && !pending_valid, "backpressure lost partial tile");
        end
        send_line(32'h05060708, 1);
        check(pending_valid && !load_start_ready, "full tile not pending");
        @(negedge clk); activate = 1;
        tick();
        check(!active_valid && pending_valid, "swapped while compute busy");
        @(negedge clk); compute_idle = 1;
        tick();
        check(active_valid && !pending_valid && active_generation == 1 &&
              active_tile_id == 7 && active_lines == 2 &&
              active_model_id == 64'h1234_5678_9abc_def0,
              "initial tile metadata/swap failed");
        @(negedge clk); activate = 0; compute_idle = 0;
        read_line(0, 32'h01020304);
        read_line(1, 32'h05060708);

        // A new tile loads into the inactive bank during active reads.
        start_tile(1, 2, 8);
        @(negedge clk); load_data = {32{32'haabbccdd}};
        load_last = 1; load_valid = 1;
        read_en = 1; read_addr = 1;
        tick();
        check(read_valid && read_data === {32{32'h05060708}},
              "active bank changed during update");
        @(negedge clk); load_valid = 0; load_last = 0; read_en = 0;
        check(pending_valid, "second tile not pending");
        read_line(0, 32'h01020304);

        @(negedge clk); window_done = 1;
        repeat (3) tick();
        check(reuse_count == 3, "window reuse counter wrong");
        @(negedge clk); window_done = 0; compute_idle = 1; activate = 1;
        read_en = 1; read_addr = 0;
        tick();
        check(active_generation == 1 && pending_valid,
              "swapped during active read");
        @(negedge clk); read_en = 0;
        tick();
        check(active_generation == 2 && active_tile_id == 8 &&
              active_lines == 1 && reuse_count == 0,
              "second tile swap failed");
        @(negedge clk); activate = 0; compute_idle = 0;
        read_line(0, 32'haabbccdd);
        @(negedge clk); read_addr = 1; read_en = 1;
        tick();
        check(!read_valid, "tail address was readable");
        @(negedge clk); read_en = 0;

        start_tile(2, 3, 9);
        send_line(32'h11111111, 0);
        @(negedge clk); load_abort = 1;
        tick();
        check(!pending_valid && !load_ready && active_generation == 2,
              "abort damaged active tile");
        @(negedge clk); load_abort = 0;
        read_line(0, 32'haabbccdd);

        start_tile(1, 3, 9);
        send_line(32'h22222222, 0);
        check(load_error && !pending_valid && !load_ready,
              "missing last published a tile");
        read_line(0, 32'haabbccdd);

        // Fill the entire bank, then drop a complete pending tile.
        start_tile(4, 3, 10);
        send_line(32'h11111111, 0);
        send_line(32'h22222222, 0);
        send_line(32'h33333333, 0);
        send_line(32'h44444444, 1);
        check(pending_valid, "full-depth tile not pending");
        @(negedge clk); load_abort = 1;
        tick();
        check(!pending_valid && active_generation == 2,
              "pending abort damaged active tile");
        @(negedge clk); load_abort = 0;
        read_line(0, 32'haabbccdd);

        start_tile(4, 4, 11);
        send_line(32'h55555555, 0);
        send_line(32'h66666666, 0);
        send_line(32'h77777777, 0);
        send_line(32'h88888888, 1);
        @(negedge clk); compute_idle = 1; activate = 1;
        tick();
        check(active_generation == 4 && active_lines == 4,
              "full-depth tile swap failed");
        @(negedge clk); activate = 0; compute_idle = 0;
        read_line(3, 32'h88888888);

        $display("MAC_WEIGHT_DOUBLE_BUFFER_PASS");
        $finish;
    end
endmodule
