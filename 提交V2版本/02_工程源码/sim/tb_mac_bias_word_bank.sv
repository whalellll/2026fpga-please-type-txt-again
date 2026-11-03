`timescale 1ns/1ps

module tb_mac_bias_word_bank;
    reg clk = 0;
    always #5 clk = ~clk;

    reg resetn = 0;
    reg word_we = 0;
    reg zero_we = 0;
    reg full_we = 0;
    reg [31:0] waddr = 0;
    reg [5:0] word_index = 0;
    reg [31:0] word_data = 0;
    reg [1535:0] full_data = 0;
    reg re = 0;
    reg [31:0] raddr = 0;
    wire [1535:0] word_result;
    wire [1535:0] full_result;

    MacBiasWordBank candidate (
        .io_clk(clk), .io_rstN(resetn),
        .io_wordWe(word_we), .io_zeroWe(zero_we),
        .io_waddr(waddr), .io_wordIndex(word_index),
        .io_wordData(word_data), .io_re(re), .io_raddr(raddr),
        .io_rdata(word_result)
    );
    Bank1R1W_2 reference_bank (
        .io_clk(clk), .io_rstN(resetn),
        .io_we(full_we), .io_waddr(waddr), .io_wdata(full_data),
        .io_re(re), .io_raddr(raddr), .io_rdata(full_result)
    );

    task check_line(input integer line);
        begin
            @(negedge clk);
            re = 1;
            raddr = line;
            @(posedge clk);
            #1;
            if (word_result !== full_result)
                $fatal(1, "bias line mismatch line=%0d candidate=%h expected=%h",
                       line, word_result, full_result);
            @(negedge clk);
            re = 0;
            raddr = line ^ 15;
            @(posedge clk);
            #1;
            if (word_result !== full_result)
                $fatal(1, "disabled read changed output line=%0d", line);
        end
    endtask

    integer line;
    integer word;
    reg [1535:0] assembled;
    reg [31:0] payload;
    initial begin
        repeat (3) @(negedge clk);
        resetn = 1;
        for (line = 0; line < 16; line = line + 1) begin
            assembled = 0;
            for (word = 0; word < 48; word = word + 1) begin
                payload = 32'h5a730001 ^ (line * 32'h10201) ^
                          (word * 32'h0103070b);
                assembled[word*32 +: 32] = payload;
                @(negedge clk);
                waddr = line;
                word_index = word;
                word_data = payload;
                word_we = 1;
            end
            @(negedge clk);
            word_we = 0;
            full_we = 1;
            waddr = line;
            full_data = assembled;
            @(negedge clk);
            full_we = 0;
        end

        for (line = 0; line < 16; line = line + 1)
            check_line(line);

        // The Stage B zero-bias path must clear a whole tile in one cycle.
        for (line = 0; line < 16; line = line + 1) begin
            @(negedge clk);
            waddr = line;
            zero_we = 1;
            full_we = 1;
            full_data = 0;
            @(negedge clk);
            zero_we = 0;
            full_we = 0;
            check_line(line);
        end

        $display("MAC_BIAS_WORD_BANK_PASS lines=16 words_per_line=48 zero_cycles=1");
        $finish;
    end
endmodule
