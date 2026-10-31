`timescale 1ns/1ps

module tb_camera_mmio;
    reg clk = 1'b0;
    reg resetn = 1'b0;
    reg [31:0] addr = 32'd0;
    reg wr = 1'b0;
    reg [31:0] wdata = 32'd0;
    reg [3:0] wstrb = 4'd0;
    wire [31:0] rdata;
    wire hit;
    wire enable;
    wire stop_request;
    wire snapshot_hold;
    reg snapshot_ready = 1'b0;
    reg snapshot_buffer = 1'b0;
    reg [31:0] snapshot_frame_count = 32'd0;

    reg cmos1_init_done = 1'b0;
    reg cmos2_init_done = 1'b0;
    reg frame_valid = 1'b0;
    reg writer_busy = 1'b0;
    reg idle = 1'b1;
    reg stopping = 1'b0;
    reg completed_buffer = 1'b0;
    reg sccb_nack = 1'b0;
    reg frame_error = 1'b0;
    reg ddr_error = 1'b0;
    reg [31:0] frame_count = 32'd0;
    reg [31:0] dropped_count = 32'd0;
    reg [31:0] bad_line_count = 32'd0;

    always #5 clk = ~clk;

    camera_mmio dut (
        .clk(clk), .resetn(resetn), .addr(addr), .wr(wr),
        .wdata(wdata), .wstrb(wstrb), .rdata(rdata), .hit(hit),
        .enable(enable), .stop_request(stop_request),
        .snapshot_hold(snapshot_hold), .snapshot_ready(snapshot_ready),
        .hud_ack(1'b0),
        .snapshot_buffer(snapshot_buffer),
        .snapshot_frame_count(snapshot_frame_count),
        .cmos1_init_done(cmos1_init_done),
        .cmos2_init_done(cmos2_init_done), .frame_valid(frame_valid),
        .writer_busy(writer_busy), .idle(idle), .stopping(stopping),
        .completed_buffer(completed_buffer), .sccb_nack(sccb_nack),
        .frame_error(frame_error), .ddr_error(ddr_error),
        .frame_count(frame_count), .dropped_count(dropped_count),
        .bad_line_count(bad_line_count)
    );

    initial begin
        repeat (3) @(posedge clk);
        resetn <= 1'b1;
        @(posedge clk);

        addr <= 32'h1fe12000;
        #1;
        if (!hit || rdata != 32'h43414d33)
            $fatal(1, "camera ID register mismatch");
        addr <= 32'h1fe12004;
        #1;
        if (rdata != 32'h00010003)
            $fatal(1, "camera version register mismatch");

        // Byte writes outside lane zero must not alter CONTROL.
        addr <= 32'h1fe12008;
        wr <= 1'b1;
        wdata <= 32'h00000003;
        wstrb <= 4'b0010;
        @(posedge clk);
        #1;
        if (enable || stop_request)
            $fatal(1, "CONTROL ignored byte enables");

        wstrb <= 4'b0001;
        @(posedge clk);
        #1;
        wr <= 1'b0;
        if (!enable || !stop_request || rdata[1:0] != 2'b11)
            $fatal(1, "CONTROL write/readback mismatch");

        wr <= 1'b1;
        wdata <= 32'h00000005;
        @(posedge clk);
        #1;
        wr <= 1'b0;
        if (!snapshot_hold || !enable || stop_request || rdata[2:0] != 3'b101)
            $fatal(1, "snapshot hold control mismatch");

        cmos1_init_done <= 1'b1;
        cmos2_init_done <= 1'b1;
        frame_valid <= 1'b1;
        writer_busy <= 1'b1;
        idle <= 1'b0;
        stopping <= 1'b1;
        completed_buffer <= 1'b1;
        sccb_nack <= 1'b1;
        frame_error <= 1'b1;
        ddr_error <= 1'b1;
        snapshot_ready <= 1'b1;
        snapshot_buffer <= 1'b1;
        snapshot_frame_count <= 32'h23456789;
        addr <= 32'h1fe1200c;
        #1;
        if (rdata[12:0] != 13'b1111111011111)
            $fatal(1, "STATUS bit mapping mismatch: %h", rdata);

        frame_count <= 32'h12345678;
        dropped_count <= 32'h89abcdef;
        bad_line_count <= 32'h55aa00ff;
        addr <= 32'h1fe12010;
        #1;
        if (rdata != 32'h12345678)
            $fatal(1, "frame counter mismatch");
        addr <= 32'h1fe12014;
        #1;
        if (rdata != 32'h89abcdef)
            $fatal(1, "drop counter mismatch");
        addr <= 32'h1fe12018;
        #1;
        if (rdata != 32'h55aa00ff)
            $fatal(1, "bad-line counter mismatch");
        addr <= 32'h1fe1201c;
        #1;
        if (rdata != 32'h23456789)
            $fatal(1, "latched snapshot frame mismatch");

        addr <= 32'h1fe12100;
        #1;
        if (hit || rdata != 32'd0)
            $fatal(1, "camera MMIO decoded outside its window");

        $display("CAMERA_MMIO_PASS");
        $finish;
    end
endmodule
