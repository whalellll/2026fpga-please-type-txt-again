`timescale 1ns/1ps

// MMIO slave for the I2S audio duplex, decoded at 0x1fe0_0600..0x1fe0_06ff.
module audio_mmio(
    input  wire        clk,
    input  wire        resetn,
    input  wire [31:0] addr,
    input  wire        wr,
    input  wire [31:0] wdata,
    input  wire [3:0]  wstrb,
    output reg  [31:0] rdata,
    output wire        hit,
    output reg         sample_write,
    output reg  [15:0] sample_data,
    input  wire        fifo_full,
    input  wire [4:0]  fifo_level,
    input  wire [23:0] microphone_sample,
    input  wire [31:0] microphone_count,
    input  wire [31:0] playback_underflows,
    output wire        counter_clear,
    output wire        microphone_read,
    input  wire [23:0] microphone_fifo_data,
    input  wire        microphone_fifo_empty,
    input  wire        microphone_fifo_full,
    input  wire [9:0]  microphone_fifo_level,
    input  wire [31:0] microphone_overflows
);
    reg clear_pulse;
    reg microphone_read_pulse;

    assign hit=(addr>=32'h1fe0_0600)&&(addr<32'h1fe0_0700);
    assign counter_clear=clear_pulse;
    assign microphone_read=microphone_read_pulse;

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            sample_write<=1'b0; sample_data<=16'd0; clear_pulse<=1'b0;
            microphone_read_pulse<=1'b0;
        end else begin
            sample_write<=1'b0; clear_pulse<=1'b0;
            microphone_read_pulse<=1'b0;
            if (wr&&hit) begin
                case (addr[7:2])
                    6'd2: if (wstrb[0]) begin
                              if (wdata[0]) clear_pulse<=1'b1;
                              if (wdata[1]&&!microphone_fifo_empty)
                                  microphone_read_pulse<=1'b1;
                          end
                    6'd3: if (wstrb[0]&&wstrb[1]&&!fifo_full) begin
                              sample_write<=1'b1;
                              sample_data<=wdata[15:0];
                          end
                    default: ;
                endcase
            end
        end
    end

    always @* begin
        case (addr[7:2])
            6'd0: rdata=32'h4155_4431;
            6'd1: rdata=32'h0002_0000;
            6'd4: rdata={23'd0,fifo_full,3'd0,fifo_level};
            6'd5: rdata={8'd0,microphone_sample};
            6'd6: rdata=microphone_count;
            6'd7: rdata=playback_underflows;
            6'd8: rdata={8'd0,microphone_fifo_data};
            6'd9: rdata={6'd0,microphone_fifo_level,14'd0,
                          microphone_fifo_full,microphone_fifo_empty};
            6'd10:rdata=microphone_overflows;
            default: rdata=32'd0;
        endcase
    end
endmodule
