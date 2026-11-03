`timescale 1ns/1ps

// Matching SoC ADS VM R-channel FIFO: 36 payload bits remain observable.
module tb_mapped_r_fifo;
    integer cpu_half = 7, sys_half = 11, sys_phase = 3;
    reg [31:0] seed = 32'h1a2b3c4d;
    reg cpu_clk = 0, sys_clk = 0;
    reg reset_clear = 1, produce = 0, drain = 0;
    reg [31:0] wr_rng, rd_rng;
    reg wr_request = 0, rd_request = 0;
    reg [38:0] wr_data = 0;
    wire [38:0] rd_data;
    wire [4:0] rd_gray, rd_gray_wr2, wr_gray, wr_gray_rd2;
    wire partial_not_full, partial_not_empty;
    wire fifo_not_full = wr_gray !=
        {~rd_gray_wr2[4:3], rd_gray_wr2[2:0]};
    wire fifo_not_empty = rd_gray != wr_gray_rd2;
    wire wr_fire = !reset_clear && wr_request && fifo_not_full;
    wire rd_fire = !reset_clear && rd_request && fifo_not_empty;
    // ADS optimized out payload bits 1, 37, and 38 across the full SoC.
    localparam [38:0] RETAINED_MASK = 39'h1ffffffffd;

    // Positional ports are checked by run_mapped_gate_tests.ps1 before compile.
    axi_async_fifo_2 dut (
        wr_data, cpu_clk, rd_fire, reset_clear, reset_clear,
        sys_clk, wr_fire, rd_data, rd_gray, rd_gray_wr2, wr_gray,
        wr_gray_rd2, partial_not_full, partial_not_empty
    );
    GTP_GRS GRS_INST (.GRS_N(1'b1));

    always #(cpu_half) cpu_clk = ~cpu_clk;
    initial begin
        if ($value$plusargs("cpu_half=%d", cpu_half)) begin end
        if ($value$plusargs("sys_half=%d", sys_half)) begin end
        if ($value$plusargs("sys_phase=%d", sys_phase)) begin end
        if ($value$plusargs("seed=%d", seed)) begin end
        if (cpu_half < 2 || sys_half < 2 || sys_phase < 1 || seed == 0)
            $fatal(1, "bad case parameters");
        #(sys_phase);
        forever #(sys_half) sys_clk = ~sys_clk;
    end

    reg [38:0] expected [0:4095];
    integer head = 0, tail = 0;
    integer writes = 0, reads = 0;
    integer wr_stalls = 0, rd_stalls = 0, sys_edges = 0;
    integer reset_pending = 0, phase_step = 0;
    reg [4:0] prev_wr_gray = 0, prev_rd_gray = 0;
    reg prev_wr_valid = 0, prev_rd_valid = 0;
    reg held = 0;
    reg [38:0] held_payload = 0;
    reg [4:0] wr_gray_change, rd_gray_change;
    reg [4:0] wr_stage1_before, rd_stage1_before;

    always @(negedge sys_clk) begin
        if (reset_clear) begin
            wr_request = 0;
            wr_data = 0;
            wr_rng = seed ^ 32'hd9b4c3a5;
        end else begin
            wr_rng = {wr_rng[30:0],
                wr_rng[31] ^ wr_rng[21] ^ wr_rng[1] ^ wr_rng[0]};
            wr_request = produce && (wr_rng[3:0] != 0);
            wr_data = {wr_rng[6:0] ^ seed[6:0], wr_rng};
        end
    end

    always @(negedge cpu_clk) begin
        if (reset_clear) begin
            rd_request = 0;
            rd_rng = seed ^ 32'h73a51f09;
        end else begin
            rd_rng = {rd_rng[30:0],
                rd_rng[31] ^ rd_rng[21] ^ rd_rng[1] ^ rd_rng[0]};
            rd_request = drain || (rd_rng[3:0] < 9);
        end
    end

    always @(posedge sys_clk) begin
        sys_edges = sys_edges + 1;
        if (reset_clear) begin
            prev_wr_valid = 0;
        end else begin
            if (prev_wr_valid) begin
                wr_gray_change = wr_gray ^ prev_wr_gray;
                if ((wr_gray_change & (wr_gray_change - 5'd1)) != 0)
                    $fatal(1, "R write Gray pointer changed multiple bits");
            end
            prev_wr_gray = wr_gray;
            prev_wr_valid = 1;
            if (wr_request && !fifo_not_full) wr_stalls = wr_stalls + 1;
            if (wr_fire) begin
                if (tail >= 4096 || tail - head >= 16)
                    $fatal(1, "mapped R FIFO overfilled or scoreboard overflow");
                expected[tail] = wr_data;
                tail = tail + 1;
                writes = writes + 1;
            end
            wr_stage1_before = dut.rd_gray_wr1;
            #1;
            if (rd_gray_wr2 !== wr_stage1_before)
                $fatal(1, "R read Gray stage2 did not sample stage1");
        end
    end

    always @(posedge cpu_clk) begin
        if (reset_clear) begin
            prev_rd_valid = 0;
            held = 0;
        end else begin
            if (prev_rd_valid) begin
                rd_gray_change = rd_gray ^ prev_rd_gray;
                if ((rd_gray_change & (rd_gray_change - 5'd1)) != 0)
                    $fatal(1, "R read Gray pointer changed multiple bits");
            end
            prev_rd_gray = rd_gray;
            prev_rd_valid = 1;
            if (held && (rd_data & RETAINED_MASK) !==
                (held_payload & RETAINED_MASK))
                $fatal(1, "stalled mapped R payload changed");
            if (fifo_not_empty && !rd_request) rd_stalls = rd_stalls + 1;
            if (rd_fire) begin
                if (head >= tail)
                    $fatal(1, "mapped R FIFO read without expected write");
                if ((rd_data & RETAINED_MASK) !==
                    (expected[head] & RETAINED_MASK))
                    $fatal(1, "mapped R payload mismatch index=%0d got=%h want=%h",
                        head, rd_data & RETAINED_MASK,
                        expected[head] & RETAINED_MASK);
                head = head + 1;
                reads = reads + 1;
            end
            held = fifo_not_empty && !rd_fire;
            held_payload = rd_data;
            rd_stage1_before = dut.wr_gray_rd1;
            #1;
            if (wr_gray_rd2 !== rd_stage1_before)
                $fatal(1, "R write Gray stage2 did not sample stage1");
        end
    end

    initial begin
        #40;
        reset_clear = 0;
        produce = 1;
        phase_step = 1;
        wait (sys_edges >= 130);
        @(negedge sys_clk);
        #1;
        if (tail == head)
            $fatal(1, "R in-flight reset had no outstanding payload");
        reset_pending = tail - head;
        phase_step = 2;
        produce = 0;
        reset_clear = 1;
        head = 0;
        tail = 0;
        #31;
        if (rd_gray !== 0 || wr_gray !== 0 ||
            rd_gray_wr2 !== 0 || wr_gray_rd2 !== 0)
            $fatal(1, "mapped R Gray state failed asynchronous reset");
        reset_clear = 0;
        produce = 1;
        phase_step = 3;
        wait (sys_edges >= 360);
        @(negedge sys_clk);
        produce = 0;
        repeat (3) @(posedge sys_clk);
        drain = 1;
        phase_step = 4;
        wait (head == tail && !fifo_not_empty);
        repeat (5) @(posedge cpu_clk);
        if (writes < 100 || reads < 70 || reset_pending < 1 ||
            wr_stalls < 1 || rd_stalls < 1)
            $fatal(1, "R coverage shortfall writes=%0d reads=%0d pending=%0d wstall=%0d rstall=%0d",
                writes, reads, reset_pending, wr_stalls, rd_stalls);
        $display("MAPPED_R_FIFO_PASS cpu_half=%0d sys_half=%0d phase=%0d seed=%0d writes=%0d reads=%0d reset_pending=%0d wr_stalls=%0d rd_stalls=%0d",
            cpu_half, sys_half, sys_phase, seed, writes, reads,
            reset_pending, wr_stalls, rd_stalls);
        $finish;
    end

    initial begin
        #300000;
        $display("DEBUG step=%0d sys_edges=%0d h=%0d t=%0d writes=%0d reads=%0d pending=%0d nonempty=%b",
            phase_step, sys_edges, head, tail, writes, reads,
            reset_pending, fifo_not_empty);
        $fatal(1, "mapped R FIFO test timeout");
    end
endmodule
