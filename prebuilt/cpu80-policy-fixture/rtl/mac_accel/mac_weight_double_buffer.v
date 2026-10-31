`timescale 1ns / 1ps

// Candidate weight tile store for the stage-2 convolution data path.
// One complete tile is read while the other bank accepts the next tile.
// The producer supplies one packed weight line per valid/ready transfer; the
// line format matches MacAccelCore's 1024-bit host weight write port.
module mac_weight_double_buffer #(
    parameter integer DEPTH = 32,
    parameter integer ADDR_WIDTH = 5
) (
    input  wire                    clk,
    input  wire                    resetn,

    input  wire                    load_start,
    output wire                    load_start_ready,
    input  wire [ADDR_WIDTH:0]     load_lines,
    input  wire [63:0]             load_model_id,
    input  wire [31:0]             load_generation,
    input  wire [31:0]             load_tile_id,
    input  wire                    load_valid,
    output wire                    load_ready,
    input  wire [1023:0]           load_data,
    input  wire                    load_last,
    input  wire                    load_abort,
    output reg                     load_error,

    input  wire                    activate,
    output wire                    activate_ready,
    input  wire                    compute_idle,
    output reg                     active_valid,
    output reg  [63:0]             active_model_id,
    output reg  [31:0]             active_generation,
    output reg  [31:0]             active_tile_id,
    output reg  [ADDR_WIDTH:0]     active_lines,
    output reg  [31:0]             reuse_count,
    input  wire                    window_done,

    input  wire                    read_en,
    input  wire [ADDR_WIDTH-1:0]   read_addr,
    output reg                     read_valid,
    output reg  [1023:0]           read_data,
    output wire                    pending_valid
);
    reg [1023:0] bank0 [0:DEPTH-1];
    reg [1023:0] bank1 [0:DEPTH-1];
    reg active_bank;
    reg loading;
    reg pending;
    reg [ADDR_WIDTH:0] write_index;
    reg [ADDR_WIDTH:0] target_lines;
    reg [63:0] target_model_id;
    reg [31:0] target_generation;
    reg [31:0] target_tile_id;
    reg [63:0] pending_model_id;
    reg [31:0] pending_generation;
    reg [31:0] pending_tile_id;
    reg [ADDR_WIDTH:0] pending_lines;

    assign load_start_ready = !loading && !pending && !load_abort;
    assign load_ready = loading && !load_abort;
    assign activate_ready = pending && compute_idle && !read_en && !load_abort;
    assign pending_valid = pending;

    always @(posedge clk) begin
        if (!resetn) begin
            active_bank <= 1'b0;
            active_valid <= 1'b0;
            active_model_id <= 64'b0;
            active_generation <= 32'b0;
            active_tile_id <= 32'b0;
            active_lines <= {(ADDR_WIDTH+1){1'b0}};
            reuse_count <= 32'b0;
            loading <= 1'b0;
            pending <= 1'b0;
            write_index <= {(ADDR_WIDTH+1){1'b0}};
            target_lines <= {(ADDR_WIDTH+1){1'b0}};
            target_model_id <= 64'b0;
            target_generation <= 32'b0;
            target_tile_id <= 32'b0;
            pending_model_id <= 64'b0;
            pending_generation <= 32'b0;
            pending_tile_id <= 32'b0;
            pending_lines <= {(ADDR_WIDTH+1){1'b0}};
            load_error <= 1'b0;
            read_valid <= 1'b0;
            read_data <= 1024'b0;
        end else begin
            load_error <= 1'b0;
            read_valid <= read_en && active_valid &&
                          ({1'b0, read_addr} < active_lines);
            if (read_en && active_valid &&
                ({1'b0, read_addr} < active_lines)) begin
                if (active_bank)
                    read_data <= bank1[read_addr];
                else
                    read_data <= bank0[read_addr];
            end

            if (window_done && active_valid && reuse_count != 32'hffff_ffff)
                reuse_count <= reuse_count + 32'd1;

            if (load_abort) begin
                loading <= 1'b0;
                pending <= 1'b0;
            end else begin
                if (load_start && load_start_ready) begin
                    if (load_lines == 0 || load_lines > DEPTH) begin
                        load_error <= 1'b1;
                    end else begin
                        loading <= 1'b1;
                        write_index <= {(ADDR_WIDTH+1){1'b0}};
                        target_lines <= load_lines;
                        target_model_id <= load_model_id;
                        target_generation <= load_generation;
                        target_tile_id <= load_tile_id;
                    end
                end

                if (load_valid && load_ready) begin
                    if (load_last != (write_index + 1'b1 == target_lines)) begin
                        loading <= 1'b0;
                        load_error <= 1'b1;
                    end else begin
                        if (active_bank)
                            bank0[write_index[ADDR_WIDTH-1:0]] <= load_data;
                        else
                            bank1[write_index[ADDR_WIDTH-1:0]] <= load_data;
                        if (load_last) begin
                            loading <= 1'b0;
                            pending <= 1'b1;
                            pending_lines <= target_lines;
                            pending_model_id <= target_model_id;
                            pending_generation <= target_generation;
                            pending_tile_id <= target_tile_id;
                        end else begin
                            write_index <= write_index + 1'b1;
                        end
                    end
                end

                if (activate && activate_ready) begin
                    active_bank <= !active_bank;
                    active_valid <= 1'b1;
                    active_lines <= pending_lines;
                    active_model_id <= pending_model_id;
                    active_generation <= pending_generation;
                    active_tile_id <= pending_tile_id;
                    reuse_count <= 32'b0;
                    pending <= 1'b0;
                end
            end
        end
    end
endmodule
