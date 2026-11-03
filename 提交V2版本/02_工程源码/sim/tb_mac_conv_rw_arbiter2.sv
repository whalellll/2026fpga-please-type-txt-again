`timescale 1ns / 1ps
module tb_mac_conv_rw_arbiter2;
    reg clk=0,resetn=0;
    always #5 clk=~clk;
    reg r_req_valid=0,w_req_valid=0,r_rsp_ready=1,w_rsp_ready=1;
    reg [31:0] r_req_addr=32'h1000_0ffc,w_req_addr=32'h1000_1000;
    reg [2:0] r_req_len=0,w_req_len=0;
    reg r_abort=0,w_abort=0,w_w_valid=1;
    reg [31:0] w_w_data=32'h4433_2211;
    reg [3:0] w_w_strb=4'hf;
    reg w_w_last=1;
    wire r_req_ready,w_req_ready,r_rsp_valid,w_rsp_valid;
    wire [31:0] r_rsp_rdata;
    wire r_rsp_last,r_rsp_error,w_rsp_last,w_rsp_error;
    wire w_w_ready,mem_abort;
    wire mem_req_valid,mem_req_write,mem_w_valid,mem_w_last,mem_rsp_ready;
    wire [31:0] mem_req_addr,mem_w_data;
    wire [2:0] mem_req_len;
    wire [3:0] mem_w_strb;
    wire mem_req_ready,mem_w_ready,mem_rsp_valid,mem_rsp_last,mem_rsp_error;
    wire [31:0] mem_rsp_rdata;
    reg [1:0] state=0;
    reg mock_write=0,hold_rsp=0;
    reg [31:0] mock_addr=0;
    integer tick=0,reads=0,writes=0,read_responses=0,write_responses=0;
    integer r_grants=0,w_grants=0;

    mac_conv_rw_arbiter2 dut (.*);
    assign mem_req_ready=state==0;
    assign mem_w_ready=state==1;
    assign mem_rsp_valid=state==2 && tick>=2 && !hold_rsp;
    assign mem_rsp_last=1;
    assign mem_rsp_error=0;
    assign mem_rsp_rdata=mock_addr^32'h5a5a_5a5a;
    always @(posedge clk) begin
        if (!resetn) begin
            state<=0;tick<=0;reads<=0;writes<=0;
            read_responses<=0;write_responses<=0;r_grants<=0;w_grants<=0;
        end else if (mem_abort) begin
            state<=0;tick<=0;
        end else begin
            if (r_req_valid && r_req_ready) begin
                r_req_valid<=0;r_grants<=r_grants+1;
            end
            if (w_req_valid && w_req_ready) begin
                w_req_valid<=0;w_grants<=w_grants+1;
            end
            if (r_rsp_valid && r_rsp_ready &&
                r_rsp_rdata !== (r_req_addr^32'h5a5a_5a5a))
                $fatal(1,"read response routed incorrectly");
            case (state)
            0: if (mem_req_valid && mem_req_ready) begin
                mock_addr<=mem_req_addr;mock_write<=mem_req_write;
                if (mem_req_len!=0) $fatal(1,"unexpected length");
                if (mem_req_write) begin writes<=writes+1;state<=1;end
                else begin reads<=reads+1;state<=2;tick<=0;end
            end
            1: if (mem_w_valid && mem_w_ready) begin
                if (mem_w_data!==w_w_data || mem_w_strb!==w_w_strb ||
                    !mem_w_last) $fatal(1,"write payload changed");
                tick<=0;state<=2;
            end
            2: if (mem_rsp_valid && mem_rsp_ready) begin
                if (mock_write) write_responses<=write_responses+1;
                else read_responses<=read_responses+1;
                state<=0;tick<=0;
            end else tick<=tick+1;
            endcase
        end
    end

    initial begin
        repeat(4) @(negedge clk);resetn=1;
        @(negedge clk);r_req_valid=1;w_req_valid=1;
        wait(read_responses==1 && write_responses==1);
        if (reads!=1 || writes!=1 || r_grants!=1 || w_grants!=1)
            $fatal(1,"concurrent read/write not both granted");
        @(negedge clk);hold_rsp=1;r_req_valid=1;
        wait(r_grants==2);
        repeat(4) @(negedge clk);r_abort=1;
        #1;
        if (!mem_abort) $fatal(1,"read abort did not reach memory");
        @(negedge clk);r_abort=0;hold_rsp=0;
        if (state!=0) $fatal(1,"abort did not release owner");
        $display("MAC_CONV_RW_ARBITER2_PASS reads=%0d writes=%0d responses=%0d/%0d",
                 reads,writes,read_responses,write_responses);
        $finish;
    end
    initial begin #10000;$fatal(1,"RW arbiter global timeout reads=%0d writes=%0d rr=%0d wr=%0d rv=%b wv=%b state=%0d",
                               reads,writes,read_responses,write_responses,
                               r_req_valid,w_req_valid,state);end
endmodule
