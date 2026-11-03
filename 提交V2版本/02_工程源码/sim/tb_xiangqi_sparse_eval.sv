`timescale 1ns/1ps

module tb_xiangqi_sparse_eval;
    localparam [31:0] DDR_BASE   = 32'h1000_0000;
    localparam [31:0] MODEL_BASE = 32'h1000_0000;
    localparam [31:0] PARENT_BASE= 32'h1000_1000;
    localparam [31:0] WEIGHT_BASE= 32'h1000_1400;
    localparam [31:0] DESC_BASE  = 32'h1000_1600;
    localparam integer MODEL_ROWS = 16;
    localparam integer WORDS = 16 * 1024;

    reg clk = 0;
    reg resetn = 0;
    always #5 clk = ~clk;

    reg reg_wr_en = 0;
    reg [7:0] reg_wr_addr = 0;
    reg [31:0] reg_wr_data = 0;
    reg [3:0] reg_wr_strb = 4'hf;
    reg [7:0] reg_rd_addr = 0;
    wire [31:0] reg_rd_data;

    wire mem_req_valid;
    wire mem_req_ready;
    wire mem_req_write;
    wire [31:0] mem_req_addr;
    wire [2:0] mem_req_len;
    wire mem_w_valid;
    wire mem_w_ready;
    wire [31:0] mem_w_data;
    wire [3:0] mem_w_strb;
    wire mem_w_last;
    reg mem_rsp_valid = 0;
    wire mem_rsp_ready;
    reg [31:0] mem_rsp_rdata = 0;
    reg mem_rsp_last = 0;
    reg mem_rsp_error = 0;
    wire irq;

    reg [31:0] memory [0:WORDS-1];
    reg rd_active = 0;
    reg [31:0] rd_addr = 0;
    reg [3:0] rd_beats_left = 0;

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

    always @(posedge clk) begin
        if (!resetn) begin
            rd_active <= 0;
            rd_addr <= 0;
            rd_beats_left <= 0;
            mem_rsp_valid <= 0;
            mem_rsp_rdata <= 0;
            mem_rsp_last <= 0;
            mem_rsp_error <= 0;
        end else begin
            if (mem_req_valid && mem_req_ready) begin
                if (mem_req_write)
                    $fatal(1, "FAIL sparse evaluator issued a write");
                rd_active <= 1;
                rd_addr <= mem_req_addr;
                rd_beats_left <= {1'b0, mem_req_len} + 4'd1;
            end
            if (rd_active && !mem_rsp_valid) begin
                mem_rsp_valid <= 1;
                mem_rsp_rdata <= memory[(rd_addr - DDR_BASE) >> 2];
                mem_rsp_last <= (rd_beats_left == 1);
                mem_rsp_error <= (rd_addr < DDR_BASE) ||
                    (rd_addr >= DDR_BASE + 64 * 1024);
            end else if (mem_rsp_valid && mem_rsp_ready) begin
                mem_rsp_valid <= 0;
                if (mem_rsp_last) begin
                    rd_active <= 0;
                end else begin
                    rd_addr <= rd_addr + 4;
                    rd_beats_left <= rd_beats_left - 1;
                end
            end
        end
    end

    task fail;
        input [511:0] why;
        begin
            $fatal(1, "FAIL tb_xiangqi_sparse_eval: %0s", why);
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
            while (!reg_rd_data[1] && timeout < 100000) begin
                @(posedge clk);
                #1;
                timeout = timeout + 1;
            end
            if (timeout == 100000)
                fail("completion timeout");
            status = reg_rd_data;
        end
    endtask

    task row_value;
        input integer row;
        input integer lane;
        output integer value;
        begin
            value = ((row * 3 + lane * 5 + 2) % 15) - 7;
        end
    endtask

    task reg_write_masked;
        input [7:0] address;
        input [31:0] value;
        input [3:0] strobe;
        begin
            @(negedge clk);
            reg_wr_addr = address;
            reg_wr_data = value;
            reg_wr_strb = strobe;
            reg_wr_en = 1;
            @(posedge clk);
            #1;
            @(negedge clk);
            reg_wr_en = 0;
            reg_wr_strb = 4'hf;
        end
    endtask

    task weight_value;
        input integer bank;
        input integer lane;
        output integer value;
        begin
            if (bank == 0)
                value = ((lane * 2 + 1) % 9) - 4;
            else
                value = ((lane * 3 + 2) % 11) - 5;
        end
    endtask

    task parent_value;
        input integer bank;
        input integer lane;
        output integer value;
        begin
            if (bank == 0)
                value = 4200 + ((lane % 13) - 6) * 510;
            else
                value = 3600 + ((lane % 9) - 4) * 630;
        end
    endtask

    task memory_byte;
        input integer row;
        input integer lane;
        output integer value;
        reg [31:0] word_value;
        reg [7:0] byte_value;
        begin
            word_value = memory[((MODEL_BASE - DDR_BASE) +
                                 row * 128 + (lane / 4) * 4) >> 2];
            case (lane % 4)
                0: byte_value = word_value[7:0];
                1: byte_value = word_value[15:8];
                2: byte_value = word_value[23:16];
                default: byte_value = word_value[31:24];
            endcase
            value = byte_value[7] ? byte_value - 256 : byte_value;
        end
    endtask

    task calculate_reference;
        input integer child;
        output integer score;
        integer lane;
        integer signed dr, db, hr, hb, wr, wb;
        integer signed sample;
        reg side;
        reg [31:0] desc [0:7];
        reg signed [63:0] sum;
        reg signed [63:0] num;
        begin
            for (lane = 0; lane < 8; lane = lane + 1)
                desc[lane] = memory[((DESC_BASE - DDR_BASE) >> 2) +
                                    child * 8 + lane];
            side = desc[0][0];
            sum = 0;
            for (lane = 0; lane < 128; lane = lane + 1) begin
                dr = 0;
                db = 0;
                if (desc[1] != 32'hffff_ffff) begin
                    memory_byte(desc[1], lane, sample);
                    dr = dr - sample;
                end
                if (desc[2] != 32'hffff_ffff) begin
                    memory_byte(desc[2], lane, sample);
                    dr = dr + sample;
                end
                if (desc[3] != 32'hffff_ffff) begin
                    memory_byte(desc[3], lane, sample);
                    dr = dr - sample;
                end
                if (desc[4] != 32'hffff_ffff) begin
                    memory_byte(desc[4], lane, sample);
                    db = db - sample;
                end
                if (desc[5] != 32'hffff_ffff) begin
                    memory_byte(desc[5], lane, sample);
                    db = db + sample;
                end
                if (desc[6] != 32'hffff_ffff) begin
                    memory_byte(desc[6], lane, sample);
                    db = db - sample;
                end
                parent_value(0, lane, hr);
                hr = hr + 627 * dr;
                parent_value(1, lane, hb);
                hb = hb + 627 * db;
                weight_value(side ? 1 : 0, lane, wr);
                weight_value(side ? 0 : 1, lane, wb);
                if (hr > 0)
                    sum = sum + hr * wr;
                if (hb > 0)
                    sum = sum + hb * wb;
            end
            num = -64'sd321987 + 64'sd1092 * sum;
            score = num / 64'sd66064384;
        end
    endtask

    integer i, row, word_index, child;
    integer signed v0, v1, v2, v3;
    integer expected [0:15];
    reg [31:0] status;
    reg [31:0] actual;
    initial begin
        repeat (100000) @(posedge clk);
        fail("global timeout");
    end

    initial begin
        for (i = 0; i < WORDS; i = i + 1)
            memory[i] = 0;

        for (row = 0; row < MODEL_ROWS; row = row + 1) begin
            for (word_index = 0; word_index < 32;
                 word_index = word_index + 1) begin
                row_value(row, word_index * 4, v0);
                row_value(row, word_index * 4 + 1, v1);
                row_value(row, word_index * 4 + 2, v2);
                row_value(row, word_index * 4 + 3, v3);
                memory[((MODEL_BASE - DDR_BASE) >> 2) + row * 32 +
                       word_index] = (v0 & 8'hff) |
                                    ((v1 & 8'hff) << 8) |
                                    ((v2 & 8'hff) << 16) |
                                    ((v3 & 8'hff) << 24);
            end
        end

        for (i = 0; i < 128; i = i + 1) begin
            parent_value(0, i, v0);
            memory[((PARENT_BASE - DDR_BASE) >> 2) + i] =
                v0;
            parent_value(1, i, v1);
            memory[((PARENT_BASE - DDR_BASE) >> 2) + 128 + i] =
                v1;
        end
        for (word_index = 0; word_index < 64;
             word_index = word_index + 1) begin
            weight_value((word_index * 4) / 128,
                         (word_index * 4) % 128, v0);
            weight_value((word_index * 4 + 1) / 128,
                         (word_index * 4 + 1) % 128, v1);
            weight_value((word_index * 4 + 2) / 128,
                         (word_index * 4 + 2) % 128, v2);
            weight_value((word_index * 4 + 3) / 128,
                         (word_index * 4 + 3) % 128, v3);
            memory[((WEIGHT_BASE - DDR_BASE) >> 2) + word_index] =
                (v0 & 8'hff) | ((v1 & 8'hff) << 8) |
                ((v2 & 8'hff) << 16) | ((v3 & 8'hff) << 24);
        end

        // Match the board stress program: all 16 result registers, alternating
        // sides, and a mixture of five- and six-row child updates.
        for (child = 0; child < 16; child = child + 1) begin
            memory[((DESC_BASE - DDR_BASE) >> 2) + child*8 + 0] =
                child & 1;
            memory[((DESC_BASE - DDR_BASE) >> 2) + child*8 + 1] =
                child % 12;
            memory[((DESC_BASE - DDR_BASE) >> 2) + child*8 + 2] =
                (child + 1) % 12;
            memory[((DESC_BASE - DDR_BASE) >> 2) + child*8 + 3] =
                (child % 3 == 0) ? (child + 2) % 12 : 32'hffff_ffff;
            memory[((DESC_BASE - DDR_BASE) >> 2) + child*8 + 4] =
                (child + 3) % 12;
            memory[((DESC_BASE - DDR_BASE) >> 2) + child*8 + 5] =
                (child + 4) % 12;
            memory[((DESC_BASE - DDR_BASE) >> 2) + child*8 + 6] =
                (child % 4 == 0) ? (child + 5) % 12 : 32'hffff_ffff;
            memory[((DESC_BASE - DDR_BASE) >> 2) + child*8 + 7] = 0;
            calculate_reference(child, expected[child]);
        end

        repeat (4) @(posedge clk);
        resetn = 1;
        reg_rd_addr = 8'h80;
        #1;
        if (reg_rd_data != 32'h5851_5345)
            fail("ID mismatch");
        reg_rd_addr = 8'h84;
        #1;
        if (reg_rd_data != 32'h0001_0000)
            fail("version mismatch");

        // Verify byte strobes after expanding the former merge helper into
        // fixed-index register assignments.  MODEL_BASE starts at 10000000.
        reg_write_masked(8'h94, 32'h1122_3344, 4'b0101);
        reg_rd_addr = 8'h94;
        #1;
        if (reg_rd_data != 32'h1022_0044)
            fail("masked configuration write mismatch");
        reg_write(8'h94, MODEL_BASE);

        // Exercise fail-fast configuration checking first.
        reg_write(8'h90, 0);
        reg_write(8'h88, 1);
        wait_done(status);
        if (!status[2] || status[19:16] != 1)
            fail("invalid child count was not rejected");
        reg_write(8'h88, 2);

        reg_write(8'h90, 16);
        reg_write(8'h94, MODEL_BASE);
        reg_write(8'h98, PARENT_BASE);
        reg_write(8'h9c, WEIGHT_BASE);
        reg_write(8'ha0, DESC_BASE);
        reg_write(8'ha4, -321987);
        reg_write(8'ha8, 32'hffff_ffff);
        reg_write(8'h88, 1);
        wait_done(status);
        if (status[2]) begin
            $display("status=%08x", status);
            fail("valid batch reported an error");
        end

        for (child = 0; child < 16; child = child + 1) begin
            reg_rd_addr = 8'hc0 + child*4;
            #1;
            actual = reg_rd_data;
            if ($signed(actual) != expected[child]) begin
                $display("child%0d actual=%0d expected=%0d", child,
                         $signed(actual), expected[child]);
                fail("child score mismatch");
            end
        end
        reg_rd_addr = 8'hac;
        #1;
        if (reg_rd_data == 0 || reg_rd_data > 25000)
            fail("cycle count outside expected budget");
        $display("XIANGQI_SPARSE_EVAL_PASS children=16 score0=%0d score15=%0d cycles=%0d",
                 expected[0], expected[15], reg_rd_data);
        $finish;
    end
endmodule
