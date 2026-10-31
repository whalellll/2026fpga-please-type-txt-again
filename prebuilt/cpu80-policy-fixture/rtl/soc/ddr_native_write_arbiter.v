`timescale 1ns/1ps

// Write-channel arbiter for the DDR controller's 256-bit native port.
//
// Master 0 is the existing CPU/MAC CDC bridge.  Master 1 is the camera frame
// writer.  The Pango native interface has no WVALID signal: after an AW is
// accepted, WREADY requests each data beat and WUSERO_LAST terminates the
// transaction.  Ownership therefore remains locked from AW acceptance through
// the accepted last write beat.
module ddr_native_write_arbiter (
    input  wire         clk,
    input  wire         resetn,

    input  wire [27:0]  s0_awaddr,
    input  wire         s0_awuser_ap,
    input  wire [3:0]   s0_awid,
    input  wire [3:0]   s0_awlen,
    input  wire         s0_awvalid,
    output wire         s0_awready,
    input  wire [255:0] s0_wdata,
    input  wire [31:0]  s0_wstrb,
    output wire         s0_wready,
    output wire [3:0]   s0_wusero_id,
    output wire         s0_wusero_last,

    input  wire [27:0]  s1_awaddr,
    input  wire [3:0]   s1_awid,
    input  wire [3:0]   s1_awlen,
    input  wire         s1_awvalid,
    input  wire         s1_urgent,
    output wire         s1_awready,
    input  wire [255:0] s1_wdata,
    input  wire [31:0]  s1_wstrb,
    output wire         s1_wready,
    output wire [3:0]   s1_wusero_id,
    output wire         s1_wusero_last,

    output wire [27:0]  m_awaddr,
    output wire         m_awuser_ap,
    output wire [3:0]   m_awid,
    output wire [3:0]   m_awlen,
    output wire         m_awvalid,
    input  wire         m_awready,
    output wire [255:0] m_wdata,
    output wire [31:0]  m_wstrb,
    input  wire         m_wready,
    input  wire [3:0]   m_wusero_id,
    input  wire         m_wusero_last,

    output wire         busy,
    output wire         owner_camera
);
    reg active;
    reg active_camera;
    reg last_owner_camera;
    reg grant_valid;
    reg grant_camera;

    wire pick_camera = s1_awvalid &&
                       (!s0_awvalid || s1_urgent || !last_owner_camera);
    wire pick_bridge = s0_awvalid && !pick_camera;
    wire selected_camera = grant_valid ? grant_camera : pick_camera;
    wire selected_valid = grant_valid
        ? (grant_camera ? s1_awvalid : s0_awvalid)
        : (pick_camera || pick_bridge);

    assign m_awaddr    = selected_camera ? s1_awaddr : s0_awaddr;
    assign m_awuser_ap = selected_camera ? 1'b0      : s0_awuser_ap;
    assign m_awid      = selected_camera ? s1_awid   : s0_awid;
    assign m_awlen     = selected_camera ? s1_awlen  : s0_awlen;
    assign m_awvalid   = !active && selected_valid;

    assign s0_awready = !active && !selected_camera && selected_valid &&
                        m_awready;
    assign s1_awready = !active &&  selected_camera && selected_valid &&
                        m_awready;

    assign m_wdata = active_camera ? s1_wdata : s0_wdata;
    assign m_wstrb = active_camera ? s1_wstrb : s0_wstrb;

    assign s0_wready = active && !active_camera && m_wready;
    assign s1_wready = active &&  active_camera && m_wready;
    assign s0_wusero_id = active && !active_camera ? m_wusero_id : 4'd0;
    assign s1_wusero_id = active &&  active_camera ? m_wusero_id : 4'd0;
    assign s0_wusero_last = active && !active_camera && m_wusero_last;
    assign s1_wusero_last = active &&  active_camera && m_wusero_last;

    assign busy = active;
    assign owner_camera = active && active_camera;

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            active            <= 1'b0;
            active_camera     <= 1'b0;
            last_owner_camera <= 1'b1;
            grant_valid       <= 1'b0;
            grant_camera      <= 1'b0;
        end else begin
            if (!active && m_awvalid && m_awready) begin
                active            <= 1'b1;
                active_camera     <= selected_camera;
                last_owner_camera <= selected_camera;
                grant_valid       <= 1'b0;
            end else if (!active && !grant_valid && selected_valid) begin
                grant_valid  <= 1'b1;
                grant_camera <= selected_camera;
            end

            if (active && m_wready && m_wusero_last)
                active <= 1'b0;
        end
    end
endmodule
