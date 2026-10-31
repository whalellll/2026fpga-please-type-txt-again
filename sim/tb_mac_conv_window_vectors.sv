module tb_mac_conv_window_vectors;
    reg clk = 0;
    always #5 clk = ~clk;
    reg resetn = 0, flush = 0;
    reg cfg_valid = 0, in_valid = 0, out_ready = 0;
    wire cfg_ready, in_ready, out_valid, done, error;
    reg [8:0] cfg_width = 5, cfg_height = 4;
    reg [2:0] cfg_kernel = 3, cfg_padding = 1;
    reg [1:0] cfg_stride = 2;
    reg [7:0] cfg_tile_id = 0;
    reg [31:0] in_data = 0;
    wire [31:0] out_data, input_beats, output_beats, stall_cycles;
    wire [8:0] out_x, out_y;
    wire [2:0] out_kx, out_ky;
    wire [7:0] out_tile_id;
    reg [31:0] source_words [0:39];
    reg [31:0] expected_words [0:107];
    integer checking = 0, tile_now = 0, seen = 0;
    integer ey = 0, ex = 0, eky = 0, ekx = 0;

    mac_conv_window #(.MAX_WIDTH(16)) dut (.*);

    always @(posedge clk) begin
        if (checking && out_valid && out_ready) begin
            if (out_data !== expected_words[tile_now * 54 + seen] ||
                out_tile_id !== tile_now || out_x !== ex || out_y !== ey ||
                out_kx !== ekx || out_ky !== eky)
                $fatal(1, "Python oracle mismatch tile=%0d tap=%0d data=%h expected=%h xy=%0d,%0d kxy=%0d,%0d",
                       tile_now, seen, out_data,
                       expected_words[tile_now * 54 + seen],
                       out_x, out_y, out_kx, out_ky);
            seen = seen + 1;
            if (ekx == 2) begin
                ekx = 0;
                if (eky == 2) begin
                    eky = 0;
                    if (ex == 2) begin
                        ex = 0;
                        ey = ey + 1;
                    end else ex = ex + 1;
                end else eky = eky + 1;
            end else ekx = ekx + 1;
        end
    end

    task run_tile;
        input integer tile;
        integer sent, ticks, pending;
        begin
            @(negedge clk);
            if (!cfg_ready) $fatal(1, "configuration port busy");
            cfg_tile_id = tile;
            cfg_valid = 1;
            @(negedge clk);
            cfg_valid = 0;
            tile_now = tile;
            checking = 1;
            seen = 0; ey = 0; ex = 0; eky = 0; ekx = 0;
            sent = 0; ticks = 0; pending = 0;
            while (sent < 20) begin
                if (!pending) begin
                    in_data = source_words[tile * 20 + sent];
                    in_valid = ticks % 4 != 1;
                end
                out_ready = ticks % 7 != 2 && ticks % 7 != 3;
                #1;
                if (in_valid && in_ready) begin
                    sent = sent + 1;
                    pending = 0;
                end else pending = in_valid;
                @(negedge clk);
                ticks = ticks + 1;
                if (ticks > 2000) $fatal(1, "source timeout");
            end
            in_valid = 0;
            while (!done) begin
                out_ready = ticks % 7 != 2 && ticks % 7 != 3;
                @(negedge clk);
                ticks = ticks + 1;
                if (ticks > 2000) $fatal(1, "output timeout");
            end
            #1;
            if (seen != 54 || input_beats != 20 || output_beats != 54 || error)
                $fatal(1, "wrong tile counts tile=%0d seen=%0d in=%0d out=%0d",
                       tile, seen, input_beats, output_beats);
            checking = 0;
            out_ready = 0;
            $display("WINDOW_PY_ORACLE_TILE_PASS tile=%0d source_bytes=%0d taps=%0d stalls=%0d cycles=%0d",
                     tile, input_beats * 4, output_beats, stall_cycles, ticks);
        end
    endtask

    initial begin
        $readmemh("sim/vectors/yolo_window_source.hex", source_words);
        $readmemh("sim/vectors/yolo_window_expected.hex", expected_words);
        repeat (3) @(negedge clk);
        resetn = 1;
        run_tile(0);
        run_tile(1);
        $display("MAC_CONV_WINDOW_PY_ORACLE_PASS");
        $finish;
    end
endmodule
