// Small-IO synthesis wrapper. A serial entropy input can affect every
// weight bit; the digest observes every read bit, preventing width pruning.
module mac_weight_pds_top (
    input wire clk,
    input wire resetn,
    input wire entropy,
    output reg [31:0] digest
);
    reg [2:0] state;
    reg [9:0] fill_count;
    reg [5:0] line;
    reg [1023:0] pattern;
    wire load_start_ready, load_ready, load_error;
    wire activate_ready, active_valid, pending_valid;
    wire [63:0] active_model_id;
    wire [31:0] active_generation, active_tile_id, reuse_count;
    wire [5:0] active_lines;
    wire read_valid;
    wire [1023:0] read_data;
    wire load_start = state == 1 && load_start_ready;
    wire load_valid = state == 2 && load_ready;
    wire activate = state == 3 && activate_ready;
    wire read_en = state == 4;
    wire [4:0] read_addr = line[4:0];
    reg [31:0] folded;
    integer i;
    always @* begin
        folded = 0;
        for (i = 0; i < 32; i = i + 1)
            folded = folded ^ read_data[i*32 +: 32];
    end

    mac_weight_double_buffer u_weights (
        .clk(clk), .resetn(resetn),
        .load_start(load_start), .load_start_ready(load_start_ready),
        .load_lines(6'd27), .load_model_id({32'h1234abcd, digest}),
        .load_generation(digest), .load_tile_id({26'b0, line}),
        .load_valid(load_valid), .load_ready(load_ready),
        .load_data(pattern), .load_last(line == 26),
        .load_abort(1'b0), .load_error(load_error),
        .activate(activate), .activate_ready(activate_ready),
        .compute_idle(1'b1), .active_valid(active_valid),
        .active_model_id(active_model_id),
        .active_generation(active_generation),
        .active_tile_id(active_tile_id), .active_lines(active_lines),
        .reuse_count(reuse_count), .window_done(read_valid),
        .read_en(read_en), .read_addr(read_addr),
        .read_valid(read_valid), .read_data(read_data),
        .pending_valid(pending_valid)
    );

    always @(posedge clk) begin
        if (!resetn) begin
            state <= 0;
            fill_count <= 0;
            line <= 0;
            pattern <= 0;
            digest <= 0;
        end else begin
            pattern <= {pattern[1022:0],
                        entropy ^ pattern[1023] ^ pattern[1020]};
            case (state)
                0: if (fill_count == 1023) state <= 1;
                   else fill_count <= fill_count + 1'b1;
                1: if (load_start) begin line <= 0; state <= 2; end
                2: if (load_valid) begin
                    if (line == 26) begin line <= 0; state <= 3; end
                    else line <= line + 1'b1;
                end
                3: if (activate) begin line <= 0; state <= 4; end
                4: begin
                    if (read_valid) digest <= digest ^ folded ^
                                              active_generation ^
                                              active_model_id[31:0] ^
                                              active_tile_id ^ reuse_count;
                    if (line == 27) state <= 1;
                    else line <= line + 1'b1;
                end
                default: state <= 0;
            endcase
        end
    end
endmodule
