`timescale 1ns/1ps
// Compare the compact DMA bank against the legacy standalone core layout.
module tb_mac_half_s16_golden #(parameter OUTPUT_PROFILE=1);
    reg clk=0, resetn=0, start=0, clear=0;
    always #5 clk=~clk;
    reg [15:0] pixels=16, cout=256;
    reg [1:0] activation=0;
    reg in_we=0, wt_we=0, bias_we=0, out_re=0;
    reg [31:0] in_addr=0, wt_addr=0, bias_addr=0, compact_addr=0, legacy_addr=0;
    reg [63:0] in_data=0;
    reg [1023:0] wt_data=0;
    wire busy_c, busy_l, done_c, done_l;
    wire [31:0] data_c, data_l;
    MacAccelCore #(.HALF_OUTPUT(OUTPUT_PROFILE),.COMPACT_S16_OUTPUT(1)) compact(
        .io_clk(clk), .io_rstN(resetn), .io_start(start), .io_doneClear(clear),
        .io_busy(busy_c), .io_done(done_c), .io_cfgPixels(pixels),
        .io_cfgCin(16'd4), .io_cfgCout(cout), .io_cfgComputeMode(2'd0),
        .io_cfgActivation(activation), .io_cfgOutputFormat(2'd3), .io_cfgOutShift(8'd0),
        .io_hostInWe(in_we), .io_hostInWaddr(in_addr), .io_hostInWdata(in_data),
        .io_hostWtWe(wt_we), .io_hostWtWaddr(wt_addr), .io_hostWtWdata(wt_data),
        .io_hostBiasWe(bias_we), .io_hostBiasWaddr(bias_addr), .io_hostBiasWdata(1536'd0),
        .io_hostOutRe(out_re), .io_hostOutRaddr(compact_addr), .io_hostOutRdata(data_c)
    );
    MacAccelCore #(.HALF_OUTPUT(OUTPUT_PROFILE)) legacy(
        .io_clk(clk), .io_rstN(resetn), .io_start(start), .io_doneClear(clear),
        .io_busy(busy_l), .io_done(done_l), .io_cfgPixels(pixels),
        .io_cfgCin(16'd4), .io_cfgCout(cout), .io_cfgComputeMode(2'd0),
        .io_cfgActivation(activation), .io_cfgOutputFormat(2'd3), .io_cfgOutShift(8'd0),
        .io_hostInWe(in_we), .io_hostInWaddr(in_addr), .io_hostInWdata(in_data),
        .io_hostWtWe(wt_we), .io_hostWtWaddr(wt_addr), .io_hostWtWdata(wt_data),
        .io_hostBiasWe(bias_we), .io_hostBiasWaddr(bias_addr), .io_hostBiasWdata(1536'd0),
        .io_hostOutRe(out_re), .io_hostOutRaddr(legacy_addr), .io_hostOutRdata(data_l)
    );
    integer p, co, tile, ci, lane, sample, cycles, total=0;
    integer expected, a;
    always @(posedge clk) if (resetn) begin
        if (busy_c!==busy_l || done_c!==done_l)
            $fatal(1,"compact layout changed compute cycles");
        if (compact.engine_io_outWe && compact.engine_io_outWaddr>=4096)
            $fatal(1,"compact bank write exceeded SRAM");
    end
    task run_case(input integer np, nc);
        begin
            pixels=np; cout=nc;
            for (p=0;p<np;p=p+1) begin
                @(negedge clk); in_we=1; in_addr=p;
                sample=p%2 ? -(p+1) : p+1;
                for (ci=0;ci<4;ci=ci+1) in_data[ci*16+:16]=sample;
            end
            @(negedge clk); in_we=0;
            for (tile=0;tile<(nc+15)/16;tile=tile+1) begin
                @(negedge clk); wt_we=1; bias_we=1; wt_addr=tile; bias_addr=tile;
                wt_data=0;
                for (lane=0;lane<16;lane=lane+1)
                    for (ci=0;ci<4;ci=ci+1)
                        wt_data[(lane*4+ci)*16+:16]=tile*16+lane+1;
            end
            @(negedge clk); wt_we=0; bias_we=0; clear=1;
            @(negedge clk); clear=0; start=1;
            @(negedge clk); start=0; cycles=0;
            while (!done_c && cycles<30000) begin @(negedge clk); cycles=cycles+1; end
            if (!done_c) $fatal(1,"compute timeout");
            repeat(3) @(negedge clk);
            for (p=0;p<np;p=p+1) for (co=0;co<nc;co=co+1) begin
                compact_addr=(p*((nc+15)/16)+co/16)*16+co%16;
                legacy_addr=(p*((nc+15)/16)+co/16)*32+co%16;
                out_re=1; @(negedge clk);
                expected=4*(p%2 ? -(p+1) : p+1)*(co+1);
                if(activation==3) begin
                    if(expected<0) expected=0;
                    if(expected>131071) expected=131071;
                    expected=(expected*expected)>>7;
                    if(expected>127) expected=127;
                end
                if ($signed(data_c)!==expected || data_c!==data_l)
                    $fatal(1,"layout mismatch p=%0d co=%0d compact=%h legacy=%h expected=%0d",p,co,data_c,data_l,expected);
                total=total+1;
            end
            out_re=0;
            $display("MAC_HALF_S16_GOLDEN_CASE_PASS p=%0d cout=%0d cycles=%0d",np,nc,cycles);
        end
    endtask
    initial begin
        #1;
        if ($size(compact.outputBank.memory)!=4096 || $size(legacy.outputBank.memory)!=8192)
            $fatal(1,"output bank depth mismatch compact=%0d legacy=%0d",$size(compact.outputBank.memory),$size(legacy.outputBank.memory));
        repeat(4) @(negedge clk); resetn=1;
        for(a=0;a<2;a=a+1) begin
            activation=a ? 3 : 0;
            run_case(16,256); run_case(3,17); run_case(2,9);
            run_case(2,8); run_case(2,7); run_case(2,1);
        end
        $display("MAC_HALF_S16_GOLDEN_PASS words=%0d compact_depth=4096 legacy_depth=8192",total);
        $finish;
    end
endmodule
