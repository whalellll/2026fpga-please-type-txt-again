module tb_mac_conv_window;
    reg clk = 0;
    always #5 clk = ~clk;
    reg resetn = 0;
    reg flush = 0;
    reg cfg_valid = 0;
    wire cfg_ready;
    reg [8:0] cfg_width = 0, cfg_height = 0;
    reg [2:0] cfg_kernel = 0, cfg_padding = 0;
    reg [1:0] cfg_stride = 0;
    reg [7:0] cfg_tile_id = 0;
    reg in_valid = 0;
    wire in_ready;
    reg [31:0] in_data = 0;
    wire out_valid;
    reg out_ready = 0;
    wire [31:0] out_data;
    wire [8:0] out_x, out_y;
    wire [2:0] out_kx, out_ky;
    wire [7:0] out_tile_id;
    wire done, error;
    wire [31:0] input_beats, output_beats, stall_cycles;
    integer cycle_count = 0;
    integer row_idx;
    always @(posedge clk) cycle_count <= cycle_count + 1;
    integer expected_x = 0, expected_y = 0;
    integer expected_kx = 0, expected_ky = 0;
    integer expected_outputs = 0;
    integer seen_outputs = 0;
    integer case_width = 0, case_height = 0, case_kernel = 0;
    integer case_stride = 0, case_padding = 0, case_out_w = 0;
    integer case_out_h = 0, case_tile = 0;
    integer checking = 0;
    reg stalled_last = 0;
    reg [31:0] stalled_data;
    reg [8:0] stalled_x, stalled_y;
    reg [2:0] stalled_kx, stalled_ky;
    reg [7:0] stalled_tile;

    mac_conv_window #(.MAX_WIDTH(16)) dut (.*);

    // Former pixel_value function, inlined at its call sites as
    // ((tile << 24) | (y << 12) | x | 32'h00010000).

    task check;
        input condition;
        input [255:0] message;
        begin if (!condition) $fatal(1, "FAIL conv window: %0s", message); end
    endtask

    always @(posedge clk) begin
        if (stalled_last && !flush && resetn)
            check(out_valid && out_data === stalled_data &&
                  out_x == stalled_x && out_y == stalled_y &&
                  out_kx == stalled_kx && out_ky == stalled_ky &&
                  out_tile_id == stalled_tile,
                  "output changed under backpressure");
        stalled_last <= resetn && !flush && out_valid && !out_ready;
        if (out_valid && !out_ready) begin
            stalled_data <= out_data;
            stalled_x <= out_x; stalled_y <= out_y;
            stalled_kx <= out_kx; stalled_ky <= out_ky;
            stalled_tile <= out_tile_id;
        end
        if (checking && out_valid && out_ready) begin : verify_tap
            integer iy, ix;
            reg [31:0] expected_data;
            iy = expected_y * case_stride + expected_ky - case_padding;
            ix = expected_x * case_stride + expected_kx - case_padding;
            expected_data = (iy < 0 || ix < 0 ||
                             iy >= case_height || ix >= case_width) ?
                            32'b0 : ((case_tile << 24) | (iy << 12) | ix | 32'h00010000);
            check(out_y == expected_y && out_x == expected_x &&
                  out_ky == expected_ky && out_kx == expected_kx,
                  "wrong window coordinates");
            if (out_data !== expected_data)
                $display("WINDOW_MISMATCH xy=%0d,%0d kxy=%0d,%0d data=%h expected=%h input=%0d",
                         out_x, out_y, out_kx, out_ky, out_data,
                         expected_data, input_beats);
            check(out_data === expected_data, "wrong window tap");
            check(out_tile_id == case_tile, "wrong channel tile");
            seen_outputs = seen_outputs + 1;
            if (expected_kx + 1 < case_kernel)
                expected_kx = expected_kx + 1;
            else begin
                expected_kx = 0;
                if (expected_ky + 1 < case_kernel)
                    expected_ky = expected_ky + 1;
                else begin
                    expected_ky = 0;
                    if (expected_x + 1 < case_out_w)
                        expected_x = expected_x + 1;
                    else begin
                        expected_x = 0;
                        expected_y = expected_y + 1;
                    end
                end
            end
        end
    end

    task run_case;
        input integer width, height, kernel, stride, padding, tile;
        integer sent, timeout, y, x, start_cycle, pending;
        begin
            case_width = width; case_height = height;
            case_kernel = kernel; case_stride = stride;
            case_padding = padding; case_tile = tile;
            case_out_w = (width + 2 * padding - kernel) / stride + 1;
            case_out_h = (height + 2 * padding - kernel) / stride + 1;
            expected_outputs = case_out_w * case_out_h * kernel * kernel;
            expected_x = 0; expected_y = 0;
            expected_kx = 0; expected_ky = 0;
            seen_outputs = 0;
            @(negedge clk);
            start_cycle = cycle_count;
            check(cfg_ready, "config not ready");
            cfg_width = width; cfg_height = height;
            cfg_kernel = kernel; cfg_stride = stride;
            cfg_padding = padding; cfg_tile_id = tile;
            cfg_valid = 1;
            @(negedge clk); cfg_valid = 0; checking = 1;
            sent = 0;
            pending = 0;
            timeout = 0;
            while (sent < width * height) begin
                y = sent / width;
                x = sent % width;
                if (!pending) begin
                    in_data = ((tile << 24) | (y << 12) | x | 32'h00010000);
                    in_valid = (timeout % 5 != 2);
                end
                out_ready = (timeout % 7 != 3 && timeout % 7 != 4);
                #1;
                if (in_valid && in_ready) begin
                    sent = sent + 1;
                    pending = 0;
                end else
                    pending = in_valid;
                @(negedge clk);
                timeout = timeout + 1;
                if (timeout > 100000) $fatal(1, "input timeout");
            end
            in_valid = 0;
            while (!done) begin
                out_ready = (timeout % 7 != 3 && timeout % 7 != 4);
                @(negedge clk);
                timeout = timeout + 1;
                if (timeout > 100000) $fatal(1, "output timeout");
            end
            #1;
            check(seen_outputs == expected_outputs, "wrong output count");
            check(input_beats == width * height, "source byte count wrong");
            check(output_beats == expected_outputs, "tap count wrong");
            check(!error, "unexpected descriptor error");
            check(cycle_count - start_cycle >= expected_outputs,
                  "cycle counter shorter than output transfer");
            checking = 0;
            out_ready = 0;
            $display("WINDOW_CASE_PASS k=%0d stride=%0d pad=%0d input=%0d taps=%0d stalls=%0d cycles=%0d",
                     kernel, stride, padding, input_beats, output_beats,
                     stall_cycles, cycle_count - start_cycle);
        end
    endtask

    task reject_case;
        input integer width, height, kernel, stride, padding;
        begin
            @(negedge clk);
            cfg_width = width; cfg_height = height;
            cfg_kernel = kernel; cfg_stride = stride;
            cfg_padding = padding; cfg_valid = 1;
            @(negedge clk);
            #1;
            check(error && cfg_ready && !in_ready && !out_valid,
                  "invalid descriptor accepted");
            cfg_valid = 0;
        end
    endtask

    initial begin
        for (row_idx = 0; row_idx < 512; row_idx = row_idx + 1) begin
            force dut.in_y = row_idx[8:0];
            #1;
            if (dut.row_mod6_in_y !== row_idx % 6)
                $fatal(1, "row_mod6 mismatch row=%0d result=%0d",
                       row_idx, dut.row_mod6_in_y);
        end
        release dut.in_y;
        repeat (3) @(negedge clk);
        resetn = 1;
        run_case(4, 3, 1, 1, 0, 1);
        run_case(5, 5, 1, 2, 0, 2);
        run_case(4, 4, 3, 1, 1, 3);
        run_case(5, 6, 3, 2, 1, 4);
        run_case(7, 7, 6, 2, 2, 5);
        run_case(6, 6, 6, 1, 0, 10);
        run_case(16, 7, 6, 1, 2, 6);
        run_case(2, 2, 3, 1, 1, 7);
        // Force a pending padded output while the consumer is stalled, then
        // abort it and immediately accept a new descriptor.
        @(negedge clk);
        cfg_width = 4; cfg_height = 4; cfg_kernel = 3;
        cfg_stride = 1; cfg_padding = 1; cfg_tile_id = 8;
        cfg_valid = 1;
        @(negedge clk);
        cfg_valid = 0;
        out_ready = 0;
        in_valid = 1;
        in_data = ((8 << 24) | (0 << 12) | 0 | 32'h00010000);
        repeat (8) begin
            @(negedge clk);
            in_data = ((8 << 24) | ((input_beats / 4) << 12) | (input_beats % 4) | 32'h00010000);
        end
        in_valid = 0;
        wait (out_valid);
        @(negedge clk);
        flush = 1;
        #1;
        check(!out_valid && !in_ready && !cfg_ready,
              "flush exposed a transfer");
        @(negedge clk);
        flush = 0;
        #1;
        check(cfg_ready && !out_valid && input_beats == 0 &&
              output_beats == 0 && stall_cycles == 0,
              "flush did not reset state and counters");
        run_case(4, 3, 1, 1, 0, 9);
        reject_case(4, 4, 2, 1, 0);
        reject_case(0, 4, 3, 1, 1);
        reject_case(17, 4, 3, 1, 1);
        reject_case(4, 4, 3, 3, 1);
        reject_case(4, 4, 3, 1, 3);
        reject_case(3, 3, 6, 1, 0);
        reject_case(4, 4, 1, 1, 1);
        $display("MAC_CONV_WINDOW_PASS");
        $finish;
    end
endmodule
