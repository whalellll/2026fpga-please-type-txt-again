`timescale 1ns/1ps
module tb_mac_conv_input_dma_address;
    reg clk=0,resetn=0,start=0;
    always #5 clk=~clk;
    localparam [31:0] BASE=32'h10000000;
    reg [8:0] width=7,height=3;
    reg [15:0] channels=1;
    reg [7:0] channel_tile=0;
    reg [31:0] input_src=BASE+32'hff0;
    wire start_ready,busy,done,error,mem_abort;
    wire mem_req_valid,mem_req_write,mem_rsp_ready,out_valid;
    wire [31:0] mem_req_addr,out_data,input_ddr_bytes,window_taps,stall_cycles,cycles;
    wire [2:0] mem_req_len,out_kx,out_ky;
    wire [8:0] out_x,out_y;
    wire [7:0] out_tile_id;
    reg rsp_active=0;
    reg [31:0] rsp_addr=0;
    reg [3:0] rsp_left=0;
    integer produced=0,requests=0,requested_pixels=0,tick=0,cases=0,total_taps=0;
    reg [31:0] golden_tmp;
    wire req_ready=!rsp_active && tick%5!=1;
    wire rsp_valid=rsp_active && tick%3!=1;
    wire out_ready=tick%7!=2;
    wire [31:0] rsp_word={8'(((rsp_addr-input_src)>>2)*7+27),
        8'(((rsp_addr-input_src)>>2)*7+18),8'(((rsp_addr-input_src)>>2)*7+9),
        8'(((rsp_addr-input_src)>>2)*7)};
    mac_conv_input_dma #(.DDR_BASE(BASE),.DDR_BYTES(256*1024*1024),.TIMEOUT_CYCLES(100)) dut (
        .clk(clk),.resetn(resetn),.start(start),.start_ready(start_ready),
        .width(width),.height(height),.channels(channels),.channel_tile(channel_tile),
        .kernel(3'd1),.stride(2'd1),.padding(3'd0),.input_src(input_src),
        .mem_req_valid(mem_req_valid),.mem_req_ready(req_ready),
        .mem_req_write(mem_req_write),.mem_req_addr(mem_req_addr),.mem_req_len(mem_req_len),
        .mem_rsp_valid(rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_rdata(rsp_word),
        .mem_rsp_last(rsp_left==1),.mem_rsp_error(1'b0),.mem_abort(mem_abort),
        .out_valid(out_valid),.out_ready(out_ready),.out_data(out_data),.out_x(out_x),
        .out_y(out_y),.out_kx(out_kx),.out_ky(out_ky),.out_tile_id(out_tile_id),
        .busy(busy),.done(done),.error(error),.input_ddr_bytes(input_ddr_bytes),
        .window_taps(window_taps),.stall_cycles(stall_cycles),.cycles(cycles));
    task golden_word;
        input integer pixel;
        output [31:0] golden_result;
        integer word_index,l;
        begin
            word_index=pixel*((channels+3)/4)+channel_tile;golden_result=0;
            for(l=0;l<4;l=l+1) if(channel_tile*4+l<channels)
                golden_result[l*8+:8]=8'(word_index*7+l*9);
        end
    endtask
    always @(posedge clk) if(resetn) begin
        tick<=tick+1;
        if(mem_abort) $fatal(1,"unexpected abort");
        if(mem_req_valid && req_ready) begin
            if(mem_req_write || mem_req_addr!==input_src+
               (requested_pixels*((channels+3)/4)+channel_tile)*4 ||
               mem_req_addr[11:0]+((mem_req_len+1)*4)>4096 ||
               (channels>4 && mem_req_len!=0)) $fatal(1,"read address/burst mismatch");
            rsp_active<=1;rsp_addr<=mem_req_addr;rsp_left<=mem_req_len+1;
            requested_pixels<=requested_pixels+mem_req_len+1;requests<=requests+1;
        end else if(rsp_valid && mem_rsp_ready) begin
            if(rsp_left==1) rsp_active<=0;
            else begin rsp_addr<=rsp_addr+4;rsp_left<=rsp_left-1;end
        end
        if(out_valid && out_ready) begin
            golden_word(produced,golden_tmp);
            if(out_data!==golden_tmp || out_x!==produced%width ||
               out_y!==produced/width || out_kx!=0 || out_ky!=0 || out_tile_id!=channel_tile)
                $fatal(1,"tap mismatch pixel=%0d actual=%h expected=%h",produced,out_data,golden_tmp);
            produced<=produced+1;
        end
    end
    task run_job;
        input integer cin,tile,w,h,offset;
        integer timeout;
        begin
            @(negedge clk);channels=cin;channel_tile=tile;width=w;height=h;
            input_src=BASE+offset;produced=0;requested_pixels=0;requests=0;
            start=1;@(negedge clk);start=0;timeout=0;
            while(!done && !error && timeout<20000) begin @(negedge clk);timeout=timeout+1;end
            if(!done || error || produced!=w*h || requested_pixels!=w*h ||
               input_ddr_bytes!=w*h*4 || window_taps!=w*h || stall_cycles==0)
                $fatal(1,"DMA totals mismatch");
            $display("MAC_CONV_ADDRESS_CASE_PASS cin=%0d tile=%0d w=%0d h=%0d bytes=%0d requests=%0d cycles=%0d stalls=%0d",
                cin,tile,w,h,input_ddr_bytes,requests,cycles,stall_cycles);
            total_taps=total_taps+produced;cases=cases+1;
        end
    endtask
    initial begin
        repeat(4) @(negedge clk);resetn=1;
        for(integer c=1;c<=8;c=c+1) run_job(c,(c-1)/4,7,3,32'hff0);
        run_job(17,4,7,3,32'h1ffc);run_job(33,8,7,3,32'h2ff8);
        run_job(1023,255,320,2,32'h3ff0);run_job(1024,255,320,2,32'h3ff0);
        $display("MAC_CONV_ADDRESS_PASS cases=%0d taps=%0d",cases,total_taps);$finish;
    end
    initial begin #10000000;$fatal(1,"DMA address timeout");end
endmodule
