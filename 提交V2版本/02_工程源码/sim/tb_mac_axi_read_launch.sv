`timescale 1ns/1ps
// Fast read launch is checked separately from the MAC arithmetic. All
// response beats, AR stalls, response errors and reset reuse remain ordered.
module tb_mac_axi_read_launch;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    reg mem_req_valid=0, mem_req_write=0;
    wire mem_req_ready;
    reg [31:0] mem_req_addr=0;
    reg [2:0] mem_req_len=0;
    reg mem_w_valid=0, mem_w_last=0;
    reg [31:0] mem_w_data=0;
    reg [3:0] mem_w_strb=15;
    wire mem_w_ready;
    wire mem_rsp_valid, mem_rsp_last, mem_rsp_error;
    reg mem_rsp_ready=0;
    wire [31:0] mem_rsp_rdata;
    wire [31:0] m_axi_awaddr, m_axi_wdata, m_axi_araddr;
    wire [7:0] m_axi_awlen, m_axi_arlen;
    wire [2:0] m_axi_awsize, m_axi_arsize;
    wire [1:0] m_axi_awburst, m_axi_arburst;
    wire [3:0] m_axi_wstrb;
    wire m_axi_awvalid, m_axi_wlast, m_axi_wvalid, m_axi_bready;
    wire m_axi_arvalid, m_axi_rready;
    reg m_axi_awready=0, m_axi_wready=0, m_axi_bvalid=0;
    reg [1:0] m_axi_bresp=0, m_axi_rresp=0;
    reg m_axi_arready=0, m_axi_rlast=0, m_axi_rvalid=0;
    reg [31:0] m_axi_rdata=0;
    mac_accel_axi_master32 dut(.*);
    integer case_no, beat, n, accepted=0, gap;
    reg [31:0] expected_addr;
    initial begin
        repeat(3) @(negedge clk); resetn=1;
        for(case_no=0;case_no<32;case_no=case_no+1) begin
            n=case_no%8+1; gap=case_no%4;
            expected_addr=32'h1b001000+case_no*32;
            @(negedge clk); mem_req_valid=1; mem_req_addr=expected_addr;
            mem_req_len=n-1; m_axi_arready=(gap==0);
            #1;
            if(!mem_req_ready || !m_axi_arvalid || m_axi_araddr!==expected_addr ||
               m_axi_arlen!==n-1 || m_axi_arsize!=2 || m_axi_arburst!=1)
                $fatal(1,"read command must launch AR without an address bubble case=%0d",case_no);
            @(posedge clk); #1;
            if(mem_req_ready) $fatal(1,"accepted more than one outstanding command");
            @(negedge clk); mem_req_valid=0; mem_req_addr=32'hdeadbeef; mem_req_len=0;
            if(gap!=0) begin
                repeat(gap) begin
                    #1;
                    if(!m_axi_arvalid || m_axi_araddr!==expected_addr || m_axi_arlen!==n-1)
                        $fatal(1,"AR changed under backpressure");
                    @(negedge clk);
                end
                m_axi_arready=1;
                @(negedge clk);
            end
            #1; if(m_axi_arvalid) $fatal(1,"duplicate AR after acceptance");
            for(beat=0;beat<n;beat=beat+1) begin
                m_axi_rvalid=1; m_axi_rdata=32'h12340000+beat;
                m_axi_rlast=(beat==n-1);
                m_axi_rresp=(case_no%3==0 && beat==0) ? 2 : 0;
                mem_rsp_ready=0; #1;
                if(!mem_rsp_valid || m_axi_rready || mem_rsp_rdata!==m_axi_rdata ||
                   mem_rsp_last!==(beat==n-1) ||
                   mem_rsp_error!==((case_no%3==0)&&(beat==n-1)))
                    $fatal(1,"response mismatch case=%0d beat=%0d",case_no,beat);
                @(negedge clk); mem_rsp_ready=1;
                @(negedge clk); m_axi_rvalid=0; mem_rsp_ready=0;
                accepted=accepted+1;
            end
            #1; if(!mem_req_ready) $fatal(1,"read did not complete");
        end
        // Early RLAST and missing RLAST must terminate with an error rather
        // than leave the command owner hung or contaminate the next job.
        for(case_no=0;case_no<2;case_no=case_no+1) begin
            @(negedge clk); mem_req_valid=1; m_axi_arready=1;
            mem_req_len=case_no==0 ? 7 : 0;
            @(negedge clk); mem_req_valid=0; m_axi_rvalid=1;
            m_axi_rlast=(case_no==0); m_axi_rresp=0; mem_rsp_ready=0;
            #1;
            if(!mem_rsp_valid || !mem_rsp_last || !mem_rsp_error)
                $fatal(1,"malformed RLAST was not reported");
            @(negedge clk); mem_rsp_ready=1;
            @(negedge clk); mem_rsp_ready=0; m_axi_rvalid=0;
            #1; if(!mem_req_ready) $fatal(1,"malformed read did not release owner");
        end
        // Reset while AR is held must cancel the outstanding command.
        @(negedge clk); mem_req_valid=1; m_axi_arready=0;
        @(negedge clk); mem_req_valid=0; resetn=0;
        @(negedge clk); #1;
        if(m_axi_arvalid || mem_rsp_valid) $fatal(1,"reset did not cancel AR");
        resetn=1;
        // Legacy write starts independently: AW and W can handshake apart.
        @(negedge clk); mem_req_valid=1; mem_req_write=1;
        mem_req_addr=32'h1b002000; mem_req_len=0;
        #1; if(m_axi_arvalid) $fatal(1,"write command launched read");
        @(negedge clk); mem_req_valid=0; m_axi_wready=1;
        mem_w_valid=1; mem_w_last=1; mem_w_data=32'h98765432;
        #1; if(!m_axi_awvalid || !m_axi_wvalid || !m_axi_wlast ||
               m_axi_awaddr!==32'h1b002000 || m_axi_wdata!==mem_w_data)
            $fatal(1,"write launch changed");
        @(negedge clk); mem_w_valid=0; m_axi_awready=1;
        @(negedge clk); m_axi_bvalid=1; mem_rsp_ready=1;
        #1; if(!m_axi_bready || !mem_rsp_valid || !mem_rsp_last || mem_rsp_error)
            $fatal(1,"write response changed");
        @(negedge clk); m_axi_bvalid=0; mem_rsp_ready=0;
        #1; if(!mem_req_ready) $fatal(1,"write did not complete");
        $display("MAC_AXI_READ_LAUNCH_PASS cases=32 read_beats=%0d ar_stall=pass rsp_stall=pass error=pass reset=pass write=pass",accepted);
        $finish;
    end
    initial begin #200000; $fatal(1,"timeout"); end
endmodule
