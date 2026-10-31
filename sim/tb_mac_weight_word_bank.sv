`timescale 1ns/1ps
// Independent word-index scoreboard, including synchronous read/hold/reset
// semantics. Legacy wide writes are checked on a separate default instance.
module tb_mac_weight_word_bank;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    reg word_we=0, wide_we=0, re=0;
    reg [31:0] wa=0, ra=0, wd=0;
    reg [4:0] wi=0;
    reg [1023:0] wide_data=0;
    wire [1023:0] q, legacy_q;
    reg [1023:0] gold [0:63];
    reg [1023:0] held=0;
    integer line, word_no, round_no, checks=0;
    Bank1R1W_1_compact #(.WORD_WRITE(1)) dut(
        .io_clk(clk), .io_rstN(resetn), .io_we(wide_we),
        .io_waddr(wa), .io_wdata(wide_data), .io_wordWe(word_we),
        .io_wordIndex(wi), .io_wordData(wd), .io_re(re),
        .io_raddr(ra), .io_rdata(q));
    Bank1R1W_1_compact legacy(
        .io_clk(clk), .io_rstN(resetn), .io_we(wide_we),
        .io_waddr(wa), .io_wdata(wide_data), .io_wordWe(1'b0),
        .io_wordIndex(5'b0), .io_wordData(32'b0), .io_re(re),
        .io_raddr(ra), .io_rdata(legacy_q));
    task read_check(input integer addr);
        begin
            @(negedge clk); re=1; ra=addr;
            @(posedge clk); #1;
            if(q!==gold[addr%64]) $fatal(1,"word bank mismatch addr=%0d",addr);
            held=q; checks=checks+1;
            @(negedge clk); re=0; ra=addr+1;
            @(posedge clk); #1;
            if(q!==held) $fatal(1,"read enable did not hold output");
        end
    endtask
    initial begin
        repeat(3) @(negedge clk); resetn=1;
        // Full overwrites, shuffled word order, gaps and successive jobs.
        for(round_no=0;round_no<2;round_no=round_no+1) begin
            for(line=0;line<64;line=line+1) begin
                for(word_no=0;word_no<32;word_no=word_no+1) begin
                    @(negedge clk); wa=line; wi=(word_no*13+7)%32;
                    wd=32'hfedcba98 ^ (line*32'h1020101) ^ (wi*32'h1234567) ^ round_no;
                    word_we=1; gold[line][wi*32+:32]=wd;
                    if(word_no%5==0) begin @(negedge clk); word_we=0; end
                end
                @(negedge clk); word_we=0;
                read_check(line);
            end
            // Invalid full-width write addresses must not alias line zero.
            @(negedge clk); word_we=1; wa=64; wi=0; wd=0;
            @(negedge clk); wa=32'h80000000;
            @(negedge clk); word_we=0;
            read_check(0); read_check(127);
        end
        // Same-address read/write observes the old word, as the wide bank did.
        @(negedge clk); wa=9; ra=9; wi=17; wd=32'h13579bdf; word_we=1; re=1;
        @(posedge clk); #1;
        if(q!==gold[9]) $fatal(1,"read-during-write changed");
        gold[9][17*32+:32]=wd;
        @(negedge clk); word_we=0; re=0;
        read_check(9);
        // Async output reset must preserve the weight memory.
        @(negedge clk); resetn=0; #1;
        if(q!==1024'b0 || legacy_q!==1024'b0) $fatal(1,"reset output");
        @(negedge clk); resetn=1;
        read_check(9);
        @(negedge clk); wide_we=1; wa=63; wide_data={32{32'hcafe8765}};
        @(negedge clk); wide_we=0; re=1; ra=63;
        @(posedge clk); #1;
        if(legacy_q!==wide_data) $fatal(1,"legacy wide write changed");
        if(q!==gold[63]) $fatal(1,"word profile accepted wide write");
        $display("MAC_WEIGHT_WORD_BANK_PASS checks=%0d words=4096 legacy=pass",checks);
        $finish;
    end
    initial begin #1000000; $fatal(1,"timeout"); end
endmodule
