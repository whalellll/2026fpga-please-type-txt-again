`timescale 1ns/1ps

// Read-channel arbiter for the DDR controller's 256-bit native port.
//
// Master 0 is the existing 32-bit CPU/MAC bridge.  Master 1 is the HDMI
// framebuffer fetcher.  The DDR controller has no RREADY input, so ownership
// is locked from AR acceptance through RLAST.  A framebuffer request marked
// urgent wins the next transaction; otherwise simultaneous requests alternate.
module ddr_native_read_arbiter (
    input  wire         clk,
    input  wire         resetn,

    input  wire [27:0]  s0_araddr,
    input  wire         s0_aruser_ap,
    input  wire [3:0]   s0_arid,
    input  wire [3:0]   s0_arlen,
    input  wire         s0_arvalid,
    output wire         s0_arready,
    output wire [255:0] s0_rdata,
    output wire [3:0]   s0_rid,
    output wire         s0_rlast,
    output wire         s0_rvalid,

    input  wire [27:0]  s1_araddr,
    input  wire [3:0]   s1_arid,
    input  wire [3:0]   s1_arlen,
    input  wire         s1_arvalid,
    input  wire         s1_urgent,
    output wire         s1_arready,
    output wire [255:0] s1_rdata,
    output wire [3:0]   s1_rid,
    output wire         s1_rlast,
    output wire         s1_rvalid,

    output wire [27:0]  m_araddr,
    output wire         m_aruser_ap,
    output wire [3:0]   m_arid,
    output wire [3:0]   m_arlen,
    output wire         m_arvalid,
    input  wire         m_arready,
    input  wire [255:0] m_rdata,
    input  wire [3:0]   m_rid,
    input  wire         m_rlast,
    input  wire         m_rvalid
);
    reg active;
    reg owner_fb;
    reg last_owner_fb;
    reg grant_valid;
    reg grant_fb;

    wire pick_fb = s1_arvalid &&
                   (!s0_arvalid || s1_urgent || !last_owner_fb);
    wire pick_bridge = s0_arvalid && !pick_fb;
    wire selected_fb = grant_valid ? grant_fb : pick_fb;
    wire selected_valid = grant_valid
        ? (grant_fb ? s1_arvalid : s0_arvalid)
        : (pick_fb || pick_bridge);

    assign m_araddr    = selected_fb ? s1_araddr : s0_araddr;
    assign m_aruser_ap = selected_fb ? 1'b0      : s0_aruser_ap;
    assign m_arid      = selected_fb ? s1_arid   : s0_arid;
    assign m_arlen     = selected_fb ? s1_arlen  : s0_arlen;
    assign m_arvalid   = !active && selected_valid;

    assign s0_arready = !active && !selected_fb && selected_valid && m_arready;
    assign s1_arready = !active &&  selected_fb && selected_valid && m_arready;

    assign s0_rdata  = m_rdata;
    assign s0_rid    = m_rid;
    assign s0_rlast  = m_rlast;
    assign s0_rvalid = active && !owner_fb && m_rvalid;

    assign s1_rdata  = m_rdata;
    assign s1_rid    = m_rid;
    assign s1_rlast  = m_rlast;
    assign s1_rvalid = active && owner_fb && m_rvalid;

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            active        <= 1'b0;
            owner_fb      <= 1'b0;
            last_owner_fb <= 1'b1;
            grant_valid   <= 1'b0;
            grant_fb      <= 1'b0;
        end else begin
            if (!active && m_arvalid && m_arready) begin
                active        <= 1'b1;
                owner_fb      <= selected_fb;
                last_owner_fb <= selected_fb;
                grant_valid   <= 1'b0;
            end else if (!active && !grant_valid && selected_valid) begin
                grant_valid <= 1'b1;
                grant_fb    <= selected_fb;
            end
            if (active && m_rvalid && m_rlast)
                active <= 1'b0;
        end
    end
endmodule
