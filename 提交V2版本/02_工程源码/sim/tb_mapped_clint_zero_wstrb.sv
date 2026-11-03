`timescale 1ns/1ps

// Isolated mapped clint module from an exact integrated SoC ADS VM.
// OLD_VM selects only the two extra e526 input ports for the negative fixture.
module tb_mapped_clint_zero_wstrb;
    reg clk = 0;
    always #5 clk = ~clk;
    reg reset_clear = 1;
    reg cyc = 0;
    reg write_fire = 0;
    reg [31:0] address = 0;
    reg [31:0] wdata = 0;
    reg [3:0] sel = 0;
    wire [31:0] rdata;
    wire ack, software_irq, timer_irq;
    GTP_GRS GRS_INST (.GRS_N(1'b1));

    clint dut (
        .addr(address), .d_araddr(address), .l_araddr(address),
        .l_wdata(wdata), .l_wstrb(sel),
        .\u_cpu/u_cpu_wrapper/local_wr_addr (address),
        .clk(clk), .cyc(cyc),
        .\u_cpu/u_cpu_wrapper/local_write_fire (write_fire),
        .\u_mac_accel/u_dma_kernel/u_mac_accel/inputBank/_T_3 (reset_clear),
        .rdata(rdata), .ack(ack),
        .software_irq(software_irq), .timer_irq(timer_irq)
`ifdef CLINT_SHARED_IO_VM
        // ADS also placed an independent SD I/O decode LUT in this module.
        , .io_addr(address), ._N321426(1'b0), .io_wr(1'b0),
        .sd_hit(1'b0), .\u_sd/busy (1'b0)
`endif
`ifdef OLD_VM
        , .io_addr(address), ._N322925(1'b1)
`endif
    );

    integer ordinary_writes = 0;
    integer zero_writes = 0;
    reg [63:0] before_ticks;

    task issue_mtime_write(
        input [31:0] target,
        input [31:0] data,
        input [3:0] lanes
    );
        begin
            @(negedge clk);
            before_ticks = dut.mtime;
            address = target;
            wdata = data;
            sel = lanes;
            cyc = 1;
            write_fire = 1;
            @(negedge clk);
            if (!ack)
                $fatal(1, "mapped CLINT write was not accepted at %h", target);
            if (lanes == 0) begin
                if (zero_writes == 0 &&
                    before_ticks[31:0] !== 32'hffff_ffff)
                    $fatal(1, "mapped CLINT rollover setup missed FFFFFFFF");
                if (dut.mtime !== before_ticks + 64'd1)
                    $fatal(1,
                        "mapped CLINT zero-WSTRB lost SYS tick addr=%h before=%h after=%h",
                        target, before_ticks, dut.mtime);
                zero_writes = zero_writes + 1;
            end else if (target[2] == 0) begin
                if (dut.mtime !== {before_ticks[63:32], data})
                    $fatal(1,
                        "mapped CLINT low full-strobe write ineffective before=%h after=%h",
                        before_ticks, dut.mtime);
                ordinary_writes = ordinary_writes + 1;
            end else begin
                if (dut.mtime !== {data, before_ticks[31:0]})
                    $fatal(1,
                        "mapped CLINT high full-strobe write ineffective before=%h after=%h",
                        before_ticks, dut.mtime);
                ordinary_writes = ordinary_writes + 1;
            end
            cyc = 0;
            write_fire = 0;
            @(negedge clk);
            if (ack)
                $fatal(1, "mapped CLINT acknowledged more than once");
        end
    endtask

    initial begin
        #22;
        reset_clear = 0;
        repeat (3) @(negedge clk);
        issue_mtime_write(32'h0200_bffc, 32'd5, 4'hf);
        issue_mtime_write(32'h0200_bff8, 32'hffff_fffd, 4'hf);
        issue_mtime_write(32'h0200_bff8, 32'hdead_beef, 4'h0);
        issue_mtime_write(32'h0200_bffc, 32'hdead_beef, 4'h0);
        if (ordinary_writes != 2 || zero_writes != 2)
            $fatal(1, "mapped CLINT test did not exercise both write classes");
        $display("MAPPED_CLINT_ZERO_WSTRB_PASS ordinary=%0d zero=%0d final_mtime=%h",
            ordinary_writes, zero_writes, dut.mtime);
        $finish;
    end

    initial begin
        #2000;
        $fatal(1, "mapped CLINT test timeout");
    end
endmodule
