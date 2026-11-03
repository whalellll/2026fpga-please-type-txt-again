`timescale 1ns/1ps

// Simulation-only 32-bit AXI RAM used to exercise CPU/DMA sharing without
// the encrypted DDR PHY model. It accepts one read and one write transaction.
module axi_shared_ram #(
    parameter [31:0] BASE = 32'h1b00_0000,
    parameter integer BYTES = 64 * 1024,
    parameter integer PFF1_SYNTHETIC = 0
)(
    input wire clk, input wire resetn,
    input wire [3:0] arid, input wire [31:0] araddr,
    input wire [7:0] arlen, input wire [2:0] arsize,
    input wire [1:0] arburst, input wire arvalid, output wire arready,
    output reg [3:0] rid, output reg [31:0] rdata,
    output reg [1:0] rresp, output reg rlast, output reg rvalid,
    input wire rready,
    input wire [3:0] awid, input wire [31:0] awaddr,
    input wire [7:0] awlen, input wire [2:0] awsize,
    input wire [1:0] awburst, input wire awvalid, output wire awready,
    input wire [3:0] wid, input wire [31:0] wdata,
    input wire [3:0] wstrb, input wire wlast,
    input wire wvalid, output wire wready,
    output reg [3:0] bid, output reg [1:0] bresp,
    output reg bvalid, input wire bready
);
    localparam [1:0] OKAY=2'b00, DECERR=2'b11;
    reg [31:0] memory [0:(BYTES/4)-1];
    reg rd_active; reg [31:0] rd_addr; reg [7:0] rd_left;
    reg [2:0] rd_size; reg [1:0] rd_burst; reg rd_bad;
    reg wr_active; reg [31:0] wr_addr; reg [7:0] wr_left;
    reg [2:0] wr_size; reg [1:0] wr_burst; reg [3:0] wr_id;
    reg wr_bad;
    integer wi;

    wire rd_addr_in_range = (rd_addr >= BASE) &&
                            (rd_addr < BASE + BYTES);
    wire wr_addr_in_range = (wr_addr >= BASE) &&
                            (wr_addr < BASE + BYTES);
    wire [31:0] rd_next_addr = (rd_burst == 2'b01) ?
                               rd_addr + (32'd1 << rd_size) : rd_addr;
    wire [31:0] wr_next_addr = (wr_burst == 2'b01) ?
                               wr_addr + (32'd1 << wr_size) : wr_addr;

    assign arready=!rd_active&&!rvalid;
    assign awready=!wr_active&&!bvalid;
    assign wready=wr_active&&!bvalid;

    always @(posedge clk) begin
        if(!resetn) begin
            rd_active<=0;rd_addr<=0;rd_left<=0;rd_size<=0;rd_burst<=0;
            rd_bad<=0;rid<=0;rdata<=0;rresp<=OKAY;rlast<=0;rvalid<=0;
        end else begin
            if(arvalid&&arready) begin
                rd_active<=1;rd_addr<=araddr;rd_left<=arlen;rd_size<=arsize;
                rd_burst<=arburst;rd_bad<=(arsize!=3'd2)||
                    ((arburst!=2'b00)&&(arburst!=2'b01));rid<=arid;
            end
            if(rd_active&&!rvalid) begin
                rlast<=(rd_left==0);
                if(!rd_bad&&rd_addr_in_range) begin
                    rdata<=memory[(rd_addr-BASE)>>2];rresp<=OKAY;
                end else if(PFF1_SYNTHETIC && rd_addr>=32'h10002000 && rd_addr<32'h10002400) begin
                    rdata<=32'h807fff01;rresp<=OKAY;
                end else if(PFF1_SYNTHETIC && rd_addr>=32'h12f45000 && rd_addr<32'h12f45400) begin
                    rdata<=32'h01020304;rresp<=OKAY;
                end else begin rdata<=0;rresp<=DECERR;end
                rvalid<=1;
            end else if(rvalid&&rready) begin
                rvalid<=0;
                if(rlast) rd_active<=0;
                else begin rd_left<=rd_left-1'b1;
                    rd_addr<=rd_next_addr;end
            end
        end
    end

    always @(posedge clk) begin
        if(!resetn) begin
            wr_active<=0;wr_addr<=0;wr_left<=0;wr_size<=0;wr_burst<=0;
            wr_id<=0;wr_bad<=0;bid<=0;bresp<=OKAY;bvalid<=0;
        end else begin
            if(awvalid&&awready) begin
                wr_active<=1;wr_addr<=awaddr;wr_left<=awlen;wr_size<=awsize;
                wr_burst<=awburst;wr_id<=awid;wr_bad<=(awsize!=3'd2)||
                    ((awburst!=2'b00)&&(awburst!=2'b01));
            end
            if(wvalid&&wready) begin
                wi=(wr_addr-BASE)>>2;
                if(!wr_bad&&wr_addr_in_range&&(wid==wr_id)) begin
                    if(wstrb[0])memory[wi][7:0]<=wdata[7:0];
                    if(wstrb[1])memory[wi][15:8]<=wdata[15:8];
                    if(wstrb[2])memory[wi][23:16]<=wdata[23:16];
                    if(wstrb[3])memory[wi][31:24]<=wdata[31:24];
                end
                if((wr_left==0)||wlast) begin
                    wr_active<=0;bid<=wr_id;
                    bresp<=(wr_bad||!wr_addr_in_range||(wid!=wr_id)||
                        (wlast!=(wr_left==0)))?DECERR:OKAY;bvalid<=1;
                end else begin wr_left<=wr_left-1'b1;
                    wr_addr<=wr_next_addr;end
            end
            if(bvalid&&bready)bvalid<=0;
        end
    end
endmodule
