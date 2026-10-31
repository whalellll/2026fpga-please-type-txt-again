`timescale 1ns / 1ps
module tb_mac_conv_read_arbiter2;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    reg a_req_valid=0, b_req_valid=0;
    wire a_req_ready, b_req_ready;
    reg [31:0] a_req_addr=32'h1000, b_req_addr=32'h2000;
    reg [2:0] a_req_len=0, b_req_len=0;
    wire a_rsp_valid,b_rsp_valid,a_rsp_last,b_rsp_last;
    reg a_rsp_ready=1,b_rsp_ready=1;
    wire [31:0] a_rsp_rdata,b_rsp_rdata;
    wire a_rsp_error,b_rsp_error;
    reg a_abort=0,b_abort=0;
    wire mem_req_valid,mem_req_ready,mem_abort;
    wire [31:0] mem_req_addr;
    wire [2:0] mem_req_len;
    reg mem_rsp_valid=0,mem_rsp_last=0,mem_rsp_error=0;
    reg [31:0] mem_rsp_rdata=0;
    wire mem_rsp_ready;
    integer i;

    assign mem_req_ready=1;
    mac_conv_read_arbiter2 dut (.*);

    initial begin
        repeat(3) @(negedge clk);resetn=1;
        a_req_valid=1;b_req_valid=1;
        for(i=0;i<6;i=i+1) begin
            #1;
            if (!mem_req_valid || mem_req_addr != (i%2==0 ? 32'h1000 : 32'h2000) ||
                mem_req_len!=0 || a_req_ready==b_req_ready)
                $fatal(1,"round-robin request %0d wrong addr=%h",i,mem_req_addr);
            @(posedge clk);#1;
            @(negedge clk);mem_rsp_valid=1;mem_rsp_last=1;
            mem_rsp_rdata=32'hf00d_0000+i;
            #1;
            if (!mem_rsp_ready ||
                (i%2==0 && (!a_rsp_valid || b_rsp_valid ||
                             a_rsp_rdata!=mem_rsp_rdata)) ||
                (i%2==1 && (!b_rsp_valid || a_rsp_valid ||
                             b_rsp_rdata!=mem_rsp_rdata)))
                $fatal(1,"response routed to wrong owner %0d",i);
            @(posedge clk);#1;
            @(negedge clk);mem_rsp_valid=0;mem_rsp_last=0;
        end
        a_req_valid=1;b_req_valid=0;
        #1;
        if (!mem_req_valid || !a_req_ready) $fatal(1,"abort setup not granted");
        @(posedge clk);#1;
        @(negedge clk);a_abort=1;
        #1;
        if (!mem_abort) $fatal(1,"abort not forwarded");
        @(posedge clk);#1;
        @(negedge clk);a_abort=0;a_req_valid=0;b_req_valid=1;
        #1;
        if (!mem_req_valid || !b_req_ready || mem_req_addr!=32'h2000)
            $fatal(1,"owner not released after abort");
        $display("MAC_CONV_READ_ARBITER2_PASS grants=6 alternating=1 abort=1");
        $finish;
    end
endmodule
