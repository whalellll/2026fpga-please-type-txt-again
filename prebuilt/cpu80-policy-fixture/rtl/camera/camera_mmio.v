`timescale 1ns/1ps

// Bootloader-facing camera control/status block.
// Base address: 0x1fe1_2000.  All counters and status inputs are synchronized
// into clk by the integrating top level before they reach this module.
module camera_mmio (
    input  wire        clk,
    input  wire        resetn,
    input  wire [31:0] addr,
    input  wire        wr,
    input  wire [31:0] wdata,
    input  wire [3:0]  wstrb,
    output reg  [31:0] rdata,
    output wire        hit,

    output reg         enable,
    output reg         stop_request,
    output reg         snapshot_hold,
    output reg [255:0] hud_text,
    output reg [2:0]   hud_style,
    output reg         hud_toggle,
    input wire         hud_ack,

    input  wire        cmos1_init_done,
    input  wire        cmos2_init_done,
    input  wire        frame_valid,
    input  wire        writer_busy,
    input  wire        idle,
    input  wire        stopping,
    input  wire        snapshot_ready,
    input  wire        snapshot_buffer,
    input  wire [31:0] snapshot_frame_count,
    input  wire        completed_buffer,
    input  wire        sccb_nack,
    input  wire        frame_error,
    input  wire        ddr_error,
    input  wire [31:0] frame_count,
    input  wire [31:0] dropped_count,
    input  wire [31:0] bad_line_count
);
    assign hit = (addr >= 32'h1fe1_2000) && (addr < 32'h1fe1_2060);
    reg ack_s1,ack_s2;
    wire hud_pending = hud_toggle != ack_s2;
    always @(posedge clk or negedge resetn)
      if(!resetn)begin ack_s1<=0;ack_s2<=0;end
      else begin ack_s1<=hud_ack;ack_s2<=ack_s1;end

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            enable       <= 1'b0;
            stop_request <= 1'b0;
            snapshot_hold <= 1'b0;
            hud_text <= {32{8'h20}};hud_style<=0;hud_toggle<=0;
        end else if (hit && wr && (addr[6:2] == 5'd2) && wstrb[0]) begin
            enable       <= wdata[0];
            stop_request <= wdata[1];
            snapshot_hold <= wdata[2];
        end else if(hit && wr && (&wstrb) && !hud_pending)begin
          case(addr[6:2])
            5'd8:begin hud_style<=wdata[2:0];hud_toggle<=~hud_toggle;end
            5'd12:hud_text[31:0]<=wdata;
            5'd13:hud_text[63:32]<=wdata;
            5'd14:hud_text[95:64]<=wdata;
            5'd15:hud_text[127:96]<=wdata;
            5'd16:hud_text[159:128]<=wdata;
            5'd17:hud_text[191:160]<=wdata;
            5'd18:hud_text[223:192]<=wdata;
            5'd19:hud_text[255:224]<=wdata;
            default:begin end
          endcase
        end
    end

    always @* begin
        rdata = 32'd0;
        if (hit) begin
            case (addr[6:2])
                3'd0: rdata = 32'h4341_4d33; // "CAM3"
                3'd1: rdata = 32'h0001_0003;
                3'd2: rdata = {29'd0, snapshot_hold, stop_request, enable};
                3'd3: rdata = {
                    19'd0,
                    snapshot_buffer,
                    snapshot_ready,
                    ddr_error,
                    frame_error,
                    sccb_nack,
                    completed_buffer,
                    stopping,
                    idle,
                    writer_busy,
                    frame_valid,
                    cmos2_init_done,
                    cmos1_init_done,
                    enable
                };
                3'd4: rdata = frame_count;
                3'd5: rdata = dropped_count;
                3'd6: rdata = bad_line_count;
                3'd7: rdata = snapshot_frame_count;
                5'd8: rdata = {hud_pending,28'd0,hud_style};
                default: rdata = 32'd0;
            endcase
        end
    end
endmodule
