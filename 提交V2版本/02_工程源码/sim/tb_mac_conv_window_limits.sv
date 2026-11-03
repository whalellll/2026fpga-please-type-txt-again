`timescale 1ns/1ps
module tb_mac_conv_window_limits;
    reg clk=0;always #5 clk=~clk;
    reg resetn=0,flush=0,cfg_valid=0,in_valid=0,out_ready=0;
    reg [8:0] cfg_width,cfg_height;
    reg [2:0] cfg_kernel=6,cfg_padding=5;
    reg [1:0] cfg_stride=2;
    reg [7:0] cfg_tile_id=0;
    reg [31:0] in_data;
    wire cfg_ready,in_ready,out_valid,done,error;
    wire [31:0] out_data,input_beats,output_beats,stall_cycles;
    wire [8:0] out_x,out_y;
    wire [2:0] out_kx,out_ky;
    wire [7:0] out_tile_id;
    mac_conv_window dut(.*);
    integer sent=0,seen=0,clock_count=0,ox,oy,kx,ky,x,y,ow,oh;
    reg checking=0;
    reg [31:0] expected;
    // Former pixel function, inlined as ((((y<<16)|x)^32'h8123c456)).
    always @(posedge clk) begin
        if(checking) begin
            clock_count=clock_count+1;
            if(in_valid && in_ready)sent=sent+1;
            if(out_valid && out_ready) begin
                kx=seen%6;ky=(seen/6)%6;ox=(seen/36)%ow;oy=seen/(36*ow);
                x=ox*2+kx-5;y=oy*2+ky-5;
                expected=(x<0 || x>=cfg_width || y<0 || y>=cfg_height)?0:((((y<<16)|x)^32'h8123c456));
                if(out_data!==expected || out_x!=ox || out_y!=oy || out_kx!=kx || out_ky!=ky)
                    $fatal(1,"window limits mismatch tap=%0d xy=%0d/%0d got=%h expected=%h",seen,x,y,out_data,expected);
                seen=seen+1;
            end
        end
    end
    task run;
        input integer width,height;
        begin
            @(negedge clk);cfg_width=width;cfg_height=height;cfg_valid=1;
            @(negedge clk);cfg_valid=0;
            sent=0;seen=0;clock_count=0;ow=(width+4)/2+1;oh=(height+4)/2+1;checking=1;
            while(!done && clock_count<200000)begin
                in_valid=sent<width*height && clock_count%7!=0;
                in_data=(((sent/width)<<16)|(sent%width))^32'h8123c456;
                out_ready=clock_count%5!=0;
                @(negedge clk);
            end
            checking=0;in_valid=0;out_ready=0;
            if(!done || error || sent!=width*height || seen!=ow*oh*36)
                $fatal(1,"window limits completion width=%0d height=%0d sent=%0d seen=%0d",width,height,sent,seen);
            $display("CONV_WINDOW_LIMIT_PASS width=%0d height=%0d taps=%0d cycles=%0d",width,height,seen,clock_count);
        end
    endtask
    initial begin
        repeat(3)@(negedge clk);resetn=1;
        run(320,7);run(7,320);$finish;
    end
endmodule
