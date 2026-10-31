`timescale 1ns/1ps
// Frozen current core is the oracle. Compare bank enables/addresses and output
// values every active cycle; exact latency must remain unchanged.
module tb_mac_half_output #(parameter OUTPUT_PROFILE=1);
`ifdef WORD_BIAS
    localparam WORD_BIAS = 1;
`else
    localparam WORD_BIAS = 0;
`endif
    reg word_we=0;
    reg [5:0] word_index=0;
    reg [31:0] word_data=0;
    integer bw,reset_case,wait_cycles,target;
    reg clk=0,resetn=0,start=0,clear=0;
    always #5 clk=~clk;
    reg [15:0] np,nk,nc;
    reg [1:0] mode,activation,format;
    reg [7:0] shift;
    reg in_we=0,wt_we=0,bias_we=0,out_re=0;
    reg [31:0] in_addr,wt_addr,bias_addr,out_addr;
    reg [63:0] in_data;
    reg [1023:0] wt_data;
    reg [1535:0] bias_data;
    wire busy_c,done_c,busy_b,done_b;
    wire [31:0] data_c,data_b;
    MacAccelCore #(.HALF_OUTPUT(OUTPUT_PROFILE),.COMPACT_S16_OUTPUT(1),.BIAS_WORD_WRITE(WORD_BIAS)) candidate(
        .io_clk(clk),.io_rstN(resetn),.io_start(start),.io_doneClear(clear),
        .io_busy(busy_c),.io_done(done_c),.io_cfgPixels(np),.io_cfgCin(nk),
        .io_cfgCout(nc),.io_cfgComputeMode(mode),.io_cfgActivation(activation),
        .io_cfgOutputFormat(format),.io_cfgOutShift(shift),
        .io_hostInWe(in_we),.io_hostInWaddr(in_addr),.io_hostInWdata(in_data),
        .io_hostWtWe(wt_we),.io_hostWtWaddr(wt_addr),.io_hostWtWdata(wt_data),
        .io_hostBiasWordWe(word_we),.io_hostBiasWordIndex(word_index),.io_hostBiasWordData(word_data),.io_hostBiasZeroWe(1'b0),
        .io_hostBiasWe(bias_we),.io_hostBiasWaddr(bias_addr),.io_hostBiasWdata(bias_data),
        .io_hostOutRe(out_re),.io_hostOutRaddr(out_addr),.io_hostOutRdata(data_c));
    BaselineMacAccelCore #(.COMPACT_S16_OUTPUT(1),.BIAS_WORD_WRITE(WORD_BIAS)) reference_core(
        .io_clk(clk),.io_rstN(resetn),.io_start(start),.io_doneClear(clear),
        .io_busy(busy_b),.io_done(done_b),.io_cfgPixels(np),.io_cfgCin(nk),
        .io_cfgCout(nc),.io_cfgComputeMode(mode),.io_cfgActivation(activation),
        .io_cfgOutputFormat(format),.io_cfgOutShift(shift),
        .io_hostInWe(in_we),.io_hostInWaddr(in_addr),.io_hostInWdata(in_data),
        .io_hostWtWe(wt_we),.io_hostWtWaddr(wt_addr),.io_hostWtWdata(wt_data),
        .io_hostBiasWordWe(word_we),.io_hostBiasWordIndex(word_index),.io_hostBiasWordData(word_data),.io_hostBiasZeroWe(1'b0),
        .io_hostBiasWe(bias_we),.io_hostBiasWaddr(bias_addr),.io_hostBiasWdata(bias_data),
        .io_hostOutRe(out_re),.io_hostOutRaddr(out_addr),.io_hostOutRdata(data_b));
    integer id,p,ci,co,t,l,ct,kt,step,cycles_c,cycles_b,gain;
    integer writes_c,writes_b,words=0,total_c=0,total_b=0;
    integer seed=32'h72ac0481;
    reg measuring=0;
    reg [8191:0] seen_c,seen_b;
    reg [47:0] bv;
    always @(posedge clk) if(resetn) begin
        if(OUTPUT_PROFILE==2 && busy_c && candidate.engine.state==6 &&
           candidate.engine.coutStepR!=(mode==0 ? 4 : 8))
            $fatal(1,"quarter output profile ignored");
        if(candidate.engine_io_outWe && (^candidate.engine_io_outWdata === 1'bx)) $fatal(1,"unknown output payload");
        if(candidate.engine_io_outWe && measuring) begin
            if(candidate.engine_io_outWaddr>=4096 || seen_c[candidate.engine_io_outWaddr])
                $fatal(1,"candidate duplicate/out-of-range write");
            seen_c[candidate.engine_io_outWaddr]=1;
            writes_c=writes_c+1;
        end
        if(reference_core.engine_io_outWe && measuring) begin
            if(reference_core.engine_io_outWaddr>=4096 || seen_b[reference_core.engine_io_outWaddr])
                $fatal(1,"reference duplicate/out-of-range write");
            seen_b[reference_core.engine_io_outWaddr]=1;
            writes_b=writes_b+1;
        end
    end
    initial begin
        repeat(4) @(negedge clk);resetn=1;
        for(id=0;id<65;id=id+1) begin
            mode=id%4;activation=(id/4)%4;format=(id/16)%4;
            // S16 square has a separate integer-golden test: the frozen core
            // interleaves post operands incorrectly in this mode.
            if(mode==0 && activation==3) activation=2;
            case((id/4)%4) 0:np=1;1:np=3;2:np=16;3:np=2;endcase
            case(id%5) 0:nc=1;1:nc=17;2:nc=32;3:nc=57;4:nc=256;endcase
            case((id/3)%5) 0:nk=1;1:nk=4;2:nk=5;3:nk=17;4:nk=256;endcase
            case(id%10) 0:shift=0;1:shift=1;2:shift=7;3:shift=30;4:shift=31;
                5:shift=47;6:shift=63;7:shift=64;8:shift=127;9:shift=255;endcase
            if(id==64) begin np=1;nk=256;nc=32;mode=2;activation=0;format=3;shift=0;end
            step=mode==0 ? 16:32;ct=(nc+step-1)/step;kt=(nk+3)/4;
            for(p=0;p<np;p=p+1) for(ci=0;ci<kt;ci=ci+1) begin
                @(negedge clk);in_we=1;in_addr=p*kt+ci;
                in_data={$random(seed),$random(seed)};
                if(mode!=0) for(l=0;l<4;l=l+1) in_data[l*16+8+:8]=0;
            end
            @(negedge clk);in_we=0;
            for(t=0;t<ct;t=t+1) begin
                for(ci=0;ci<kt;ci=ci+1) begin
                    @(negedge clk);wt_we=1;wt_addr=t*kt+ci;
                    for(l=0;l<32;l=l+1) wt_data[l*32+:32]=$random(seed);
                end
                @(negedge clk);wt_we=0;bias_we=!WORD_BIAS;bias_addr=t;
                for(l=0;l<32;l=l+1) begin
                    bv={$random(seed),16'($random(seed))};
                    bias_data[l*48+:48]=bv;
                end
                if(WORD_BIAS) begin
                    for(bw=0;bw<48;bw=bw+1) begin
                        word_we=1;word_index=bw;word_data=bias_data[bw*32+:32];
                        @(negedge clk);
                    end
                    word_we=0;
                end else @(negedge clk);
                bias_we=0;
            end
            @(negedge clk);clear=1;
            @(negedge clk);clear=0;start=1;seen_c=0;seen_b=0;
            writes_c=0;writes_b=0;measuring=1;
            @(negedge clk);start=0;cycles_c=0;cycles_b=0;
            while(!done_c || !done_b) begin
                if(!done_c) cycles_c=cycles_c+1;
                if(!done_b) cycles_b=cycles_b+1;
                if(cycles_c>100000 || cycles_b>100000) $fatal(1,"core timeout id=%0d",id);
                @(negedge clk);
            end
            repeat(3) @(negedge clk);measuring=0;
            gain=0;
            if(cycles_c<cycles_b)
                $fatal(1,"post pipeline cycle contract id=%0d candidate=%0d reference=%0d expected_gain=%0d",id,cycles_c,cycles_b,gain);
            if(writes_c!=np*nc || writes_b!=np*nc || seen_c!==seen_b)
                $fatal(1,"output address/count mismatch id=%0d",id);
            for(p=0;p<np;p=p+1) for(co=0;co<nc;co=co+1) begin
                out_addr=(p*ct+co/step)*step+co%step;out_re=1;
                @(negedge clk);
                if(data_c!==data_b)
                    $fatal(1,"output mismatch id=%0d mode=%0d act=%0d format=%0d shift=%0d p=%0d co=%0d got=%h expected=%h",id,mode,activation,format,shift,p,co,data_c,data_b);
                words=words+1;
            end
            out_re=0;total_c=total_c+cycles_c;total_b=total_b+cycles_b;
            $display("MAC_HALF_OUTPUT_CASE_PASS id=%0d mode=%0d activation=%0d format=%0d shift=%0d p=%0d k=%0d co=%0d candidate=%0d reference=%0d saved=%0d",id,mode,activation,format,shift,np,nk,nc,cycles_c,cycles_b,gain);
        end
        // Reset at every active phase, with a complete restart after each cut.
        np=2;nk=5;nc=17;mode=1;activation=3;format=0;shift=0;
        for(reset_case=0;reset_case<11;reset_case=reset_case+1) begin
            case(reset_case) 0:target=1;1:target=4;2:target=5;3:target=6;4:target=2;
                5:target=7;6:target=8;7:target=9;8:target=10;9:target=11;10:target=12;endcase
            @(negedge clk);resetn=0;start=0;clear=0;out_re=0;measuring=0;
            repeat(2) @(negedge clk);resetn=1;
            @(negedge clk);start=1;
            @(negedge clk);start=0;wait_cycles=0;
            while(candidate.engine.state!=target && wait_cycles<20000) begin @(negedge clk);wait_cycles=wait_cycles+1;end
            if(wait_cycles==20000) $fatal(1,"reset phase unreachable target=%0d",target);
            resetn=0;repeat(2) @(negedge clk);resetn=1;
            repeat(2) @(negedge clk);
            if({busy_c,done_c}!==2'b0 || {busy_b,done_b}!==2'b0) $fatal(1,"reset status mismatch");
            start=1;@(negedge clk);start=0;cycles_c=0;
            while(!done_c || !done_b) begin
                @(negedge clk);cycles_c=cycles_c+1;if(cycles_c>20000) $fatal(1,"reset restart timeout");
            end
        end
        $display("MAC_HALF_OUTPUT_PASS cases=65 reset_phases=11 words=%0d candidate=%0d reference=%0d",words,total_c,total_b);
        $finish;
    end
endmodule
