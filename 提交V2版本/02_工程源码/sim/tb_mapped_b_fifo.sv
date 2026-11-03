`timescale 1ns/1ps

// Uses the B FIFO submodule in a matching integrated SoC ADS VM. ADS retained one
// payload bit after whole-SoC optimization, so this checks that bit plus the
// mapped FIFO pointer/synchronizer behavior; it is not an AXI-wide test.
module tb_mapped_b_fifo;
    integer cpu_half = 7;
    integer sys_half = 11;
    integer sys_phase = 3;
    reg [31:0] seed = 32'h1a2b3c4d;
    reg cpu_clk = 0;
    reg sys_clk = 0;
    reg reset_clear = 1;
    reg produce = 0;
    reg drain = 0;
    reg [31:0] wr_rng;
    reg [31:0] rd_rng;
    reg wr_request = 0;
    reg rd_request = 0;
    reg [5:0] wr_data = 0;
    reg [1:0] b_count = 0;
    reg c_bvalid = 0;
    wire [5:0] rd_data;
    wire [4:0] rd_gray, rd_gray_wr2, wr_gray, wr_gray_rd2;
    wire not_full, not_empty, rd_fire;
    // Whole-SoC optimization split the full/empty comparisons; the two
    // named LUT outputs above are only partial terms. Use retained mapped
    // Gray pointers for the source FIFO's complete flow-control comparisons.
    wire fifo_not_full = wr_gray !=
        {~rd_gray_wr2[4:3], rd_gray_wr2[2:0]};
    wire fifo_not_empty = rd_gray != wr_gray_rd2;
    wire wr_fire = !reset_clear && wr_request && fifo_not_full;

    // Positional ports follow the ADS VM declaration at line 204549.
    axi_async_fifo_3 dut (
        b_count, wr_data, cpu_clk, c_bvalid, reset_clear,
        reset_clear, sys_clk, wr_fire, rd_data, rd_gray,
        rd_gray_wr2, wr_gray, wr_gray_rd2,
        not_full, not_empty, rd_fire
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

    reg expected [0:4095];
    integer head = 0;
    integer tail = 0;
    integer writes = 0;
    integer reads = 0;
    integer wr_stalls = 0;
    integer rd_stalls = 0;
    integer sys_edges = 0;
    integer reset_pending = 0;
    integer phase_step = 0;
    reg [4:0] prev_wr_gray = 0;
    reg [4:0] prev_rd_gray = 0;
    reg prev_wr_valid = 0;
    reg prev_rd_valid = 0;
    reg held = 0;
    reg held_bit = 0;
    reg [4:0] wr_gray_change;
    reg [4:0] rd_gray_change;
    reg [4:0] wr_stage1_before;
    reg [4:0] rd_stage1_before;

    always @(negedge sys_clk) begin
        if (reset_clear) begin
            wr_request = 0;
            wr_data = 0;
            wr_rng = seed ^ 32'hd9b4c3a5;
        end else begin
            wr_rng = {wr_rng[30:0],
                wr_rng[31] ^ wr_rng[21] ^ wr_rng[1] ^ wr_rng[0]};
            wr_request = produce && (wr_rng[3:0] != 0);
            wr_data[1] = wr_rng[9];
        end
    end

    always @(negedge cpu_clk) begin
        if (reset_clear) begin
            rd_request = 0;
            b_count = 0;
            c_bvalid = 0;
            rd_rng = seed ^ 32'h73a51f09;
        end else begin
            rd_rng = {rd_rng[30:0],
                rd_rng[31] ^ rd_rng[21] ^ rd_rng[1] ^ rd_rng[0]};
            rd_request = drain || (rd_rng[3:0] < 9);
            b_count = {1'b0, rd_request};
            c_bvalid = fifo_not_empty;
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
                    $fatal(1, "write Gray pointer changed multiple bits");
            end
            prev_wr_gray = wr_gray;
            prev_wr_valid = 1;
            if (wr_request && !fifo_not_full) wr_stalls = wr_stalls + 1;
            if (wr_fire) begin
                if (tail >= 4096 || tail - head >= 16)
                    $fatal(1, "mapped FIFO overfilled or scoreboard overflow");
                expected[tail] = wr_data[1];
                tail = tail + 1;
                writes = writes + 1;
            end
            wr_stage1_before = dut.rd_gray_wr1;
            #1;
            if (rd_gray_wr2 !== wr_stage1_before)
                $fatal(1, "read Gray stage2 did not sample stage1");
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
                    $fatal(1, "read Gray pointer changed multiple bits");
            end
            prev_rd_gray = rd_gray;
            prev_rd_valid = 1;
            if (held && rd_data[1] !== held_bit)
                $fatal(1, "stalled mapped B payload changed");
            if (fifo_not_empty && !rd_request) rd_stalls = rd_stalls + 1;
            if (rd_fire) begin
                if (head >= tail)
                    $fatal(1, "mapped FIFO read without expected write");
                if (rd_data[1] !== expected[head])
                    $fatal(1, "mapped B payload mismatch index=%0d got=%b want=%b",
                        head, rd_data[1], expected[head]);
                head = head + 1;
                reads = reads + 1;
            end
            held = fifo_not_empty && !rd_fire;
            held_bit = rd_data[1];
            rd_stage1_before = dut.wr_gray_rd1;
            #1;
            if (wr_gray_rd2 !== rd_stage1_before)
                $fatal(1, "write Gray stage2 did not sample stage1");
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
            $fatal(1, "in-flight reset scenario had no outstanding payload");
        reset_pending = tail - head;
        phase_step = 2;
        produce = 0;
        reset_clear = 1;
        head = 0;
        tail = 0;
        #31;
        if (rd_gray !== 0 || wr_gray !== 0 ||
            rd_gray_wr2 !== 0 || wr_gray_rd2 !== 0)
            $fatal(1, "mapped Gray state failed asynchronous reset");
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
            $fatal(1, "coverage shortfall writes=%0d reads=%0d pending=%0d wstall=%0d rstall=%0d",
                writes, reads, reset_pending, wr_stalls, rd_stalls);
        $display("MAPPED_B_FIFO_PASS cpu_half=%0d sys_half=%0d phase=%0d seed=%0d writes=%0d reads=%0d reset_pending=%0d wr_stalls=%0d rd_stalls=%0d",
            cpu_half, sys_half, sys_phase, seed, writes, reads,
            reset_pending, wr_stalls, rd_stalls);
        $finish;
    end

    initial begin
        #300000;
        $display("DEBUG step=%0d sys_edges=%0d h=%0d t=%0d writes=%0d reads=%0d reset_pending=%0d fifo_not_empty=%b wr_stalls=%0d rd_stalls=%0d rd_fire=%b wr_fire=%b rd_gray=%h wr_gray=%h",
            phase_step, sys_edges, head, tail, writes, reads,
            reset_pending, fifo_not_empty, wr_stalls, rd_stalls,
            rd_fire, wr_fire, rd_gray, wr_gray);
        $fatal(1, "mapped B FIFO test timeout");
    end
endmodule
