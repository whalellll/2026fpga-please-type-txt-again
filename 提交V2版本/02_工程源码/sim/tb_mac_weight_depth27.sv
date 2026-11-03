`timescale 1ns / 1ps
module tb_mac_weight_depth27;
    reg clk = 0;
    always #5 clk = ~clk;
    reg resetn = 0;
    reg load_start = 0, load_valid = 0, load_last = 0, load_abort = 0;
    reg [5:0] load_lines = 0;
    reg [63:0] load_model_id = 0;
    reg [31:0] load_generation = 0, load_tile_id = 0;
    reg [1023:0] load_data = 0;
    wire load_start_ready, load_ready, load_error;
    reg activate = 0, compute_idle = 1, window_done = 0;
    wire activate_ready, active_valid, pending_valid;
    wire [63:0] active_model_id;
    wire [31:0] active_generation, active_tile_id, reuse_count;
    wire [5:0] active_lines;
    reg read_en = 0;
    reg [4:0] read_addr = 0;
    wire read_valid;
    wire [1023:0] read_data;
    integer i;
    integer overlap_reads = 0, load_beats = 0;

    mac_weight_double_buffer dut (.*);

    task tick;
        begin @(posedge clk); #1; end
    endtask
    task start_load;
        input [31:0] generation;
        begin
            @(negedge clk);
            if (!load_start_ready) $fatal(1, "load start blocked");
            load_lines = 27;
            load_model_id = 64'h5555_0000_1234_abcd;
            load_generation = generation;
            load_tile_id = generation + 10;
            load_start = 1;
            tick();
            @(negedge clk); load_start = 0;
        end
    endtask
    task send_line;
        input integer index;
        input [31:0] base;
        begin
            @(negedge clk);
            if (!load_ready) $fatal(1, "load stalled at line %0d", index);
            load_data = {32{base + index}};
            load_last = (index == 26);
            load_valid = 1;
            tick();
            load_beats = load_beats + 1;
            @(negedge clk); load_valid = 0; load_last = 0;
        end
    endtask
    task read_line;
        input integer index;
        input [31:0] expected;
        begin
            @(negedge clk); read_addr = index; read_en = 1;
            tick();
            if (!read_valid || read_data !== {32{expected}})
                $fatal(1, "wrong active line %0d: %h", index, read_data[31:0]);
            @(negedge clk); read_en = 0;
        end
    endtask

    initial begin
        repeat (3) tick();
        @(negedge clk); resetn = 1;
        start_load(1);
        for (i = 0; i < 27; i = i + 1) send_line(i, 32'h1000);
        if (!pending_valid || load_error) $fatal(1, "27-line tile not pending");
        @(negedge clk); activate = 1;
        tick();
        if (!active_valid || active_lines != 27 || active_generation != 1)
            $fatal(1, "27-line tile activation failed");
        @(negedge clk); activate = 0; compute_idle = 0;
        read_line(26, 32'h101a);

        start_load(2);
        for (i = 0; i < 27; i = i + 1) begin
            @(negedge clk);
            if (!load_ready) $fatal(1, "second bank stalled");
            load_data = {32{32'h2000 + i}};
            load_last = (i == 26);
            load_valid = 1;
            read_addr = i;
            read_en = 1;
            tick();
            load_beats = load_beats + 1;
            if (!read_valid || read_data !== {32{32'h1000 + i}})
                $fatal(1, "active read corrupt during inactive load %0d", i);
            overlap_reads = overlap_reads + 1;
            @(negedge clk); load_valid = 0; load_last = 0; read_en = 0;
        end
        if (!pending_valid || active_generation != 1 || overlap_reads != 27)
            $fatal(1, "27-line bank overlap failed");
        @(negedge clk); compute_idle = 1; activate = 1;
        tick();
        if (active_generation != 2 || active_tile_id != 12 ||
            active_model_id != 64'h5555_0000_1234_abcd || active_lines != 27)
            $fatal(1, "second 27-line bank metadata/swap failed");
        @(negedge clk); activate = 0;
        read_line(26, 32'h201a);
        $display("T3_WEIGHT_DEPTH27_PASS load_beats=%0d overlap_reads=%0d", load_beats, overlap_reads);
        $finish;
    end
endmodule
