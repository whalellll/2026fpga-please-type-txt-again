`timescale 1ns/1ps
// Cycle/valid-payload equivalence through abort and reset in every core state.
module tb_mac_conv_restart;
    reg clk=0,resetn=0,start=0,abort=0;
    always #5 clk=~clk;
    reg tap_valid=0,out_ready=0;
    reg [31:0] tap_data;
    reg [2:0] tap_kx,tap_ky;
    reg [511:0] quant_bias;
    reg [79:0] quant_shift;
    reg weight_read_valid=0;
    reg [1023:0] weight_read_data;
    wire ready0,ready1,tap_ready0,tap_ready1,wreq0,wreq1;
    wire [4:0] waddr0,waddr1;
    wire valid0,valid1,last0,last1,done0,done1,error0,error1;
    wire [7:0] data0,data1;
    wire [31:0] cycles0,cycles1;
    integer tick=0,taps=0,outputs=0,checks=0,jobs=0,job=0,i,s,r;
    integer timeout,before_outputs;
    `define COMMON .clk(clk),.resetn(resetn),.start(start),.abort(abort), \
        .width(9'd6),.height(9'd6),.channels(16'd3),.output_channels(16'd16), \
        .kernel(3'd6),.stride(2'd1),.padding(3'd0),.weight_lines(6'd27), \
        .quant_bias(quant_bias),.quant_shift(quant_shift),.tap_valid(tap_valid), \
        .tap_data(tap_data),.tap_x(9'd0),.tap_y(9'd0),.tap_kx(tap_kx), \
        .tap_ky(tap_ky),.tap_tile(8'd0),.weight_read_valid(weight_read_valid), \
        .weight_read_data(weight_read_data),.out_ready(out_ready)
    BaselineConvCore reference(`COMMON,.start_ready(ready0),.tap_ready(tap_ready0),
        .weight_read_en(wreq0),.weight_read_addr(waddr0),.out_valid(valid0),
        .out_data(data0),.out_last(last0),.done(done0),.error(error0),.cycles(cycles0));
    mac_conv_compute_core dut(`COMMON,.start_ready(ready1),.tap_ready(tap_ready1),
        .weight_read_en(wreq1),.weight_read_addr(waddr1),.out_valid(valid1),
        .out_data(data1),.out_last(last1),.done(done1),.error(error1),.cycles(cycles1));
    `undef COMMON
    always @(posedge clk) begin
        tick<=tick+1;
        weight_read_valid<=resetn && !abort && wreq0;
        if(wreq0) for(integer b=0;b<128;b=b+1)
            weight_read_data[b*8+:8]<=8'(b*13+waddr0*11+job*37);
        if(resetn && !abort && tap_valid && tap_ready0) taps<=taps+1;
    end
    always @(negedge clk) if(resetn) begin
        if({ready0,tap_ready0,wreq0,valid0,done0,error0,cycles0} !==
           {ready1,tap_ready1,wreq1,valid1,done1,error1,cycles1})
            $fatal(1,"control/cycle mismatch state=%0d",reference.state);
        if(wreq0 && waddr0!==waddr1) $fatal(1,"weight address mismatch");
        if(valid0 && {data0,last0}!=={data1,last1}) $fatal(1,"valid output mismatch");
        if(valid0 && out_ready) outputs=outputs+1;
        checks=checks+1;
    end
    always @* begin
        tap_data=32'(taps*65537+job*379);
        tap_kx=taps%6;tap_ky=(taps/6)%6;
    end
    task launch;
        begin
            @(posedge clk);#1;
            taps=0;job=job+1;
            for(i=0;i<16;i=i+1) begin
                quant_bias[i*32+:32]=(job%2 ? 32'h7fffffff : 32'h80000000)+i*123;
                quant_shift[i*5+:5]=(job+i)%32;
            end
            tap_valid=1;out_ready=1;start=1;
            @(posedge clk);#1;start=0;
        end
    endtask
    task complete_job;
        begin
            before_outputs=outputs;launch();timeout=0;
            while(!done0 && timeout<2000) begin
                @(posedge clk);#1;timeout=timeout+1;
                tap_valid=tick%5!=1;out_ready=tick%7!=3;
            end
            if(!done0 || error0 || outputs-before_outputs!=16)
                $fatal(1,"job did not produce 16 outputs got=%0d",outputs-before_outputs);
            jobs=jobs+1;tap_valid=0;
            @(posedge clk);#1;
        end
    endtask
    initial begin
        repeat(3) @(posedge clk);#1;resetn=1;
        complete_job();
        for(r=0;r<2;r=r+1) for(s=1;s<=5;s=s+1) begin
            launch();timeout=0;
            while(reference.state!=s && timeout<2000) begin
                @(posedge clk);#1;timeout=timeout+1;
            end
            if(timeout>=2000) $fatal(1,"state never reached %0d",s);
            if(r==0) abort=1;else resetn=0;
            tap_valid=0;
            @(posedge clk);#1;abort=0;resetn=1;
            repeat(2) @(posedge clk);#1;
            complete_job();
        end
        $display("MAC_CONV_RESTART_PASS complete_jobs=%0d resets=5 aborts=5 compared_cycles=%0d",jobs,checks);
        $finish;
    end
endmodule
