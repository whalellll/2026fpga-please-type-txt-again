`timescale 1ns/1ps
// Exercise channel selection independently of the PE and DMA timing.
// Distinct 48-bit lanes expose truncated high bits and packed-lane swaps.
module tb_mac_lane_select;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    reg [1535:0] acc_bits,bias_bits,post_bits;
    reg [5:0] lane;
    reg [1:0] mode;
    reg [31:0] random_state=32'h731ac965;
    integer sample,m,l,i,physical,checks=0;
    reg [47:0] acc_value,bias_value,expected_sum;
    reg [31:0] narrow_sum;
    MacEngine dut(.io_clk(clk),.io_rstN(resetn),.io_start(1'b0),
        .io_doneClear(1'b0),.io_cfgPixels(16'd1),.io_cfgCin(16'd4),
        .io_cfgCout(16'd32),.io_cfgComputeMode(2'd0),.io_cfgActivation(2'd0),
        .io_cfgOutputFormat(2'd3),.io_cfgOutShift(8'd0),
        .io_wtRdata(1024'b0),.io_inRdata(64'b0),.io_biasRdata(1536'b0));
    // Former next_random function, inlined as sequential statements.
    initial begin
        repeat(3) @(negedge clk);resetn=1;
        force dut.accSnapshot=acc_bits;
        force dut.biasSnapshot=bias_bits;
        force dut.postSnapshot=post_bits;
        force dut.laneIndex=lane;
        force dut.computeModeR=mode;
        for(sample=0;sample<32;sample=sample+1) begin
            for(i=0;i<32;i=i+1) begin
                random_state=random_state^(random_state<<13);
                random_state=random_state^(random_state>>17);
                random_state=random_state^(random_state<<5);
                acc_bits[i*48+:48]={16'(random_state^i),random_state};
                random_state=random_state^(random_state<<13);
                random_state=random_state^(random_state>>17);
                random_state=random_state^(random_state<<5);
                bias_bits[i*48+:48]={16'(random_state^sample),random_state};
                random_state=random_state^(random_state<<13);
                random_state=random_state^(random_state>>17);
                random_state=random_state^(random_state<<5);
                post_bits[i*48+:48]={16'(random_state+i),random_state};
            end
            // Include 48-bit overflow, 32-bit overflow, and signed boundaries.
            acc_bits[0+:48]=48'h7fffffffffff;bias_bits[0+:48]=1;
            acc_bits[48+:48]=48'h800000000000;bias_bits[48+:48]=48'hffffffffffff;
            acc_bits[96+:48]=48'h12347fffffff;bias_bits[96+:48]=1;
            acc_bits[144+:48]=48'h567880000000;bias_bits[144+:48]=48'hffffffffffff;
            for(m=0;m<4;m=m+1) for(l=0;l<64;l=l+1) begin
                mode=m;lane=l;#1;
                physical=m==0 ? l%32 : (l%2)*16+(l%32)/2;
                acc_value=acc_bits[physical*48+:48];
                bias_value=bias_bits[(l%32)*48+:48];
                narrow_sum=acc_value[31:0]+bias_value[31:0];
                expected_sum=(m==1 || m==2) ? {{16{narrow_sum[31]}},narrow_sum} :
                    acc_value+bias_value;
                if(dut.sum48Shared!==expected_sum ||
                   dut._GEN_366!==post_bits[physical*48+:48])
                    $fatal(1,"lane selection sample=%0d mode=%0d lane=%0d physical=%0d sum=%h expected=%h",sample,m,l,physical,dut.sum48Shared,expected_sum);
                checks=checks+1;
            end
        end
        release dut.accSnapshot;release dut.biasSnapshot;release dut.postSnapshot;
        release dut.laneIndex;release dut.computeModeR;
        $display("MAC_LANE_SELECT_PASS checks=%0d modes=4 lane_indices=64 seed=731ac965",checks);
        $finish;
    end
endmodule
