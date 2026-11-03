`timescale 1ns/1ps

module tb_pff1_stagea_gather;
    localparam [31:0] SCRATCH = 32'h1b00_0000;
    localparam [31:0] THREAT = 32'h1000_2000;
    localparam [31:0] PSQ = 32'h12f4_5000;
    localparam [31:0] DESC = SCRATCH + 32'h100;
    localparam [31:0] BASE = SCRATCH + 32'h1000;
    localparam [31:0] OUT = SCRATCH + 32'h2000;
    reg clk = 0;
    always #5 clk = ~clk;
    reg resetn = 0;
    reg reg_wr_en = 0;
    reg [7:0] reg_wr_addr = 0;
    reg [31:0] reg_wr_data = 0;
    reg [3:0] reg_wr_strb = 4'hf;
    reg [7:0] reg_rd_addr = 0;
    wire [31:0] reg_rd_data;
    wire mem_req_valid, mem_req_write;
    wire [31:0] mem_req_addr;
    wire [2:0] mem_req_len;
    wire mem_req_ready;
    wire mem_w_valid, mem_w_last;
    wire [31:0] mem_w_data;
    wire [3:0] mem_w_strb;
    wire mem_w_ready;
    wire mem_rsp_valid, mem_rsp_last, mem_rsp_error;
    wire [31:0] mem_rsp_rdata;
    wire mem_rsp_ready;

    pff1_stagea_gather dut (
        .clk(clk), .resetn(resetn), .reg_wr_en(reg_wr_en),
        .reg_wr_addr(reg_wr_addr), .reg_wr_data(reg_wr_data),
        .reg_wr_strb(reg_wr_strb), .reg_rd_addr(reg_rd_addr),
        .reg_rd_data(reg_rd_data), .mem_req_valid(mem_req_valid),
        .mem_req_ready(mem_req_ready), .mem_req_write(mem_req_write),
        .mem_req_addr(mem_req_addr), .mem_req_len(mem_req_len),
        .mem_w_valid(mem_w_valid), .mem_w_ready(mem_w_ready),
        .mem_w_data(mem_w_data), .mem_w_strb(mem_w_strb),
        .mem_w_last(mem_w_last), .mem_rsp_valid(mem_rsp_valid),
        .mem_rsp_ready(mem_rsp_ready), .mem_rsp_rdata(mem_rsp_rdata),
        .mem_rsp_last(mem_rsp_last), .mem_rsp_error(mem_rsp_error)
    );

    reg [31:0] scratch [0:262143];
    reg [1:0] bus_state = 0;
    reg [31:0] bus_addr = 0;
    reg [3:0] bus_beats = 0;
    reg [3:0] bus_index = 0;
    assign mem_req_ready = bus_state == 0;
    assign mem_w_ready = bus_state == 2;
    assign mem_rsp_valid = bus_state == 1 || bus_state == 3;
    assign mem_rsp_last = bus_state == 3 || bus_index + 4'd1 == bus_beats;
    assign mem_rsp_error = 0;

    // Former feature_byte function as a task; the four byte lanes used by
    // mem_rsp_rdata are precomputed combinationally from read_address.
    reg [7:0] feature_byte_result;
    task feature_byte;
        input [31:0] address;
        integer row, lane;
        begin
            if (address >= THREAT && address < THREAT + 32'd46640128) begin
                row = (address - THREAT) / 1024;
                lane = (address - THREAT) % 1024;
                feature_byte_result = (row == 0 ? ((lane % 17) - 8) : ((lane % 7) - 3));
            end else if (address >= PSQ && address < PSQ + 32'd16932864) begin
                lane = (address - PSQ) % 1024;
                feature_byte_result = (lane % 9) - 4;
            end else feature_byte_result = 8'hxx;
        end
    endtask
    reg [7:0] fb3, fb2, fb1, fb0;
    always @* begin
        feature_byte(read_address + 32'd3); fb3 = feature_byte_result;
        feature_byte(read_address + 32'd2); fb2 = feature_byte_result;
        feature_byte(read_address + 32'd1); fb1 = feature_byte_result;
        feature_byte(read_address);         fb0 = feature_byte_result;
    end

    wire [31:0] read_address=bus_addr+{26'b0,bus_index,2'b0};
    // Keep the mutable RAM in the expression's sensitivity. A function
    // hiding scratch can retain stale data when a retry uses the same address.
    assign mem_rsp_rdata = bus_state != 1 ? 32'b0 :
        (read_address >= SCRATCH && read_address < SCRATCH + 32'h100000) ?
        scratch[(read_address-SCRATCH)>>2] :
        {fb3, fb2, fb1, fb0};

    always @(posedge clk) begin
        if (!resetn) begin
            bus_state <= 0;
            bus_index <= 0;
        end else case (bus_state)
            0: if (mem_req_valid && mem_req_ready) begin
                bus_addr <= mem_req_addr;
                bus_beats <= {1'b0, mem_req_len} + 4'd1;
                bus_index <= 0;
                bus_state <= mem_req_write ? 2 : 1;
            end
            1: if (mem_rsp_ready) begin
                if (bus_index + 4'd1 == bus_beats) bus_state <= 0;
                else bus_index <= bus_index + 4'd1;
            end
            2: if (mem_w_valid && mem_w_ready) begin
                if (mem_w_strb != 4'hf) $fatal(1, "write strobe");
                scratch[(bus_addr - SCRATCH) / 4 + bus_index] <= mem_w_data;
                if (mem_w_last != (bus_index + 4'd1 == bus_beats))
                    $fatal(1, "write last");
                if (mem_w_last) bus_state <= 3;
                else bus_index <= bus_index + 4'd1;
            end
            3: if (mem_rsp_ready) bus_state <= 0;
        endcase
    end

    task automatic wr(input [7:0] address, input [31:0] value);
        begin
            @(negedge clk);
            reg_wr_en = 1;
            reg_wr_addr = address;
            reg_wr_data = value;
            @(negedge clk);
            reg_wr_en = 0;
        end
    endtask

    task automatic wait_done;
        integer ticks;
        begin
            reg_rd_addr = 8'h0c;
            ticks = 0;
            while (!reg_rd_data[1] && ticks < 100000) begin
                @(negedge clk);
                ticks = ticks + 1;
            end
            if (!reg_rd_data[1]) $fatal(1, "timeout");
        end
    endtask

    integer lane, got, expected, base_value;
    initial begin
        repeat (4) @(negedge clk);
        resetn = 1;
        scratch[(DESC - SCRATCH) / 4] = 32'h0000_0000; // + threat row 0
        scratch[(DESC - SCRATCH) / 4 + 1] = 32'h8000_0001; // - threat row 1
        scratch[(DESC - SCRATCH) / 4 + 2] = 32'h4000_0000; // + PSQ row 0
        for (lane = 0; lane < 1024; lane = lane + 1) begin
            base_value = (lane * 101 + 32700) & 16'hffff;
            if (!(lane & 1)) scratch[(BASE - SCRATCH) / 4 + lane / 2] = base_value;
            else scratch[(BASE - SCRATCH) / 4 + lane / 2] =
                scratch[(BASE - SCRATCH) / 4 + lane / 2] | (base_value << 16);
            scratch[(OUT - SCRATCH) / 4 + lane / 2] = 32'ha5a5_a5a5;
        end
        wr(8'h10, BASE);
        wr(8'h14, DESC);
        wr(8'h18, OUT);
        wr(8'h1c, 3);
        wr(8'h08, 1);
        wait_done();
        if (reg_rd_data[2]) $fatal(1, "unexpected error status=%h", reg_rd_data);
        for (lane = 0; lane < 1024; lane = lane + 1) begin
            got = (scratch[(OUT - SCRATCH) / 4 + lane / 2] >> ((lane & 1) * 16)) & 16'hffff;
            expected = ((lane * 101 + 32700) + ((lane % 17) - 8)
                        - ((lane % 7) - 3) + ((lane % 9) - 4)) & 16'hffff;
            if (got !== expected)
                $fatal(1, "lane=%d got=%h expected=%h", lane, got, expected);
        end
        $display("PFF1_STAGEA_GATHER_PASS lanes=1024 terms=3 cycles=%d", dut.cycle_count);

        wr(8'h08, 2); // clear done
        scratch[(DESC - SCRATCH) / 4] = 32'h0000_b1ec; // row 45548 exceeds 45547
        for (lane = 0; lane < 512; lane = lane + 1)
            scratch[(OUT - SCRATCH) / 4 + lane] = 32'hcafe_babe;
        wr(8'h1c, 1);
        wr(8'h08, 1);
        wait_done();
        if (!reg_rd_data[2]) $fatal(1, "row bound not rejected");
        if (bus_state !== 0 || mem_req_valid !== 0)
            $fatal(1, "invalid row left an outstanding DDR read");
        for (lane = 0; lane < 512; lane = lane + 1)
            if (scratch[(OUT - SCRATCH) / 4 + lane] !== 32'hcafe_babe)
                $fatal(1, "output canary damaged at word %d", lane);
        $display("PFF1_STAGEA_BOUNDS_PASS");

        wr(8'h08, 2);
        wr(8'h1c, 32'd1025); // High bits must not wrap to a legal count.
        wr(8'h08, 1);
        wait_done();
        if (!reg_rd_data[2] || reg_rd_data[11:8] != 1)
            $fatal(1, "term count truncation accepted");
        wr(8'h08, 2);
        wr(8'h1c, 1);
        scratch[(DESC - SCRATCH) / 4] = 32'h0000_0000;
        wr(8'h18, SCRATCH + 32'hff800); // 2 KiB output would reach limit exactly.
        wr(8'h08, 1);
        wait_done();
        if (reg_rd_data[2]) $fatal(1, "legal final output page rejected");
        wr(8'h08, 2);
        wr(8'h18, SCRATCH + 32'hff804); // 4 bytes past scratch limit.
        wr(8'h08, 1);
        wait_done();
        if (!reg_rd_data[2] || reg_rd_data[11:8] != 2)
            $fatal(1, "scratch output overflow accepted");
        $display("PFF1_STAGEA_CONFIG_PASS");
        $finish;
    end
endmodule
