// One output pixel at a time: collect its logical S8 activations, then
// consume four flattened inputs per 1024-bit weight row. Each row holds
// 32 output channels x four S8 weights; this first compute tile uses up to
// 16 output channels. A 2x4 PE tile consumes four input lanes and updates
// two output channels per cycle.
module mac_conv_compute_core (
    input wire clk,
    input wire resetn,
    input wire start,
    input wire abort,
    output wire start_ready,
    input wire [8:0] width,
    input wire [8:0] height,
    input wire [15:0] channels,
    input wire [15:0] output_channels,
    input wire [2:0] kernel,
    input wire [1:0] stride,
    input wire [2:0] padding,
    input wire [5:0] weight_lines,
    input wire [511:0] quant_bias,
    input wire [79:0] quant_shift,
    input wire tap_valid,
    output wire tap_ready,
    input wire [31:0] tap_data,
    input wire [8:0] tap_x,
    input wire [8:0] tap_y,
    input wire [2:0] tap_kx,
    input wire [2:0] tap_ky,
    input wire [7:0] tap_tile,
    output wire weight_read_en,
    output wire [4:0] weight_read_addr,
    input wire weight_read_valid,
    input wire [1023:0] weight_read_data,
    output wire out_valid,
    input wire out_ready,
    output wire [7:0] out_data,
    output wire out_last,
    output reg done,
    output reg error,
    output reg [31:0] cycles
);
    localparam S_IDLE=3'd0,S_CAPTURE=3'd1,S_WREQ=3'd2,
               S_WWAIT=3'd3,S_MAC=3'd4,S_OUTPUT=3'd5;
    reg [2:0] state;
    reg [7:0] activation_bank0[0:31];
    reg [7:0] activation_bank1[0:31];
    reg [7:0] activation_bank2[0:31];
    reg [7:0] activation_bank3[0:31];
    reg signed [31:0] acc_even[0:7],acc_odd[0:7];
    reg [7:0] scalar_count;
    reg [4:0] row_index;
    reg [3:0] oc_base,out_channel;
    reg [8:0] width_r,height_r;
    // Public 16-bit dimensions are validated before narrowing internal state.
    reg [2:0] channels_r;
    reg [4:0] output_channels_r;
    reg [7:0] scalar_goal_r;
    reg [2:0] kernel_r,padding_r;
    reg [1:0] stride_r;
    reg [5:0] weight_lines_r;
    reg [511:0] quant_bias_r;
    reg [79:0] quant_shift_r;
    reg [511:0] weight_row;
    reg pixel_last;
    integer lane,channel;

    wire [10:0] span_width = {2'b0,width_r} + ({8'b0,padding_r} << 1) - kernel_r;
    wire [10:0] span_height = {2'b0,height_r} + ({8'b0,padding_r} << 1) - kernel_r;
    wire [8:0] output_width = (stride_r == 2 ? span_width >> 1 : span_width) + 1'b1;
    wire [8:0] output_height = (stride_r == 2 ? span_height >> 1 : span_height) + 1'b1;
    // Cin <= 4 and k in {1,3,6}: the flattened count fits eight bits.
    // Retain full-width range checks so invalid high bits cannot alias a tile.
    wire [7:0] cfg_cin_small = {5'b0,channels[2:0]};
    wire [7:0] cfg_scalar_goal = kernel == 1 ? cfg_cin_small :
        kernel == 3 ? (cfg_cin_small << 3) + cfg_cin_small :
                      (cfg_cin_small << 5) + (cfg_cin_small << 2);
    wire [7:0] cfg_weight_lines = (cfg_scalar_goal + 8'd3) >> 2;
    wire valid_config = width != 0 && height != 0 &&
                        channels != 0 && channels <= 4 &&
                        output_channels != 0 && output_channels <= 16 &&
                        (kernel == 1 || kernel == 3 || kernel == 6) &&
                        (stride == 1 || stride == 2) &&
                        padding < kernel &&
                        width + 2*padding >= kernel &&
                        height + 2*padding >= kernel &&
                        cfg_scalar_goal <= 128 &&
                        weight_lines == cfg_weight_lines;
    wire [6:0] scalar_base = {row_index,2'b0};
    wire [31:0] act_word = {
        scalar_base+3 < scalar_count ? activation_bank3[row_index] : 8'b0,
        scalar_base+2 < scalar_count ? activation_bank2[row_index] : 8'b0,
        scalar_base+1 < scalar_count ? activation_bank1[row_index] : 8'b0,
        scalar_base   < scalar_count ? activation_bank0[row_index]   : 8'b0
    };
    wire [31:0] bias_selected = quant_bias_r[out_channel*32 +: 32];
    wire [4:0] shift_selected = quant_shift_r[out_channel*5 +: 5];
    wire [63:0] weight_pair = weight_row[{oc_base[3:1],6'b0} +: 64];
    wire signed [31:0] out_acc = out_channel[0] ? acc_odd[out_channel[3:1]] :
                                                  acc_even[out_channel[3:1]];
    wire signed [32:0] biased = $signed({out_acc[31],out_acc}) +
                                $signed({bias_selected[31],bias_selected});

    // Former dot4 function: four signed 8x8 products sign-extended and
    // summed, precomputed for the two weight half-words used in S_MAC.
    reg signed [15:0] dot4_lo_p0,dot4_lo_p1,dot4_lo_p2,dot4_lo_p3;
    reg signed [31:0] dot4_lo;
    always @* begin
        dot4_lo_p0=$signed(act_word[7:0])*$signed(weight_pair[7:0]);
        dot4_lo_p1=$signed(act_word[15:8])*$signed(weight_pair[15:8]);
        dot4_lo_p2=$signed(act_word[23:16])*$signed(weight_pair[23:16]);
        dot4_lo_p3=$signed(act_word[31:24])*$signed(weight_pair[31:24]);
        dot4_lo={{16{dot4_lo_p0[15]}},dot4_lo_p0}+
               {{16{dot4_lo_p1[15]}},dot4_lo_p1}+
               {{16{dot4_lo_p2[15]}},dot4_lo_p2}+
               {{16{dot4_lo_p3[15]}},dot4_lo_p3};
    end
    reg signed [15:0] dot4_hi_p0,dot4_hi_p1,dot4_hi_p2,dot4_hi_p3;
    reg signed [31:0] dot4_hi;
    always @* begin
        dot4_hi_p0=$signed(act_word[7:0])*$signed(weight_pair[39:32]);
        dot4_hi_p1=$signed(act_word[15:8])*$signed(weight_pair[47:40]);
        dot4_hi_p2=$signed(act_word[23:16])*$signed(weight_pair[55:48]);
        dot4_hi_p3=$signed(act_word[31:24])*$signed(weight_pair[63:56]);
        dot4_hi={{16{dot4_hi_p0[15]}},dot4_hi_p0}+
               {{16{dot4_hi_p1[15]}},dot4_hi_p1}+
               {{16{dot4_hi_p2[15]}},dot4_hi_p2}+
               {{16{dot4_hi_p3[15]}},dot4_hi_p3};
    end


    // Former requant function as a combinational block.
    reg signed [33:0] requant_magnitude,requant_rounded;
    reg [7:0] requant_out;
    always @* begin
        requant_magnitude = biased < 0 ?
            -$signed({biased[32],biased}) : $signed({biased[32],biased});
        if (shift_selected != 0)
            requant_magnitude =
                (requant_magnitude + (34'sd1 << (shift_selected-1))) >>>
                shift_selected;
        requant_rounded = biased < 0 ? -requant_magnitude :
            requant_magnitude;
        if (requant_rounded > 34'sd127) requant_out=8'h7f;
        else if (requant_rounded < -34'sd128) requant_out=8'h80;
        else requant_out=requant_rounded[7:0];
    end


    assign start_ready = state == S_IDLE && resetn;
    assign tap_ready = state == S_CAPTURE && resetn;
    assign weight_read_en = state == S_WREQ;
    assign weight_read_addr = row_index;
    assign out_valid = state == S_OUTPUT;
    assign out_data = requant_out;
    assign out_last = pixel_last && out_channel+1 == output_channels_r;

    // Consecutive 1..4 bytes touch each modulo-four bank at most once.
    // Reconstruct the flattened row with four parallel reads. No cycles added.
    wire activation_capture = resetn && !abort && state == S_CAPTURE &&
        tap_valid && tap_ready && tap_tile == 0 && scalar_count + channels_r <= 128;
    wire [1:0] bank0_lane = 2'd0 - scalar_count[1:0];
    wire [4:0] bank0_write_row = scalar_count[6:2] + (scalar_count[1:0] > 2'd0);
    always @(posedge clk) if (activation_capture && bank0_lane < channels_r)
        activation_bank0[bank0_write_row] <= tap_data[bank0_lane*8 +: 8];
    wire [1:0] bank1_lane = 2'd1 - scalar_count[1:0];
    wire [4:0] bank1_write_row = scalar_count[6:2] + (scalar_count[1:0] > 2'd1);
    always @(posedge clk) if (activation_capture && bank1_lane < channels_r)
        activation_bank1[bank1_write_row] <= tap_data[bank1_lane*8 +: 8];
    wire [1:0] bank2_lane = 2'd2 - scalar_count[1:0];
    wire [4:0] bank2_write_row = scalar_count[6:2] + (scalar_count[1:0] > 2'd2);
    always @(posedge clk) if (activation_capture && bank2_lane < channels_r)
        activation_bank2[bank2_write_row] <= tap_data[bank2_lane*8 +: 8];
    wire [1:0] bank3_lane = 2'd3 - scalar_count[1:0];
    wire [4:0] bank3_write_row = scalar_count[6:2] + (scalar_count[1:0] > 2'd3);
    always @(posedge clk) if (activation_capture && bank3_lane < channels_r)
        activation_bank3[bank3_write_row] <= tap_data[bank3_lane*8 +: 8];

    always @(posedge clk) begin
        if (!resetn) begin
            state<=S_IDLE;scalar_count<=0;row_index<=0;
            oc_base<=0;out_channel<=0;weight_row<=0;pixel_last<=0;
            width_r<=0;height_r<=0;channels_r<=0;output_channels_r<=0;scalar_goal_r<=0;
            kernel_r<=0;stride_r<=0;padding_r<=0;weight_lines_r<=0;
            quant_bias_r<=0;quant_shift_r<=0;
            cycles<=0;done<=0;error<=0;
            for (channel=0;channel<8;channel=channel+1) begin
                acc_even[channel]<=0;acc_odd[channel]<=0;
            end
        end else if (abort) begin
            state<=S_IDLE;done<=0;error<=0;
        end else begin
            done<=0;error<=0;
            if (state != S_IDLE && cycles != 32'hffff_ffff) cycles<=cycles+1;
            case (state)
                S_IDLE: if (start) begin
                    cycles<=0;
                    if (!valid_config) error<=1;
                    else begin
                        width_r<=width;height_r<=height;
                        channels_r<=channels[2:0];output_channels_r<=output_channels[4:0];
                        scalar_goal_r<=cfg_scalar_goal;
                        kernel_r<=kernel;stride_r<=stride;padding_r<=padding;
                        weight_lines_r<=weight_lines;
                        quant_bias_r<=quant_bias;quant_shift_r<=quant_shift;
                        scalar_count<=0;row_index<=0;oc_base<=0;
                        out_channel<=0;pixel_last<=0;
                        for (channel=0;channel<8;channel=channel+1) begin
                            acc_even[channel]<=0;acc_odd[channel]<=0;
                        end
                        state<=S_CAPTURE;
                    end
                end
                S_CAPTURE: if (tap_valid && tap_ready) begin
                    if (tap_tile != 0 || scalar_count+channels_r > 128) begin
                        error<=1;state<=S_IDLE;
                    end else begin
                        // Four independent bank write ports capture these bytes.
                        scalar_count<=scalar_count+channels_r;
                        if (tap_kx+1 == kernel_r && tap_ky+1 == kernel_r) begin
                            if (scalar_count+channels_r != scalar_goal_r) begin
                                error<=1;state<=S_IDLE;
                            end else begin
                                pixel_last <= tap_x+1 == output_width &&
                                              tap_y+1 == output_height;
                                row_index<=0;oc_base<=0;state<=S_WREQ;
                            end
                        end
                    end
                end
                S_WREQ: state<=S_WWAIT;
                S_WWAIT: if (weight_read_valid) begin
                    weight_row<=weight_read_data[511:0];
                    oc_base<=0;
                    state<=S_MAC;
                end
                S_MAC: begin
                    if (oc_base < output_channels_r)
                        acc_even[oc_base[3:1]] <= acc_even[oc_base[3:1]] +
                            dot4_lo;
                    if (oc_base+1 < output_channels_r)
                        acc_odd[oc_base[3:1]] <= acc_odd[oc_base[3:1]] +
                            dot4_hi;
                    if (oc_base+2 >= output_channels_r) begin
                        oc_base<=0;
                        if (row_index+1 == weight_lines_r) begin
                            out_channel<=0;state<=S_OUTPUT;
                        end else begin
                            row_index<=row_index+1'b1;
                            state<=S_WREQ;
                        end
                    end else oc_base<=oc_base+4'd2;
                end
                S_OUTPUT: if (out_ready) begin
                    if (out_channel+1 == output_channels_r) begin
                        if (pixel_last) begin
                            done<=1;state<=S_IDLE;
                        end else begin
                            scalar_count<=0;row_index<=0;oc_base<=0;
                            out_channel<=0;
                            for (channel=0;channel<8;channel=channel+1) begin
                                acc_even[channel]<=0;acc_odd[channel]<=0;
                            end
                            state<=S_CAPTURE;
                        end
                    end else out_channel<=out_channel+1'b1;
                end
                default: state<=S_IDLE;
            endcase
        end
    end
endmodule
