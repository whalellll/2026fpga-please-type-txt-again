`timescale 1ns/1ps
// Independent byte sequence, including cross-bank writes for Cin=1/2/3,
// padding poison, input stalls, all read rows, and aborted capture recovery.
module tb_mac_conv_activation_bank;
    reg clk=0,resetn=0,start=0,abort=0,tap_valid=0;
    always #5 clk=~clk;
    reg [15:0] channels;
    reg [2:0] kernel,tap_kx=0,tap_ky=0;
    reg [31:0] tap_data;
    reg [4:0] selected_row;
    wire tap_ready,start_ready,error;
    reg [7:0] golden[0:127];
    reg [31:0] expected;
    integer c,k,x,y,l,row,count,total=0,cases=0;
    mac_conv_compute_core dut(.clk(clk),.resetn(resetn),.start(start),.abort(abort),
        .start_ready(start_ready),.width({6'b0,kernel}),.height({6'b0,kernel}),
        .channels(channels),.output_channels(16'd1),.kernel(kernel),.stride(2'd1),
        .padding(3'd0),.weight_lines(6'((channels*kernel*kernel+3)/4)),
        .quant_bias(512'b0),.quant_shift(80'b0),.tap_valid(tap_valid),
        .tap_ready(tap_ready),.tap_data(tap_data),.tap_x(9'd0),.tap_y(9'd0),
        .tap_kx(tap_kx),.tap_ky(tap_ky),.tap_tile(8'd0),
        .weight_read_valid(1'b0),.weight_read_data(1024'b0),.out_ready(1'b0),.error(error));
    task begin_capture;
        begin
            @(negedge clk);abort=1;tap_valid=0;
            @(negedge clk);abort=0;start=1;
            @(negedge clk);start=0;
            if(!tap_ready) $fatal(1,"capture was not accepted");
        end
    endtask
    initial begin
        repeat(3) @(negedge clk);resetn=1;
        for(c=1;c<=4;c=c+1) for(k=1;k<=6;k=k+1) if(k==1 || k==3 || k==6) begin
            if(c*k*k<=128) begin
                channels=c;kernel=k;begin_capture();
                // Abort after writing a poisoned first tap, then start cleanly.
                tap_data=32'hdeadbeef;tap_kx=0;tap_ky=0;tap_valid=1;
                @(negedge clk);tap_valid=0;begin_capture();count=0;
                for(y=0;y<k;y=y+1) for(x=0;x<k;x=x+1) begin
                    if((x+y)%2) begin
                        tap_valid=0;tap_data=32'hfefdfcfb;
                        @(negedge clk);
                    end
                    tap_kx=x;tap_ky=y;tap_data=32'ha5a5a5a5;
                    for(l=0;l<c;l=l+1) begin
                        golden[count]=8'(cases*31+count*19+7);
                        tap_data[l*8+:8]=golden[count];count=count+1;
                    end
                    tap_valid=1;
                    @(negedge clk);
                end
                tap_valid=0;
                if(error || dut.scalar_count!=count) $fatal(1,"captured byte count");
                force dut.row_index=selected_row;
                for(row=0;row<32;row=row+1) begin
                    selected_row=row;#1;expected=0;
                    for(l=0;l<4;l=l+1)
                        if(row*4+l<count) expected[l*8+:8]=golden[row*4+l];
                    if(dut.act_word!==expected)
                        $fatal(1,"activation bytes c=%0d k=%0d row=%0d got=%h expected=%h",c,k,row,dut.act_word,expected);
                    total=total+4;
                end
                release dut.row_index;
                cases=cases+1;
            end
        end
        $display("MAC_CONV_ACTIVATION_BANK_PASS cases=%0d checked_bytes=%0d stalls=enabled abort_recovery=enabled",cases,total);
        $finish;
    end
endmodule
