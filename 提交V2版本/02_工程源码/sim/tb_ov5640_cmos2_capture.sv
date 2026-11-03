`timescale 1ns/1ps

module tb_ov5640_cmos2_capture;
    reg pclk = 1'b0;
    reg resetn = 1'b0;
    reg capture_enable = 1'b0;
    reg camera_vsync = 1'b0;
    reg camera_href = 1'b0;
    reg [7:0] camera_data = 8'd0;

    wire frame_vsync;
    wire line_active;
    wire pixel_valid;
    wire [15:0] pixel_rgb565;

    reg [15:0] expected [0:15];
    integer expected_count = 0;
    integer observed_count = 0;
    integer count_before_disable = 0;

    always #5 pclk = ~pclk;

    ov5640_cmos2_capture dut (
        .pclk(pclk),
        .resetn(resetn),
        .capture_enable(capture_enable),
        .camera_vsync(camera_vsync),
        .camera_href(camera_href),
        .camera_data(camera_data),
        .frame_vsync(frame_vsync),
        .line_active(line_active),
        .pixel_valid(pixel_valid),
        .pixel_rgb565(pixel_rgb565)
    );

    task expect_raw_word;
        input [7:0] first_value;
        input [7:0] second_value;
        begin
            expected[expected_count] = {
                second_value[4:0],
                first_value[2:0],
                second_value[7:5],
                first_value[7:3]
            };
            expected_count = expected_count + 1;
        end
    endtask

    task drive_byte;
        input [7:0] value;
        begin
            @(negedge pclk);
            camera_href = 1'b1;
            camera_data = value;
            @(posedge pclk);
            #1;
        end
    endtask

    task end_line;
        begin
            @(negedge pclk);
            camera_href = 1'b0;
            camera_data = 8'd0;
            repeat (2) @(posedge pclk);
            #1;
        end
    endtask

    always @(posedge pclk) begin
        #1;
        if (pixel_valid) begin
            if (observed_count >= expected_count)
                $fatal(1, "unexpected pixel %h", pixel_rgb565);
            if (pixel_rgb565 !== expected[observed_count])
                $fatal(1, "pixel %0d mismatch: got %h expected %h",
                    observed_count, pixel_rgb565, expected[observed_count]);
            observed_count = observed_count + 1;
        end
    end

    initial begin
        repeat (3) @(posedge pclk);
        resetn = 1'b1;
        camera_vsync = 1'b1;
        capture_enable = 1'b1;

        // Enabling during an existing VSYNC pulse must not synthesize a false
        // frame edge.  Capture arms only after low, then follows the next
        // complete VSYNC pulse.
        repeat (4) @(posedge pclk);
        #1;
        if (frame_vsync || line_active || pixel_valid)
            $fatal(1, "capture armed in the middle of VSYNC");
        @(negedge pclk);
        camera_vsync = 1'b0;
        repeat (3) @(posedge pclk);
        @(negedge pclk);
        camera_vsync = 1'b1;
        repeat (2) @(posedge pclk);
        #1;
        if (!frame_vsync)
            $fatal(1, "capture did not arm on a clean VSYNC edge");
        @(negedge pclk);
        camera_vsync = 1'b0;
        repeat (2) @(posedge pclk);

        // Reference RGB565 reordering: red and blue fields exchange places.
        expect_raw_word(8'hf8, 8'h00);
        expect_raw_word(8'h07, 8'he0);
        expect_raw_word(8'h00, 8'h1f);
        drive_byte(8'hf8);
        drive_byte(8'h00);
        drive_byte(8'h07);
        drive_byte(8'he0);
        drive_byte(8'h00);
        drive_byte(8'h1f);
        end_line();

        // An odd byte at the end of one line must not pair with the next line.
        expect_raw_word(8'haa, 8'hbb);
        drive_byte(8'haa);
        drive_byte(8'hbb);
        drive_byte(8'hcc);
        end_line();

        expect_raw_word(8'hdd, 8'hee);
        drive_byte(8'hdd);
        drive_byte(8'hee);
        end_line();

        // Disabling between the first and second internal byte phases drops
        // the partial pixel and prevents it from surviving a later re-entry.
        count_before_disable = observed_count;
        drive_byte(8'h11);
        drive_byte(8'h22);
        @(negedge pclk);
        capture_enable = 1'b0;
        camera_href = 1'b0;
        repeat (3) @(posedge pclk);
        #1;
        if (observed_count != count_before_disable)
            $fatal(1, "partial pixel escaped while capture was disabled");

        @(negedge pclk);
        capture_enable = 1'b1;
        expect_raw_word(8'h12, 8'h34);
        drive_byte(8'h12);
        drive_byte(8'h34);
        end_line();

        // VSYNC is registered once at the DVP input and once at the output.
        @(negedge pclk);
        camera_vsync = 1'b1;
        repeat (2) @(posedge pclk);
        #1;
        if (!frame_vsync)
            $fatal(1, "registered VSYNC did not assert");
        @(negedge pclk);
        camera_vsync = 1'b0;
        repeat (2) @(posedge pclk);
        #1;
        if (frame_vsync)
            $fatal(1, "registered VSYNC did not deassert");

        if (observed_count != expected_count)
            $fatal(1, "pixel count mismatch: got %0d expected %0d",
                observed_count, expected_count);

        $display("OV5640_CMOS2_CAPTURE_PASS pixels=%0d", observed_count);
        $finish;
    end

    initial begin
        #20000;
        $fatal(1, "capture test timeout");
    end
endmodule
