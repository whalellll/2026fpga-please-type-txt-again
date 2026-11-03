`timescale 1ns/1ps
// Frozen, pre-change core is the differential oracle. Check every output,
// its address, and the exact cycle reduction for the output-lane pipeline.
module tb_mac_post_pipeline;
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
    MacAccelCore #(.COMPACT_S16_OUTPUT(1)) candidate(
        .io_clk(clk),.io_rstN(resetn),.io_start(start),.io_doneClear(clear),
        .io_busy(busy_c),.io_done(done_c),.io_cfgPixels(np),.io_cfgCin(nk),
        .io_cfgCout(nc),.io_cfgComputeMode(mode),.io_cfgActivation(activation),
        .io_cfgOutputFormat(format),.io_cfgOutShift(shift),
        .io_hostInWe(in_we),.io_hostInWaddr(in_addr),.io_hostInWdata(in_data),
        .io_hostWtWe(wt_we),.io_hostWtWaddr(wt_addr),.io_hostWtWdata(wt_data),
        .io_hostBiasWe(bias_we),.io_hostBiasWaddr(bias_addr),.io_hostBiasWdata(bias_data),
        .io_hostOutRe(out_re),.io_hostOutRaddr(out_addr),.io_hostOutRdata(data_c));
    BaselineMacAccelCore #(.COMPACT_S16_OUTPUT(1)) reference_core(
        .io_clk(clk),.io_rstN(resetn),.io_start(start),.io_doneClear(clear),
        .io_busy(busy_b),.io_done(done_b),.io_cfgPixels(np),.io_cfgCin(nk),
        .io_cfgCout(nc),.io_cfgComputeMode(mode),.io_cfgActivation(activation),
        .io_cfgOutputFormat(format),.io_cfgOutShift(shift),
        .io_hostInWe(in_we),.io_hostInWaddr(in_addr),.io_hostInWdata(in_data),
        .io_hostWtWe(wt_we),.io_hostWtWaddr(wt_addr),.io_hostWtWdata(wt_data),
        .io_hostBiasWe(bias_we),.io_hostBiasWaddr(bias_addr),.io_hostBiasWdata(bias_data),
        .io_hostOutRe(out_re),.io_hostOutRaddr(out_addr),.io_hostOutRdata(data_b));
    integer id,p,ci,co,t,l,ct,kt,step,cycles_c,cycles_b,gain;
    integer writes_c,writes_b,words=0,total_c=0,total_b=0;
    integer seed=32'h72ac0481;
    reg measuring=0;
    reg [8191:0] seen_c,seen_b;
    reg [47:0] bv;
    always @(posedge clk) if(resetn && measuring) begin
        if(candidate.engine_io_outWe) begin
            if(candidate.engine_io_outWaddr>=4096 || seen_c[candidate.engine_io_outWaddr])
                $fatal(1,"candidate duplicate/out-of-range write");
            seen_c[candidate.engine_io_outWaddr]=1;
            writes_c=writes_c+1;
        end
        if(reference_core.engine_io_outWe) begin
            if(reference_core.engine_io_outWaddr>=4096 || seen_b[reference_core.engine_io_outWaddr])
                $fatal(1,"reference duplicate/out-of-range write");
            seen_b[reference_core.engine_io_outWaddr]=1;
            writes_b=writes_b+1;
        end
    end
    initial begin
        repeat(4) @(negedge clk);resetn=1;
        for(id=0;id<64;id=id+1) begin
            mode=id%4;activation=(id/4)%4;format=(id/16)%4;
            case((id/4)%4) 0:np=1;1:np=3;2:np=16;3:np=2;endcase
            case(id%5) 0:nc=1;1:nc=17;2:nc=32;3:nc=57;4:nc=256;endcase
            case((id/3)%5) 0:nk=1;1:nk=4;2:nk=5;3:nk=17;4:nk=256;endcase
            case(id%10) 0:shift=0;1:shift=1;2:shift=7;3:shift=30;4:shift=31;
                5:shift=47;6:shift=63;7:shift=64;8:shift=127;9:shift=255;endcase
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
                @(negedge clk);wt_we=0;bias_we=1;bias_addr=t;
                for(l=0;l<32;l=l+1) begin
                    bv={$random(seed),16'($random(seed))};
                    bias_data[l*48+:48]=bv;
                end
                @(negedge clk);bias_we=0;
            end
            @(negedge clk);clear=1;
            @(negedge clk);clear=0;start=1;seen_c=0;seen_b=0;
            writes_c=0;writes_b=0;measuring=1;
            @(negedge clk);start=0;cycles_c=0;cycles_b=0;
            while(!done_c || !done_b) begin
                if(!done_c) cycles_c=cycles_c+1;
                if(!done_b) cycles_b=cycles_b+1;
                if(cycles_b>100000) $fatal(1,"core timeout id=%0d",id);
                @(negedge clk);
            end
            repeat(3) @(negedge clk);measuring=0;
            gain=np*(nc-ct);
            if(cycles_b-cycles_c!=gain)
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
            $display("MAC_POST_PIPELINE_CASE_PASS id=%0d mode=%0d activation=%0d format=%0d shift=%0d p=%0d k=%0d co=%0d candidate=%0d reference=%0d saved=%0d",id,mode,activation,format,shift,np,nk,nc,cycles_c,cycles_b,gain);
        end
        $display("MAC_POST_PIPELINE_PASS cases=64 words=%0d candidate=%0d reference=%0d",words,total_c,total_b);
        $finish;
    end
endmodule
