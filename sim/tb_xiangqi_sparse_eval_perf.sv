`timescale 1ns/1ps

// Performance-oriented simulation for xiangqi_sparse_eval.
//
// This is not a cycle-accurate DDR3 model.  It deliberately sweeps synthetic
// first-beat latency and inter-beat gaps, then reports where the evaluator
// spends its cycles.  The burst/beat assertions keep the measurements honest.
module tb_xiangqi_sparse_eval_perf;
    localparam [31:0] DDR_BASE    = 32'h1000_0000;
    localparam [31:0] MODEL_BASE  = 32'h1000_0000;
    localparam [31:0] PARENT_BASE = 32'h1000_1000;
    localparam [31:0] WEIGHT_BASE = 32'h1000_1400;
    localparam [31:0] DESC_BASE   = 32'h1000_1600;
    localparam integer MODEL_ROWS = 16;
    localparam integer WORDS      = 16 * 1024;

    reg clk = 0;
    reg resetn = 0;
    always #5 clk = ~clk;

    reg         reg_wr_en = 0;
    reg [7:0]   reg_wr_addr = 0;
    reg [31:0]  reg_wr_data = 0;
    reg [3:0]   reg_wr_strb = 4'hf;
    reg [7:0]   reg_rd_addr = 0;
    wire [31:0] reg_rd_data;

    wire        mem_req_valid;
    wire        mem_req_ready;
    wire        mem_req_write;
    wire [31:0] mem_req_addr;
    wire [2:0]  mem_req_len;
    wire        mem_w_valid;
    wire        mem_w_ready;
    wire [31:0] mem_w_data;
    wire [3:0]  mem_w_strb;
    wire        mem_w_last;
    reg         mem_rsp_valid = 0;
    wire        mem_rsp_ready;
    reg [31:0]  mem_rsp_rdata = 0;
    reg         mem_rsp_last = 0;
    reg         mem_rsp_error = 0;
    wire        irq;

    reg [31:0] memory [0:WORDS-1];
    reg         rd_active = 0;
    reg [31:0]  rd_addr = 0;
    reg [3:0]   rd_beats_left = 0;
    integer     wait_cycles = 0;
    integer     read_latency_cfg = 0;
    integer     beat_gap_cfg = 0;
    integer     burst_count = 0;
    integer     beat_count = 0;

    integer perf_preload_cycles = 0;
    integer perf_descriptor_cycles = 0;
    integer perf_row_cycles = 0;
    integer perf_clear_cycles = 0;
    integer perf_row_pick_cycles = 0;
    integer perf_mac_cycles = 0;
    integer perf_divide_cycles = 0;
    integer perf_next_cycles = 0;

    assign mem_req_ready = !rd_active && !mem_rsp_valid;
    assign mem_w_ready = 1'b0;

    xiangqi_sparse_eval #(
        .DDR_BASE(DDR_BASE),
        .DDR_BYTES(64 * 1024),
        .MODEL_ROWS(MODEL_ROWS)
    ) dut (
        .clk(clk), .resetn(resetn),
        .reg_wr_en(reg_wr_en), .reg_wr_addr(reg_wr_addr),
        .reg_wr_data(reg_wr_data), .reg_wr_strb(reg_wr_strb),
        .reg_rd_addr(reg_rd_addr), .reg_rd_data(reg_rd_data),
        .mem_req_valid(mem_req_valid), .mem_req_ready(mem_req_ready),
        .mem_req_write(mem_req_write), .mem_req_addr(mem_req_addr),
        .mem_req_len(mem_req_len), .mem_w_valid(mem_w_valid),
        .mem_w_ready(mem_w_ready), .mem_w_data(mem_w_data),
        .mem_w_strb(mem_w_strb), .mem_w_last(mem_w_last),
        .mem_rsp_valid(mem_rsp_valid), .mem_rsp_ready(mem_rsp_ready),
        .mem_rsp_rdata(mem_rsp_rdata), .mem_rsp_last(mem_rsp_last),
        .mem_rsp_error(mem_rsp_error), .irq(irq)
    );

    // Configurable read-memory timing model.  Requests are always accepted
    // when idle; each burst can wait before its first beat and between beats.
    always @(posedge clk) begin
        if (!resetn) begin
            rd_active <= 0;
            rd_addr <= 0;
            rd_beats_left <= 0;
            wait_cycles <= 0;
            mem_rsp_valid <= 0;
            mem_rsp_rdata <= 0;
            mem_rsp_last <= 0;
            mem_rsp_error <= 0;
            burst_count <= 0;
            beat_count <= 0;
        end else begin
            if (mem_req_valid && mem_req_ready) begin
                if (mem_req_write)
                    $fatal(1, "FAIL perf: evaluator issued a write");
                rd_active <= 1;
                rd_addr <= mem_req_addr;
                rd_beats_left <= {1'b0, mem_req_len} + 4'd1;
                wait_cycles <= read_latency_cfg;
                burst_count <= burst_count + 1;
            end

            if (rd_active && !mem_rsp_valid) begin
                if (wait_cycles != 0) begin
                    wait_cycles <= wait_cycles - 1;
                end else begin
                    mem_rsp_valid <= 1;
                    mem_rsp_rdata <= memory[(rd_addr - DDR_BASE) >> 2];
                    mem_rsp_last <= (rd_beats_left == 1);
                    mem_rsp_error <= (rd_addr < DDR_BASE) ||
                        (rd_addr >= DDR_BASE + 64 * 1024);
                end
            end else if (mem_rsp_valid && mem_rsp_ready) begin
                beat_count <= beat_count + 1;
                if (mem_rsp_last) begin
                    mem_rsp_valid <= 0;
                    rd_active <= 0;
                end else begin
                    rd_addr <= rd_addr + 4;
                    rd_beats_left <= rd_beats_left - 1;
                    if (beat_gap_cfg == 0) begin
                        // Keep valid asserted and advance the payload so an
                        // ideal burst transfers one beat every clock.
                        mem_rsp_valid <= 1;
                        mem_rsp_rdata <= memory[((rd_addr + 4) -
                                                DDR_BASE) >> 2];
                        mem_rsp_last <= (rd_beats_left == 2);
                        mem_rsp_error <= ((rd_addr + 4) < DDR_BASE) ||
                            ((rd_addr + 4) >= DDR_BASE + 64 * 1024);
                    end else begin
                        mem_rsp_valid <= 0;
                        wait_cycles <= beat_gap_cfg - 1;
                    end
                end
            end
        end
    end

    // State-level attribution.  These counters add up exactly to the public
    // CYCLES register, so latency and compute costs can be compared directly.
    always @(posedge clk) begin
        if (!resetn) begin
            perf_preload_cycles <= 0;
            perf_descriptor_cycles <= 0;
            perf_row_cycles <= 0;
            perf_clear_cycles <= 0;
            perf_row_pick_cycles <= 0;
            perf_mac_cycles <= 0;
            perf_divide_cycles <= 0;
            perf_next_cycles <= 0;
        end else if (dut.busy) begin
            case (dut.state)
                4'd1, 4'd2, 4'd3, 4'd4:
                    perf_preload_cycles <= perf_preload_cycles + 1;
                4'd5, 4'd6:
                    perf_descriptor_cycles <= perf_descriptor_cycles + 1;
                4'd7:
                    perf_clear_cycles <= perf_clear_cycles + 1;
                4'd8:
                    perf_row_pick_cycles <= perf_row_pick_cycles + 1;
                4'd9, 4'd10:
                    perf_row_cycles <= perf_row_cycles + 1;
                4'd11:
                    perf_mac_cycles <= perf_mac_cycles + 1;
                4'd12, 4'd13:
                    perf_divide_cycles <= perf_divide_cycles + 1;
                4'd14:
                    perf_next_cycles <= perf_next_cycles + 1;
                default: $fatal(1, "FAIL perf: busy in state %0d", dut.state);
            endcase
        end
    end

    task fail;
        input [511:0] why;
        begin
            $fatal(1, "FAIL tb_xiangqi_sparse_eval_perf: %0s", why);
        end
    endtask

    task reg_write;
        input [7:0] address;
        input [31:0] value;
        begin
            @(negedge clk);
            reg_wr_addr = address;
            reg_wr_data = value;
            reg_wr_en = 1;
            @(posedge clk);
            #1;
            @(negedge clk);
            reg_wr_en = 0;
        end
    endtask

    task wait_done;
        output [31:0] status;
        integer timeout;
        begin
            reg_rd_addr = 8'h8c;
            #1;
            timeout = 0;
            while (!reg_rd_data[1] && timeout < 500000) begin
                @(posedge clk);
                #1;
                timeout = timeout + 1;
            end
            if (timeout == 500000)
                fail("completion timeout");
            status = reg_rd_data;
        end
    endtask

    task prepare_descriptors;
        input integer children;
        input integer rows_per_child;
        integer child;
        integer slot;
        integer base_word;
        begin
            for (child = 0; child < 16; child = child + 1) begin
                base_word = ((DESC_BASE - DDR_BASE) >> 2) + child * 8;
                memory[base_word] = child & 1;
                for (slot = 0; slot < 6; slot = slot + 1) begin
                    if ((child < children) && (slot < rows_per_child))
                        memory[base_word + slot + 1] =
                            (child + slot) % MODEL_ROWS;
                    else
                        memory[base_word + slot + 1] = 32'hffff_ffff;
                end
                memory[base_word + 7] = 0;
            end
        end
    endtask

    task clear_perf_counters;
        begin
            @(negedge clk);
            burst_count = 0;
            beat_count = 0;
            perf_preload_cycles = 0;
            perf_descriptor_cycles = 0;
            perf_row_cycles = 0;
            perf_clear_cycles = 0;
            perf_row_pick_cycles = 0;
            perf_mac_cycles = 0;
            perf_divide_cycles = 0;
            perf_next_cycles = 0;
        end
    endtask

    task run_case;
        input integer profile;
        input integer children;
        input integer rows_per_child;
        input integer first_latency;
        input integer beat_gap;
        integer total_cycles;
        integer attributed_cycles;
        integer expected_bursts;
        integer expected_beats;
        integer memory_cycles;
        integer bytes_read;
        integer nodes_per_second;
        integer scalar_ops;
        real cycles_per_child;
        real memory_percent;
        real mac_percent;
        real useful_mac_per_cycle;
        real useful_ops_per_cycle;
        reg [31:0] status;
        begin
            read_latency_cfg = first_latency;
            beat_gap_cfg = beat_gap;
            prepare_descriptors(children, rows_per_child);
            reg_write(8'h88, 2);
            clear_perf_counters;
            reg_write(8'h90, children);
            reg_write(8'h88, 1);
            wait_done(status);
            if (status[2]) begin
                $display("status=%08x", status);
                fail("performance case reported an error");
            end

            reg_rd_addr = 8'hac;
            #1;
            total_cycles = reg_rd_data;
            attributed_cycles = perf_preload_cycles +
                perf_descriptor_cycles + perf_row_cycles +
                perf_clear_cycles + perf_row_pick_cycles +
                perf_mac_cycles + perf_divide_cycles + perf_next_cycles;
            expected_bursts = 40 + children * (1 + 4 * rows_per_child);
            expected_beats = 320 + children * (8 + 32 * rows_per_child);
            if (total_cycles != attributed_cycles) begin
                $display("cycles=%0d attributed=%0d", total_cycles,
                         attributed_cycles);
                fail("state attribution does not equal CYCLES");
            end
            if (burst_count != expected_bursts) begin
                $display("bursts=%0d expected=%0d", burst_count,
                         expected_bursts);
                fail("unexpected DDR burst count");
            end
            if (beat_count != expected_beats) begin
                $display("beats=%0d expected=%0d", beat_count,
                         expected_beats);
                fail("unexpected DDR beat count");
            end
            if (perf_mac_cycles != children * 128)
                fail("unexpected MAC cycle count");
            if (perf_clear_cycles != children * 128)
                fail("unexpected clear cycle count");
            if (perf_divide_cycles != children * 65)
                fail("unexpected divide cycle count");

            memory_cycles = perf_preload_cycles +
                perf_descriptor_cycles + perf_row_cycles;
            bytes_read = beat_count * 4;
            nodes_per_second = (49500000 * children) / total_cycles;
            scalar_ops = children * 128 * (rows_per_child + 2);
            cycles_per_child = $itor(total_cycles) / $itor(children);
            memory_percent = 100.0 * $itor(memory_cycles) /
                $itor(total_cycles);
            mac_percent = 100.0 * $itor(perf_mac_cycles) /
                $itor(total_cycles);
            useful_mac_per_cycle = $itor(children * 256) /
                $itor(total_cycles);
            useful_ops_per_cycle = $itor(scalar_ops) /
                $itor(total_cycles);

            case (profile)
                0: $write("XQ_PERF profile=zero_wait");
                1: $write("XQ_PERF profile=latency4");
                2: $write("XQ_PERF profile=contended");
                default: $write("XQ_PERF profile=unknown");
            endcase
            $display(" children=%0d rows=%0d latency=%0d gap=%0d cycles=%0d cycles_per_child=%0.2f bytes=%0d bursts=%0d preload=%0d descriptor=%0d row_ddr=%0d clear=%0d mac=%0d divide=%0d control=%0d memory_pct=%0.2f mac_pct=%0.2f nodes_s_49m5=%0d useful_mac_per_cycle=%0.4f useful_ops_per_cycle=%0.4f",
                children, rows_per_child, first_latency, beat_gap,
                total_cycles, cycles_per_child, bytes_read, burst_count,
                perf_preload_cycles, perf_descriptor_cycles,
                perf_row_cycles, perf_clear_cycles, perf_mac_cycles,
                perf_divide_cycles,
                perf_row_pick_cycles + perf_next_cycles,
                memory_percent, mac_percent, nodes_per_second,
                useful_mac_per_cycle, useful_ops_per_cycle);
        end
    endtask

    integer i;
    integer row;
    integer word_index;
    initial begin
        repeat (1000000) @(posedge clk);
        fail("global timeout");
    end

    initial begin
        for (i = 0; i < WORDS; i = i + 1)
            memory[i] = 0;
        for (row = 0; row < MODEL_ROWS; row = row + 1)
            for (word_index = 0; word_index < 32;
                 word_index = word_index + 1)
                memory[((MODEL_BASE - DDR_BASE) >> 2) + row * 32 +
                       word_index] = 32'h01ff_02fe ^ row ^ word_index;
        for (i = 0; i < 256; i = i + 1)
            memory[((PARENT_BASE - DDR_BASE) >> 2) + i] =
                32'd3200 + i * 3;
        for (i = 0; i < 64; i = i + 1)
            memory[((WEIGHT_BASE - DDR_BASE) >> 2) + i] =
                32'h01ff_02fe ^ i;

        repeat (4) @(posedge clk);
        resetn = 1;
        reg_write(8'h94, MODEL_BASE);
        reg_write(8'h98, PARENT_BASE);
        reg_write(8'h9c, WEIGHT_BASE);
        reg_write(8'ha0, DESC_BASE);
        reg_write(8'ha4, 0);
        reg_write(8'ha8, 0);

        $display("XQ_PERF_NOTE synthetic_memory_model=1 clock_hz=49500000");
        $display("XQ_PERF_SWEEP batch_scaling rows=6 profile=zero_wait");
        run_case(0, 1, 6, 0, 0);
        run_case(0, 2, 6, 0, 0);
        run_case(0, 4, 6, 0, 0);
        run_case(0, 8, 6, 0, 0);
        run_case(0, 16, 6, 0, 0);

        $display("XQ_PERF_SWEEP row_sparsity children=16 profile=zero_wait");
        run_case(0, 16, 0, 0, 0);
        run_case(0, 16, 2, 0, 0);
        run_case(0, 16, 4, 0, 0);

        $display("XQ_PERF_SWEEP memory_latency children=16 rows=6");
        run_case(1, 16, 6, 4, 0);
        run_case(2, 16, 6, 12, 2);

        $display("XIANGQI_SPARSE_PERF_PASS cases=10");
        $finish;
    end
endmodule
