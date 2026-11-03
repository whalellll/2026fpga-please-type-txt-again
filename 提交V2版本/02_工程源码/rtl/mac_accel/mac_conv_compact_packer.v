// Packs a continuous S8 output stream into aligned DDR words. The final word
// carries only the valid byte lanes, so Cout need not be divisible by four.
module mac_conv_compact_packer (
    input wire clk,
    input wire resetn,
    input wire start,
    input wire abort,
    output wire start_ready,
    input wire [31:0] base_addr,
    input wire [31:0] total_bytes,
    input wire byte_valid,
    output wire byte_ready,
    input wire [7:0] byte_data,
    input wire byte_last,
    output wire word_valid,
    input wire word_ready,
    output reg [31:0] word_addr,
    output reg [31:0] word_data,
    output reg [3:0] word_strb,
    output reg done,
    output reg error,
    output reg [31:0] output_ddr_bytes
);
    localparam S_IDLE=2'd0,S_FILL=2'd1,S_WORD=2'd2;
    reg [1:0] state;
    reg [31:0] base_r,total_r,byte_count,word_count,pack_data;
    reg [1:0] lane_count;
    reg [2:0] pending_bytes;
    reg pending_last;

    assign start_ready = state == S_IDLE && resetn;
    assign byte_ready = state == S_FILL && byte_count < total_r;
    assign word_valid = state == S_WORD;

    always @(posedge clk) begin
        if (!resetn) begin
            state<=S_IDLE;base_r<=0;total_r<=0;
            byte_count<=0;word_count<=0;pack_data<=0;lane_count<=0;
            pending_bytes<=0;pending_last<=0;
            word_addr<=0;word_data<=0;word_strb<=0;
            output_ddr_bytes<=0;done<=0;error<=0;
        end else if (abort) begin
            state<=S_IDLE;done<=0;error<=0;
        end else begin
            done<=0;error<=0;
            case (state)
                S_IDLE: if (start) begin
                    output_ddr_bytes<=0;
                    if (base_addr[1:0] != 0 || total_bytes == 0) error<=1;
                    else begin
                        base_r<=base_addr;total_r<=total_bytes;
                        byte_count<=0;word_count<=0;
                        pack_data<=0;lane_count<=0;
                        state<=S_FILL;
                    end
                end
                S_FILL: if (byte_valid && byte_ready) begin
                    if (byte_last != (byte_count+1 == total_r)) begin
                        error<=1;state<=S_IDLE;
                    end else begin
                        byte_count<=byte_count+1'b1;
                        if (lane_count == 3 || byte_last) begin
                            word_addr<=base_r + (word_count << 2);
                            word_data<=pack_data |
                                       ({24'b0,byte_data} << (lane_count*8));
                            case (lane_count)
                                0: word_strb<=4'b0001;
                                1: word_strb<=4'b0011;
                                2: word_strb<=4'b0111;
                                default: word_strb<=4'b1111;
                            endcase
                            pending_bytes<={1'b0,lane_count}+3'd1;
                            pending_last<=byte_last;
                            state<=S_WORD;
                        end else begin
                            pack_data[lane_count*8 +: 8]<=byte_data;
                            lane_count<=lane_count+1'b1;
                        end
                    end
                end
                S_WORD: if (word_ready) begin
                    output_ddr_bytes<=output_ddr_bytes+pending_bytes;
                    if (pending_last) begin
                        done<=1;state<=S_IDLE;
                    end else begin
                        word_count<=word_count+1'b1;
                        pack_data<=0;lane_count<=0;
                        state<=S_FILL;
                    end
                end
                default: state<=S_IDLE;
            endcase
        end
    end
endmodule
