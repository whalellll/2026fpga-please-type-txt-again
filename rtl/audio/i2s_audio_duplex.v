`timescale 1ns/1ps

// 16 kHz stereo-frame I2S master for a 24-bit INMP441 microphone and an
// optional MAX98357A playback channel.  The fractional accumulator produces
// a 1.024 MHz BCLK from the 49.5 MHz system clock.
module i2s_audio_duplex #(
    parameter [31:0] ADD_STEP   = 32'd131072,
    parameter [31:0] WRAP_POINT = 32'd3168000,
    parameter integer MIC_FIFO_ADDR_BITS = 9
)(
    input  wire        clk,
    input  wire        resetn,
    input  wire        counter_clear,
    input  wire        mic_sd,
    output reg         i2s_bclk,
    output reg         i2s_ws,
    output reg         amp_sd,
    input  wire        sample_write,
    input  wire [15:0] sample_data,
    output wire        fifo_full,
    output wire [4:0]  fifo_level,
    output reg  [23:0] microphone_sample,
    output reg  [31:0] microphone_count,
    output reg  [31:0] playback_underflows,
    input  wire        microphone_read,
    output wire [23:0] microphone_fifo_data,
    output wire        microphone_fifo_empty,
    output wire        microphone_fifo_full,
    output wire [MIC_FIFO_ADDR_BITS:0] microphone_fifo_level,
    output reg  [31:0] microphone_overflows
);
    localparam integer MIC_FIFO_DEPTH = 1 << MIC_FIFO_ADDR_BITS;
    reg [31:0] phase_accumulator;
    reg [6:0] bit_index;
    reg [23:0] mic_shift;
    reg [15:0] play_shift;
    reg [15:0] fifo [0:15];
    reg [3:0] fifo_write_pointer;
    reg [3:0] fifo_read_pointer;
    reg [4:0] fifo_count;
    reg bclk_rise;
    reg bclk_fall;
    // Synchronous read port permits block-RAM inference. RAM is not reset.
    reg [23:0] microphone_fifo [0:MIC_FIFO_DEPTH-1];
    reg [MIC_FIFO_ADDR_BITS-1:0] microphone_write_pointer;
    reg [MIC_FIFO_ADDR_BITS-1:0] microphone_read_pointer;
    reg [MIC_FIFO_ADDR_BITS:0] microphone_fifo_count;
    reg [23:0] microphone_head_q;
    reg microphone_head_forward;

    wire [32:0] phase_sum = {1'b0,phase_accumulator}+{1'b0,ADD_STEP};
    assign fifo_full = (fifo_count==5'd16);
    assign fifo_level = fifo_count;
    wire fifo_push = sample_write && !fifo_full;
    wire fifo_pop = bclk_rise && (bit_index==7'd0) && (fifo_count!=0);
    wire microphone_capture = bclk_rise && (bit_index==7'd24);
    wire microphone_pop = microphone_read && !microphone_fifo_empty;
    wire microphone_push = microphone_capture &&
                           (!microphone_fifo_full || microphone_pop);
    wire [MIC_FIFO_ADDR_BITS-1:0] microphone_head_address =
        microphone_read_pointer + microphone_pop;
    assign microphone_fifo_empty = (microphone_fifo_count==0);
    assign microphone_fifo_full = (microphone_fifo_count==MIC_FIFO_DEPTH);
    assign microphone_fifo_level = microphone_fifo_count;
    // Empty->one and one->one push/pop must forward the new sample because
    // synchronous RAM returns old data on a same-address write/read edge.
    assign microphone_fifo_data = microphone_fifo_empty ? 24'd0 :
        microphone_head_forward ? microphone_sample : microphone_head_q;
    always @(posedge clk) begin
        microphone_head_q <= microphone_fifo[microphone_head_address];
        if (resetn && !counter_clear && microphone_push)
            microphone_fifo[microphone_write_pointer] <= {mic_shift[22:0],mic_sd};
    end

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            phase_accumulator<=32'd0; i2s_bclk<=1'b0; i2s_ws<=1'b0;
            amp_sd<=1'b0; bit_index<=7'd0; mic_shift<=24'd0;
            play_shift<=16'd0; fifo_write_pointer<=4'd0;
            fifo_read_pointer<=4'd0; fifo_count<=5'd0;
            microphone_sample<=24'd0; microphone_count<=32'd0;
            playback_underflows<=32'd0; bclk_rise<=1'b0; bclk_fall<=1'b0;
            microphone_write_pointer<={MIC_FIFO_ADDR_BITS{1'b0}};
            microphone_read_pointer<={MIC_FIFO_ADDR_BITS{1'b0}};
            microphone_fifo_count<={(MIC_FIFO_ADDR_BITS+1){1'b0}};
            microphone_overflows<=32'd0; microphone_head_forward<=1'b0;
        end else begin
            microphone_head_forward <= !counter_clear && microphone_push &&
                (microphone_fifo_empty || (microphone_pop && microphone_fifo_count==1));
            bclk_rise <= 1'b0;
            bclk_fall <= 1'b0;
            if (phase_sum >= {1'b0,WRAP_POINT}) begin
                phase_accumulator <= phase_sum - {1'b0,WRAP_POINT};
                i2s_bclk <= ~i2s_bclk;
                if (!i2s_bclk) bclk_rise <= 1'b1;
                else bclk_fall <= 1'b1;
            end else begin
                phase_accumulator <= phase_sum[31:0];
            end

            if (counter_clear) begin
                microphone_count <= 32'd0;
                playback_underflows <= 32'd0;
                microphone_write_pointer <= {MIC_FIFO_ADDR_BITS{1'b0}};
                microphone_read_pointer <= {MIC_FIFO_ADDR_BITS{1'b0}};
                microphone_fifo_count <= {(MIC_FIFO_ADDR_BITS+1){1'b0}};
                microphone_overflows <= 32'd0;
            end else begin
                if (microphone_push)
                    microphone_write_pointer <= microphone_write_pointer+1'b1;
                else if (microphone_capture && microphone_fifo_full)
                    microphone_overflows <= microphone_overflows+1'b1;
                if (microphone_pop)
                    microphone_read_pointer <= microphone_read_pointer+1'b1;
                case ({microphone_push,microphone_pop})
                    2'b10: microphone_fifo_count <= microphone_fifo_count+1'b1;
                    2'b01: microphone_fifo_count <= microphone_fifo_count-1'b1;
                    default: microphone_fifo_count <= microphone_fifo_count;
                endcase
            end
            if (fifo_push) begin
                fifo[fifo_write_pointer] <= sample_data;
                fifo_write_pointer <= fifo_write_pointer + 1'b1;
            end
            case ({fifo_push,fifo_pop})
                2'b10:fifo_count <= fifo_count + 1'b1;
                2'b01:fifo_count <= fifo_count - 1'b1;
                default:fifo_count <= fifo_count;
            endcase

            if (bclk_rise) begin
                if ((bit_index>=7'd1)&&(bit_index<=7'd24))
                    mic_shift <= {mic_shift[22:0],mic_sd};
                if (bit_index==7'd24) begin
                    microphone_sample <= {mic_shift[22:0],mic_sd};
                    if (!counter_clear)
                        microphone_count <= microphone_count + 1'b1;
                end
                if (bit_index==7'd63) begin
                    bit_index <= 7'd0;
                    i2s_ws <= 1'b0;
                end else begin
                    bit_index <= bit_index + 1'b1;
                    if (bit_index==7'd31) i2s_ws <= 1'b1;
                end
                if (bit_index==7'd0) begin
                    if (fifo_count!=0) begin
                        play_shift <= fifo[fifo_read_pointer];
                        fifo_read_pointer <= fifo_read_pointer + 1'b1;
                    end else begin
                        play_shift <= 16'd0;
                        if (!counter_clear)
                            playback_underflows <= playback_underflows + 1'b1;
                    end
                end
            end

            if (bclk_fall) begin
                if ((bit_index>=7'd1)&&(bit_index<=7'd16))
                    amp_sd <= play_shift[16-bit_index];
                else if ((bit_index>=7'd33)&&(bit_index<=7'd48))
                    amp_sd <= play_shift[48-bit_index];
                else
                    amp_sd <= 1'b0;
            end
        end
    end
endmodule
