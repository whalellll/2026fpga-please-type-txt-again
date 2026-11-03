`timescale 1ns/1ps

module tb_clint_sys_irq;
    reg sys_clk = 0, cpu_clk = 0, reset_request = 0;
    always #10.101 sys_clk = ~sys_clk;
    initial begin #3.7; forever #7.3 cpu_clk = ~cpu_clk; end
    reg [2:0] sys_pipe = 0, cpu_pipe = 0;
    always @(posedge sys_clk or negedge reset_request)
        if (!reset_request) sys_pipe <= 0;
        else sys_pipe <= {sys_pipe[1:0],1'b1};
    always @(posedge cpu_clk or negedge reset_request)
        if (!reset_request) cpu_pipe <= 0;
        else cpu_pipe <= {cpu_pipe[1:0],1'b1};
    wire sys_resetn = sys_pipe[2], cpu_resetn = cpu_pipe[2];

    reg cyc = 0, stb = 0, we = 1;
    reg [31:0] addr = 0, wdata = 0;
    reg [3:0] sel = 0;
    wire [31:0] rdata;
    wire ack, err, timer_irq_sys, software_irq_sys;
    reg external_irq_sys = 0;
    wire timer_irq_cpu, software_irq_cpu, external_irq_cpu;
    clint dut(.clk(sys_clk),.resetn(sys_resetn),.cyc(cyc),.stb(stb),.we(we),
        .addr(addr),.wdata(wdata),.sel(sel),.rdata(rdata),.ack(ack),.err(err),
        .timer_irq(timer_irq_sys),.software_irq(software_irq_sys));
    cpu_irq_sync irq_return(.cpu_clk(cpu_clk),.cpu_resetn(cpu_resetn),
        .timer_irq_sys(timer_irq_sys),.software_irq_sys(software_irq_sys),
        .external_irq_sys(external_irq_sys),
        .timer_irq_cpu(timer_irq_cpu),.software_irq_cpu(software_irq_cpu),
        .external_irq_cpu(external_irq_cpu));

    task mmio_write(input [31:0] address, input [31:0] data,
                    input [3:0] strobes);
        begin
            @(negedge sys_clk);
            addr = address; wdata = data; sel = strobes;
            cyc = 1; stb = 1; we = 1;
            @(negedge sys_clk);
            if (!ack || err) $fatal(1,"CLINT write did not acknowledge");
            cyc = 0; stb = 0;
            @(negedge sys_clk);
            if (ack) $fatal(1,"CLINT write repeated after strobe ended");
        end
    endtask

    task mmio_read(input [31:0] address, output [31:0] data);
        begin
            @(negedge sys_clk);
            addr = address; we = 0;
            #1; data = rdata;
        end
    endtask

    task mmio_zero_strobe_mtime(input [31:0] address);
        reg [63:0] before_ticks;
        begin
            @(negedge sys_clk);
            before_ticks = dut.mtime;
            addr = address; wdata = 32'hdead_beef; sel = 4'b0000;
            cyc = 1; stb = 1; we = 1;
            @(negedge sys_clk);
            if (!ack || err) $fatal(1,"zero-strobe mtime write did not acknowledge");
            if (dut.mtime !== before_ticks + 64'd1)
                $fatal(1,"zero-strobe mtime write lost a SYS tick at %h",address);
            cyc = 0; stb = 0;
            @(negedge sys_clk);
            if (ack) $fatal(1,"zero-strobe mtime write acknowledged twice");
        end
    endtask

    reg [31:0] high0, low0, high1;
    initial begin
        #30; reset_request = 1;
        repeat (5) @(negedge sys_clk);
        if (timer_irq_sys || software_irq_sys || timer_irq_cpu ||
            software_irq_cpu || err || dut.mtimecmp !== 64'hffff_ffff_ffff_ffff)
            $fatal(1,"bad CLINT reset state");

        // Byte strobes on mtimecmp must preserve the untouched lanes.
        mmio_write(32'h0200_4000,32'h1234_5678,4'hf);
        mmio_write(32'h0200_4000,32'haa00_00bb,4'b1001);
        mmio_read(32'h0200_4000,low0);
        if (low0 !== 32'haa34_56bb)
            $fatal(1,"mtimecmp byte-strobe merge failed: %h",low0);

        // A legal AXI write with no byte lanes selected has no timer side
        // effect: mtime must still advance once on the accepting SYS edge.
        mmio_zero_strobe_mtime(32'h0200_bff8);
        mmio_zero_strobe_mtime(32'h0200_bffc);

        // Program just before the low-word rollover.  The SYS timer rolls
        // into the high word independently of CPU clock phase/frequency.
        mmio_write(32'h0200_bffc,32'd5,4'hf);
        mmio_write(32'h0200_bff8,32'hffff_fffe,4'hf);
        mmio_read(32'h0200_bffc,high0);
        mmio_read(32'h0200_bff8,low0);
        mmio_read(32'h0200_bffc,high1);
        if (high1 < high0 || high1 != 32'd6 || dut.mtime[63:32] != 32'd6)
            $fatal(1,"mtime rollover/high-low-high retry boundary failed");

        mmio_write(32'h0200_0000,32'd1,4'b0001);
        repeat (4) @(negedge cpu_clk);
        if (!software_irq_sys || !software_irq_cpu)
            $fatal(1,"MSIP level failed to cross to CPU");
        mmio_write(32'h0200_0000,32'd0,4'b0010);
        repeat (3) @(negedge cpu_clk);
        if (!software_irq_sys || !software_irq_cpu)
            $fatal(1,"non-low-byte write unexpectedly cleared MSIP");
        mmio_write(32'h0200_0000,32'd0,4'b0001);
        repeat (4) @(negedge cpu_clk);
        if (software_irq_sys || software_irq_cpu)
            $fatal(1,"MSIP clear failed to cross to CPU");

        // Restart near zero and arm MTIP at a small fixed SYS tick value.
        mmio_write(32'h0200_bffc,32'd0,4'hf);
        mmio_write(32'h0200_bff8,32'd0,4'hf);
        mmio_write(32'h0200_4004,32'd0,4'hf);
        mmio_write(32'h0200_4000,32'd24,4'hf);
        wait (timer_irq_sys);
        repeat (4) @(negedge cpu_clk);
        if (!timer_irq_cpu) $fatal(1,"MTIP level failed to cross to CPU");
        repeat (5) @(negedge cpu_clk);
        if (!timer_irq_cpu) $fatal(1,"MTIP did not persist as a level");
        mmio_write(32'h0200_4004,32'd1,4'hf);
        repeat (4) @(negedge cpu_clk);
        if (timer_irq_sys || timer_irq_cpu)
            $fatal(1,"MTIP clear failed to cross to CPU");

        external_irq_sys = 1;
        repeat (4) @(negedge cpu_clk);
        if (!external_irq_cpu) $fatal(1,"external level sync failed");
        external_irq_sys = 0;
        repeat (4) @(negedge cpu_clk);
        if (external_irq_cpu) $fatal(1,"external level clear failed");

        reset_request = 0;
        #1;
        if (timer_irq_cpu || software_irq_cpu || external_irq_cpu)
            $fatal(1,"CPU IRQ survived common asynchronous reset");
        #40; reset_request = 1;
        repeat (5) @(negedge sys_clk);
        if (dut.mtimecmp !== 64'hffff_ffff_ffff_ffff || ack ||
            timer_irq_sys || software_irq_sys || timer_irq_cpu || software_irq_cpu)
            $fatal(1,"CLINT/IRQ produced ghost state after reset");
        $display("CLINT_SYS_IRQ_PASS mtime_rollover=1 strobe=1 mtip_msip=1 reset=1");
        $finish;
    end
    initial begin #20000; $fatal(1,"CLINT/IRQ timeout"); end
endmodule
