`timescale 1ns / 1ps

// CPU-free top level: software control registers + DMA + MAC + DDR AXI master.
module mac_accel_ddr_kernel_top #(
    parameter [31:0] DDR_BASE = 32'h0000_0000,
    parameter integer DDR_BYTES = 256 * 1024 * 1024,
    parameter integer SPARSE_MODEL_ROWS = 1620,
    parameter integer ENABLE_PFF1_GATHER = 0,
    parameter integer WEIGHT_BANK_LINES = 1024,
    parameter ENABLE_FP8 = 1,
    // v2 platform: the YOLO conv frontend is synthesized out by default.
    // The chess stack uses the dense MAC (Stage B), sparse evaluator and
    // PFF1 gather only; the conv sources stay in the repository.
    parameter integer ENABLE_CONV = 0
) (
    input  wire        clk,
    input  wire        resetn,

    input  wire        reg_wr_en,
    input  wire [8:0]  reg_wr_addr,
    input  wire [31:0] reg_wr_data,
    input  wire [3:0]  reg_wr_strb,
    input  wire [8:0]  reg_rd_addr,
    output wire [31:0] reg_rd_data,
    output wire        irq,

    output wire [31:0] m_axi_awaddr,
    output wire [7:0]  m_axi_awlen,
    output wire [2:0]  m_axi_awsize,
    output wire [1:0]  m_axi_awburst,
    output wire        m_axi_awvalid,
    input  wire        m_axi_awready,
    output wire [31:0] m_axi_wdata,
    output wire [3:0]  m_axi_wstrb,
    output wire        m_axi_wlast,
    output wire        m_axi_wvalid,
    input  wire        m_axi_wready,
    input  wire [1:0]  m_axi_bresp,
    input  wire        m_axi_bvalid,
    output wire        m_axi_bready,

    output wire [31:0] m_axi_araddr,
    output wire [7:0]  m_axi_arlen,
    output wire [2:0]  m_axi_arsize,
    output wire [1:0]  m_axi_arburst,
    output wire        m_axi_arvalid,
    input  wire        m_axi_arready,
    input  wire [31:0] m_axi_rdata,
    input  wire [1:0]  m_axi_rresp,
    input  wire        m_axi_rlast,
    input  wire        m_axi_rvalid,
    output wire        m_axi_rready
);

    wire dma_req_valid, dma_req_ready, dma_req_write;
    wire [31:0] dma_req_addr;
    wire [2:0] dma_req_len;
    wire dma_w_valid, dma_w_ready;
    wire [31:0] dma_w_data;
    wire [3:0] dma_w_strb;
    wire dma_w_last;
    wire dma_rsp_valid, dma_rsp_ready;
    wire [31:0] dma_rsp_rdata;
    wire dma_rsp_last, dma_rsp_error;
    wire dma_irq;

    wire sparse_req_valid, sparse_req_ready, sparse_req_write;
    wire [31:0] sparse_req_addr;
    wire [2:0] sparse_req_len;
    wire sparse_w_valid, sparse_w_ready;
    wire [31:0] sparse_w_data;
    wire [3:0] sparse_w_strb;
    wire sparse_w_last;
    wire sparse_rsp_valid, sparse_rsp_ready;
    wire [31:0] sparse_rsp_rdata;
    wire sparse_rsp_last, sparse_rsp_error;
    wire sparse_irq;

    wire conv_req_valid, conv_req_ready, conv_req_write;
    wire [31:0] conv_req_addr;
    wire [2:0] conv_req_len;
    wire conv_w_valid,conv_w_ready,conv_w_last;
    wire [31:0] conv_w_data;
    wire [3:0] conv_w_strb;
    wire conv_rsp_valid, conv_rsp_ready, conv_rsp_last, conv_rsp_error;
    wire [31:0] conv_rsp_rdata;
    wire conv_abort;
    wire [31:0] conv_reg_rd_data;

    wire mem_req_valid;
    wire mem_req_ready;
    wire mem_req_write;
    wire [31:0] mem_req_addr;
    wire [2:0] mem_req_len;
    wire mem_w_valid;
    wire mem_w_ready;
    wire [31:0] mem_w_data;
    wire [3:0] mem_w_strb;
    wire mem_w_last;
    wire mem_rsp_valid;
    wire mem_rsp_ready;
    wire [31:0] mem_rsp_rdata;
    wire mem_rsp_last;
    wire mem_rsp_error;

    wire [31:0] dma_reg_rd_data;
    wire [31:0] sparse_reg_rd_data;
    wire [31:0] gather_reg_rd_data,gather_req_addr,gather_w_data;
    wire gather_req_valid,gather_req_ready,gather_req_write;
    wire [2:0] gather_req_len;
    wire gather_w_valid,gather_w_ready,gather_w_last,gather_rsp_ready;
    wire [3:0] gather_w_strb;
    // 0 = idle, 1 = legacy dense DMA, 2 = sparse, 3 = stage-2 conv DMA.
    reg [2:0] memory_owner;

    wire choose_dma = dma_req_valid;
    wire choose_conv = !choose_dma && conv_req_valid;
    wire choose_sparse = !choose_dma && !choose_conv && sparse_req_valid;
    wire choose_gather = !choose_dma && !choose_conv && !choose_sparse && gather_req_valid;
    wire abort_conv_owner = memory_owner == 2'd3 && conv_abort;

    assign reg_rd_data = reg_rd_addr[8] ? gather_reg_rd_data :
                         reg_rd_addr[7] ? sparse_reg_rd_data :
                         reg_rd_addr[6] ? conv_reg_rd_data :
                                          dma_reg_rd_data;
    assign irq = dma_irq | sparse_irq;

    // One transaction is outstanding in the AXI adapter.  Lock ownership
    // from command acceptance through the last response beat so the legacy
    // DMA writer and sparse read-only engine can safely share it.
    assign mem_req_valid = memory_owner == 0 &&
                           (choose_dma || choose_conv || choose_sparse || choose_gather);
    assign mem_req_write = choose_dma ? dma_req_write :
                           choose_conv ? conv_req_write :
                           choose_gather ? gather_req_write : 1'b0;
    assign mem_req_addr = ({32{choose_dma}} & dma_req_addr) |
                          ({32{choose_conv}} & conv_req_addr) |
                          ({32{choose_sparse}} & sparse_req_addr) |
                          ({32{choose_gather}} & gather_req_addr);
    assign mem_req_len = ({3{choose_dma}} & dma_req_len) |
                         ({3{choose_conv}} & conv_req_len) |
                         ({3{choose_sparse}} & sparse_req_len) |
                         ({3{choose_gather}} & gather_req_len);
    assign dma_req_ready = memory_owner == 0 && choose_dma && mem_req_ready;
    assign conv_req_ready = memory_owner == 0 && choose_conv && mem_req_ready;
    assign sparse_req_ready = memory_owner == 0 && choose_sparse &&
                              mem_req_ready;
    assign gather_req_ready = memory_owner == 0 && choose_gather && mem_req_ready;

    assign mem_w_valid = memory_owner == 2'd1 ? dma_w_valid :
                         memory_owner == 2'd3 ? conv_w_valid :
                         memory_owner == 3'd4 ? gather_w_valid : 1'b0;
    assign mem_w_data = memory_owner == 3'd4 ? gather_w_data :
                        memory_owner == 2'd3 ? conv_w_data : dma_w_data;
    assign mem_w_strb = memory_owner == 3'd4 ? gather_w_strb :
                        memory_owner == 2'd3 ? conv_w_strb : dma_w_strb;
    assign mem_w_last = memory_owner == 3'd4 ? gather_w_last :
                        memory_owner == 2'd3 ? conv_w_last : dma_w_last;
    assign dma_w_ready = memory_owner == 2'd1 &&
                         mem_w_ready;
    assign conv_w_ready = memory_owner == 2'd3 && mem_w_ready;
    assign sparse_w_ready = 1'b0;
    assign gather_w_ready = memory_owner == 3'd4 && mem_w_ready;

    assign dma_rsp_valid = memory_owner == 2'd1 &&
                           mem_rsp_valid;
    assign sparse_rsp_valid = memory_owner == 2'd2 &&
                              mem_rsp_valid;
    assign conv_rsp_valid = memory_owner == 2'd3 && mem_rsp_valid;
    assign dma_rsp_rdata = mem_rsp_rdata;
    assign sparse_rsp_rdata = mem_rsp_rdata;
    assign conv_rsp_rdata = mem_rsp_rdata;
    assign dma_rsp_last = mem_rsp_last;
    assign sparse_rsp_last = mem_rsp_last;
    assign conv_rsp_last = mem_rsp_last;
    assign dma_rsp_error = mem_rsp_error;
    assign sparse_rsp_error = mem_rsp_error;
    assign conv_rsp_error = mem_rsp_error;
    assign mem_rsp_ready = memory_owner == 2'd1 ? dma_rsp_ready :
                           memory_owner == 2'd2 ? sparse_rsp_ready :
                           memory_owner == 2'd3 ? conv_rsp_ready :
                           memory_owner == 3'd4 ? gather_rsp_ready : 1'b0;

    always @(posedge clk) begin
        if (!resetn) begin
            memory_owner <= 0;
        end else begin
            if (abort_conv_owner) begin
                memory_owner <= 0;
            end else if (memory_owner == 0 && mem_req_valid && mem_req_ready) begin
                memory_owner <= choose_dma ? 3'd1 :
                                choose_conv ? 3'd3 :
                                choose_sparse ? 3'd2 : 3'd4;
            end else if (memory_owner != 0 && mem_rsp_valid &&
                         mem_rsp_ready && mem_rsp_last) begin
                memory_owner <= 0;
            end
        end
    end

    mac_accel_dma_kernel #(
        .DDR_BASE(DDR_BASE),
        .DDR_BYTES(DDR_BYTES),
        .WEIGHT_BANK_LINES(WEIGHT_BANK_LINES),
        .ENABLE_FP8(ENABLE_FP8)
    ) u_dma_kernel (
        .clk(clk),
        .resetn(resetn),
        .reg_wr_en(reg_wr_en && !reg_wr_addr[8] && !reg_wr_addr[7] && !reg_wr_addr[6]),
        .reg_wr_addr(reg_wr_addr[7:0]),
        .reg_wr_data(reg_wr_data),
        .reg_wr_strb(reg_wr_strb),
        .reg_rd_addr(reg_rd_addr[7:0]),
        .reg_rd_data(dma_reg_rd_data),
        .mem_req_valid(dma_req_valid),
        .mem_req_ready(dma_req_ready),
        .mem_req_write(dma_req_write),
        .mem_req_addr(dma_req_addr),
        .mem_req_len(dma_req_len),
        .mem_w_valid(dma_w_valid),
        .mem_w_ready(dma_w_ready),
        .mem_w_data(dma_w_data),
        .mem_w_strb(dma_w_strb),
        .mem_w_last(dma_w_last),
        .mem_rsp_valid(dma_rsp_valid),
        .mem_rsp_ready(dma_rsp_ready),
        .mem_rsp_rdata(dma_rsp_rdata),
        .mem_rsp_last(dma_rsp_last),
        .mem_rsp_error(dma_rsp_error),
        .irq(dma_irq)
    );

    generate if(ENABLE_CONV) begin : g_conv
    mac_conv_mmio_frontend #(
        .DDR_BASE(DDR_BASE),
        .DDR_BYTES(DDR_BYTES)
    ) u_conv (
        .clk(clk),
        .resetn(resetn),
        .reg_wr_en(reg_wr_en && !reg_wr_addr[8] && !reg_wr_addr[7] && reg_wr_addr[6]),
        .reg_wr_addr(reg_wr_addr[7:0]),
        .reg_wr_data(reg_wr_data),
        .reg_wr_strb(reg_wr_strb),
        .reg_rd_addr(reg_rd_addr[7:0]),
        .reg_rd_data(conv_reg_rd_data),
        .mem_req_valid(conv_req_valid),
        .mem_req_ready(conv_req_ready),
        .mem_req_write(conv_req_write),
        .mem_req_addr(conv_req_addr),
        .mem_req_len(conv_req_len),
        .mem_w_valid(conv_w_valid),
        .mem_w_ready(conv_w_ready),
        .mem_w_data(conv_w_data),
        .mem_w_strb(conv_w_strb),
        .mem_w_last(conv_w_last),
        .mem_rsp_valid(conv_rsp_valid),
        .mem_rsp_ready(conv_rsp_ready),
        .mem_rsp_rdata(conv_rsp_rdata),
        .mem_rsp_last(conv_rsp_last),
        .mem_rsp_error(conv_rsp_error),
        .mem_abort(conv_abort),
        .tap_valid(),
        .tap_ready(1'b1),
        .tap_data(),
        .tap_x(),
        .tap_y(),
        .tap_kx(),
        .tap_ky(),
        .tap_tile()
    );
    end else begin : g_no_conv
        assign conv_req_valid=0;
        assign conv_req_write=0;
        assign conv_req_addr=0;
        assign conv_req_len=0;
        assign conv_w_valid=0;
        assign conv_w_data=0;
        assign conv_w_strb=0;
        assign conv_w_last=0;
        assign conv_rsp_ready=0;
        assign conv_abort=0;
        assign conv_reg_rd_data=0;
    end endgenerate

    xiangqi_sparse_eval #(
        .DDR_BASE(DDR_BASE),
        .DDR_BYTES(DDR_BYTES),
        .MODEL_ROWS(SPARSE_MODEL_ROWS)
    ) u_sparse_eval (
        .clk(clk),
        .resetn(resetn),
        .reg_wr_en(reg_wr_en && !reg_wr_addr[8] && reg_wr_addr[7]),
        .reg_wr_addr(reg_wr_addr[7:0]),
        .reg_wr_data(reg_wr_data),
        .reg_wr_strb(reg_wr_strb),
        .reg_rd_addr(reg_rd_addr[7:0]),
        .reg_rd_data(sparse_reg_rd_data),
        .mem_req_valid(sparse_req_valid),
        .mem_req_ready(sparse_req_ready),
        .mem_req_write(sparse_req_write),
        .mem_req_addr(sparse_req_addr),
        .mem_req_len(sparse_req_len),
        .mem_w_valid(sparse_w_valid),
        .mem_w_ready(sparse_w_ready),
        .mem_w_data(sparse_w_data),
        .mem_w_strb(sparse_w_strb),
        .mem_w_last(sparse_w_last),
        .mem_rsp_valid(sparse_rsp_valid),
        .mem_rsp_ready(sparse_rsp_ready),
        .mem_rsp_rdata(sparse_rsp_rdata),
        .mem_rsp_last(sparse_rsp_last),
        .mem_rsp_error(sparse_rsp_error),
        .irq(sparse_irq)
    );

    generate if(ENABLE_PFF1_GATHER) begin : g_pff1
        pff1_stagea_gather #(.SCRATCH_BASE(DDR_BASE),.SCRATCH_BYTES(DDR_BYTES)) u_gather (
            .clk(clk),.resetn(resetn),
            .reg_wr_en(reg_wr_en && reg_wr_addr[8]),
            .reg_wr_addr(reg_wr_addr[7:0]),.reg_wr_data(reg_wr_data),.reg_wr_strb(reg_wr_strb),
            .reg_rd_addr(reg_rd_addr[7:0]),.reg_rd_data(gather_reg_rd_data),
            .mem_req_valid(gather_req_valid),.mem_req_ready(gather_req_ready),
            .mem_req_write(gather_req_write),.mem_req_addr(gather_req_addr),.mem_req_len(gather_req_len),
            .mem_w_valid(gather_w_valid),.mem_w_ready(gather_w_ready),.mem_w_data(gather_w_data),
            .mem_w_strb(gather_w_strb),.mem_w_last(gather_w_last),
            .mem_rsp_valid(memory_owner==3'd4 && mem_rsp_valid),.mem_rsp_ready(gather_rsp_ready),
            .mem_rsp_rdata(mem_rsp_rdata),.mem_rsp_last(mem_rsp_last),.mem_rsp_error(mem_rsp_error)
        );
    end else begin : g_no_pff1
        assign gather_reg_rd_data=0;
        assign gather_req_valid=0;
        assign gather_req_write=0;
        assign gather_req_addr=0;
        assign gather_req_len=0;
        assign gather_w_valid=0;
        assign gather_w_data=0;
        assign gather_w_strb=0;
        assign gather_w_last=0;
        assign gather_rsp_ready=0;
    end endgenerate

    mac_accel_axi_master32 u_ddr_axi (
        .clk(clk),
        .resetn(resetn && !abort_conv_owner),
        .mem_req_valid(mem_req_valid),
        .mem_req_ready(mem_req_ready),
        .mem_req_write(mem_req_write),
        .mem_req_addr(mem_req_addr),
        .mem_req_len(mem_req_len),
        .mem_w_valid(mem_w_valid),
        .mem_w_ready(mem_w_ready),
        .mem_w_data(mem_w_data),
        .mem_w_strb(mem_w_strb),
        .mem_w_last(mem_w_last),
        .mem_rsp_valid(mem_rsp_valid),
        .mem_rsp_ready(mem_rsp_ready),
        .mem_rsp_rdata(mem_rsp_rdata),
        .mem_rsp_last(mem_rsp_last),
        .mem_rsp_error(mem_rsp_error),
        .m_axi_awaddr(m_axi_awaddr),
        .m_axi_awlen(m_axi_awlen),
        .m_axi_awsize(m_axi_awsize),
        .m_axi_awburst(m_axi_awburst),
        .m_axi_awvalid(m_axi_awvalid),
        .m_axi_awready(m_axi_awready),
        .m_axi_wdata(m_axi_wdata),
        .m_axi_wstrb(m_axi_wstrb),
        .m_axi_wlast(m_axi_wlast),
        .m_axi_wvalid(m_axi_wvalid),
        .m_axi_wready(m_axi_wready),
        .m_axi_bresp(m_axi_bresp),
        .m_axi_bvalid(m_axi_bvalid),
        .m_axi_bready(m_axi_bready),
        .m_axi_araddr(m_axi_araddr),
        .m_axi_arlen(m_axi_arlen),
        .m_axi_arsize(m_axi_arsize),
        .m_axi_arburst(m_axi_arburst),
        .m_axi_arvalid(m_axi_arvalid),
        .m_axi_arready(m_axi_arready),
        .m_axi_rdata(m_axi_rdata),
        .m_axi_rresp(m_axi_rresp),
        .m_axi_rlast(m_axi_rlast),
        .m_axi_rvalid(m_axi_rvalid),
        .m_axi_rready(m_axi_rready)
    );

endmodule
