`timescale 1ns / 1ps

// CPU-free top level: software control registers + DMA + MAC + DDR AXI master.
module mac_accel_ddr_kernel_top #(
    parameter [31:0] DDR_BASE = 32'h0000_0000,
    parameter integer DDR_BYTES = 256 * 1024 * 1024,
    parameter integer SPARSE_MODEL_ROWS = 1620,
    parameter integer ENABLE_H128_SPARSE = 1,
    parameter integer ENABLE_PFF1_GATHER = 0,
    parameter integer ENABLE_NNUE_PIPELINE = 0,
    parameter integer ENABLE_NNUE_BATCH = 0,
    parameter integer PIKAFISH_ONLY = 0,
    parameter integer HALF_OUTPUT = 0,
    parameter integer WEIGHT_BANK_LINES = 1024,
    parameter ENABLE_FP8 = 1,
    // v2 platform: the YOLO conv frontend is synthesized out by default.
    // The chess stack uses the dense MAC (Stage B), sparse evaluator and
    // PFF1 gather only; the conv sources stay in the repository.
    parameter integer ENABLE_VISION32 = 0,
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
    wire nnue_active,nnue_reg_we;
    wire [7:0] nnue_reg_addr;
    wire [31:0] nnue_reg_data,nnue_reg_rd_data,nnue_req_addr;
    wire nnue_req_valid,nnue_req_ready,nnue_rsp_ready;
    wire [2:0] nnue_req_len;
    wire link_input_we,link_weight_we,link_output_valid,link_output_ready;
    wire [10:0] link_input_addr,link_weight_addr;
    wire [63:0] link_input_data;
    wire [4:0] link_weight_word;
    wire [31:0] link_weight_data,link_output_data;
    wire [12:0] link_output_index;
    wire gather_stream_begin,gather_stream_valid,gather_stream_commit,gather_stream_abort,gather_stream_view;
    wire [31:0] gather_stream_tag,gather_stream_data;
    wire [8:0] gather_stream_index;
    wire batch_active,batch_g_we,batch_n_we,gather_busy,conv_busy;
    wire [7:0] batch_g_addr;
    wire [6:0] batch_n_addr,batch_n_read;
    wire [31:0] batch_g_data,batch_n_data,batch_reg_data;
    wire batch_req_valid,batch_req_ready,batch_req_write,batch_w_valid,batch_w_ready,batch_w_last,batch_rsp_ready;
    wire [31:0] batch_req_addr,batch_w_data;
    wire [2:0] batch_req_len;
    wire [3:0] batch_w_strb;
    wire raw_g_req_valid,raw_g_req_write,raw_g_w_valid,raw_g_w_last,raw_g_rsp_ready;
    wire [31:0] raw_g_req_addr,raw_g_w_data,local_rsp_data;
    wire [2:0] raw_g_req_len;
    wire [3:0] raw_g_w_strb;
    wire local_select,local_owned,local_req_ready,local_w_ready,local_rsp_valid,local_rsp_last,local_rsp_error;
    assign gather_req_valid=raw_g_req_valid && !local_select;
    assign gather_req_write=raw_g_req_write;
    assign gather_req_addr=raw_g_req_addr;assign gather_req_len=raw_g_req_len;
    assign gather_w_valid=raw_g_w_valid && !local_owned;
    assign gather_w_data=raw_g_w_data;assign gather_w_strb=raw_g_w_strb;assign gather_w_last=raw_g_w_last;
    assign gather_rsp_ready=raw_g_rsp_ready && !local_owned;
    // 0 = idle, 1 = legacy dense DMA, 2 = sparse, 3 = stage-2 conv DMA.
    reg [2:0] memory_owner;

    wire choose_dma = dma_req_valid;
    wire choose_conv = !choose_dma && conv_req_valid;
    wire choose_sparse = !choose_dma && !choose_conv && sparse_req_valid;
    wire choose_gather = !choose_dma && !choose_conv && !choose_sparse && gather_req_valid;
    wire choose_nnue = !choose_dma && !choose_conv && !choose_sparse && !choose_gather && nnue_req_valid;
    wire choose_batch = !choose_dma && !choose_conv && !choose_sparse && !choose_gather && !choose_nnue && batch_req_valid;
    wire abort_conv_owner = memory_owner == 2'd3 && conv_abort;

    assign reg_rd_data = reg_rd_addr[8] ? (reg_rd_addr[7] ? nnue_reg_rd_data : gather_reg_rd_data) :
                         reg_rd_addr[7] ? sparse_reg_rd_data :
                         reg_rd_addr[6] ? conv_reg_rd_data :
                                          dma_reg_rd_data;
    assign irq = dma_irq | sparse_irq;

    // One transaction is outstanding in the AXI adapter.  Lock ownership
    // from command acceptance through the last response beat so the legacy
    // DMA writer and sparse read-only engine can safely share it.
    assign mem_req_valid = memory_owner == 0 &&
                           (choose_dma || choose_conv || choose_sparse || choose_gather || choose_nnue || choose_batch);
    assign mem_req_write = choose_dma ? dma_req_write :
                           choose_conv ? conv_req_write :
                           choose_gather ? gather_req_write : choose_batch ? batch_req_write : 1'b0;
    assign mem_req_addr = ({32{choose_dma}} & dma_req_addr) |
                          ({32{choose_conv}} & conv_req_addr) |
                          ({32{choose_sparse}} & sparse_req_addr) |
                          ({32{choose_gather}} & gather_req_addr) |
                          ({32{choose_nnue}} & nnue_req_addr) |
                          ({32{choose_batch}} & batch_req_addr);
    assign mem_req_len = ({3{choose_dma}} & dma_req_len) |
                         ({3{choose_conv}} & conv_req_len) |
                         ({3{choose_sparse}} & sparse_req_len) |
                         ({3{choose_gather}} & gather_req_len) |
                         ({3{choose_nnue}} & nnue_req_len) |
                         ({3{choose_batch}} & batch_req_len);
    assign dma_req_ready = memory_owner == 0 && choose_dma && mem_req_ready;
    assign conv_req_ready = memory_owner == 0 && choose_conv && mem_req_ready;
    assign sparse_req_ready = memory_owner == 0 && choose_sparse &&
                              mem_req_ready;
    assign gather_req_ready = memory_owner == 0 && choose_gather && mem_req_ready;
    assign nnue_req_ready = memory_owner == 0 && choose_nnue && mem_req_ready;
    assign batch_req_ready = memory_owner == 0 && choose_batch && mem_req_ready;

    assign mem_w_valid = memory_owner == 2'd1 ? dma_w_valid :
                         memory_owner == 2'd3 ? conv_w_valid :
                         memory_owner == 3'd4 ? gather_w_valid : memory_owner==3'd6 ? batch_w_valid : 1'b0;
    assign mem_w_data = memory_owner==3'd6 ? batch_w_data : memory_owner == 3'd4 ? gather_w_data :
                        memory_owner == 2'd3 ? conv_w_data : dma_w_data;
    assign mem_w_strb = memory_owner==3'd6 ? batch_w_strb : memory_owner == 3'd4 ? gather_w_strb :
                        memory_owner == 2'd3 ? conv_w_strb : dma_w_strb;
    assign mem_w_last = memory_owner==3'd6 ? batch_w_last : memory_owner == 3'd4 ? gather_w_last :
                        memory_owner == 2'd3 ? conv_w_last : dma_w_last;
    assign dma_w_ready = memory_owner == 2'd1 &&
                         mem_w_ready;
    assign conv_w_ready = memory_owner == 2'd3 && mem_w_ready;
    assign sparse_w_ready = 1'b0;
    assign gather_w_ready = memory_owner == 3'd4 && mem_w_ready;
    assign batch_w_ready = memory_owner == 3'd6 && mem_w_ready;

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
                           memory_owner == 3'd4 ? gather_rsp_ready :
                           memory_owner == 3'd5 ? nnue_rsp_ready : memory_owner==3'd6 ? batch_rsp_ready : 1'b0;

    always @(posedge clk) begin
        if (!resetn) begin
            memory_owner <= 0;
        end else begin
            if (abort_conv_owner) begin
                memory_owner <= 0;
            end else if (memory_owner == 0 && mem_req_valid && mem_req_ready) begin
                memory_owner <= choose_dma ? 3'd1 :
                                choose_conv ? 3'd3 :
                                choose_sparse ? 3'd2 : choose_gather ? 3'd4 : choose_nnue ? 3'd5 : 3'd6;
            end else if (memory_owner != 0 && mem_rsp_valid &&
                         mem_rsp_ready && mem_rsp_last) begin
                memory_owner <= 0;
            end
        end
    end

    generate if(!PIKAFISH_ONLY)begin:g_generic_dense
    mac_accel_dma_kernel #(
        .DDR_BASE(DDR_BASE),
        .DDR_BYTES(DDR_BYTES),
        .HALF_OUTPUT(HALF_OUTPUT),.WEIGHT_BANK_LINES(WEIGHT_BANK_LINES),
        .ENABLE_LOCAL_LINK(ENABLE_NNUE_PIPELINE),
        .ENABLE_FP8(ENABLE_FP8)
    ) u_dma_kernel (
        .clk(clk),
        .resetn(resetn),
        .reg_wr_en(nnue_active ? nnue_reg_we : reg_wr_en && !reg_wr_addr[8] && !reg_wr_addr[7] && !reg_wr_addr[6]),
        .reg_wr_addr(nnue_active ? nnue_reg_addr : reg_wr_addr[7:0]),
        .reg_wr_data(nnue_active ? nnue_reg_data : reg_wr_data),
        .reg_wr_strb(nnue_active ? 4'hf : reg_wr_strb),
        .reg_rd_addr(nnue_active ? 8'h0c : reg_rd_addr[7:0]),
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
        .irq(dma_irq),
        .link_input_we(link_input_we),.link_input_addr(link_input_addr),.link_input_data(link_input_data),
        .link_weight_we(link_weight_we),.link_weight_addr(link_weight_addr),.link_weight_word(link_weight_word),.link_weight_data(link_weight_data),
        .link_output_valid(link_output_valid),.link_output_ready(link_output_ready),.link_output_index(link_output_index),.link_output_data(link_output_data)
    );

    end else begin:g_no_generic_dense
        // A different ID prevents the old dense driver from probing this
        // synthesis prototype as if the removed generic engine existed.
        assign dma_reg_rd_data=reg_rd_addr[7:0]==8'h00 ? 32'h50464e31 :
                               reg_rd_addr[7:0]==8'h04 ? 32'h00010000 :
                               reg_rd_addr[7:0]==8'h0c ? 32'h00000006 : 0;
        assign dma_req_valid=0;assign dma_req_write=0;assign dma_req_addr=0;assign dma_req_len=0;
        assign dma_w_valid=0;assign dma_w_data=0;assign dma_w_strb=0;assign dma_w_last=0;
        assign dma_rsp_ready=0;assign dma_irq=0;
        assign link_output_valid=0;assign link_output_index=0;assign link_output_data=0;
    end endgenerate

    generate if(ENABLE_CONV && !ENABLE_VISION32) begin : g_conv
    mac_conv_mmio_frontend #(
        .DDR_BASE(DDR_BASE),
        .DDR_BYTES(DDR_BYTES)
    ) u_conv (
        .clk(clk),
        .resetn(resetn),
        .reg_wr_en(reg_wr_en && !batch_active && !reg_wr_addr[8] && !reg_wr_addr[7] && reg_wr_addr[6]),
        .reg_wr_addr(reg_wr_addr[7:0]),
        .reg_wr_data(reg_wr_data),
        .reg_wr_strb(reg_wr_strb),
        .reg_rd_addr(reg_rd_addr[7:0]),
        .reg_rd_data(conv_reg_rd_data),.busy_out(conv_busy),
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
    end else if(ENABLE_CONV && ENABLE_VISION32)begin:g_vision32
      vision32_layer #(.DDR_BASE(DDR_BASE),.DDR_BYTES(DDR_BYTES)) u_vision32(
        .clk(clk),.resetn(resetn),
        .reg_wr_en(reg_wr_en && !batch_active && !reg_wr_addr[8] && !reg_wr_addr[7] && reg_wr_addr[6]),
        .reg_wr_addr(reg_wr_addr[7:0]),.reg_wr_data(reg_wr_data),.reg_wr_strb(reg_wr_strb),
        .reg_rd_addr(reg_rd_addr[7:0]),.reg_rd_data(conv_reg_rd_data),
        .mem_req_valid(conv_req_valid),.mem_req_ready(conv_req_ready),.mem_req_write(conv_req_write),
        .mem_req_addr(conv_req_addr),.mem_req_len(conv_req_len),
        .mem_w_valid(conv_w_valid),.mem_w_ready(conv_w_ready),.mem_w_data(conv_w_data),
        .mem_w_strb(conv_w_strb),.mem_w_last(conv_w_last),
        .mem_rsp_valid(conv_rsp_valid),.mem_rsp_ready(conv_rsp_ready),.mem_rsp_rdata(conv_rsp_rdata),
        .mem_rsp_last(conv_rsp_last),.mem_rsp_error(conv_rsp_error),.mem_abort(conv_abort),.busy_out(conv_busy));
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
        assign conv_busy=0;
    end endgenerate

    generate if(ENABLE_H128_SPARSE) begin : g_h128
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

    end else begin : g_no_h128
        assign sparse_reg_rd_data=batch_reg_data;
        assign sparse_req_valid=0;
        assign sparse_req_write=0;
        assign sparse_req_addr=0;
        assign sparse_req_len=0;
        assign sparse_w_valid=0;
        assign sparse_w_data=0;
        assign sparse_w_strb=0;
        assign sparse_w_last=0;
        assign sparse_rsp_ready=0;
        assign sparse_irq=0;
    end endgenerate

    generate if(ENABLE_PFF1_GATHER) begin : g_pff1
        pff1_stagea_gather #(.SCRATCH_BASE(DDR_BASE),.SCRATCH_BYTES(DDR_BYTES),.ENABLE_LOCAL_LINK(ENABLE_NNUE_PIPELINE),.ENABLE_EMPTY(ENABLE_NNUE_BATCH)) u_gather (
            .clk(clk),.resetn(resetn),
            .reg_wr_en(batch_active ? batch_g_we : reg_wr_en && reg_wr_addr[8] && !reg_wr_addr[7]),
            .reg_wr_addr(batch_active ? batch_g_addr : reg_wr_addr[7:0]),.reg_wr_data(batch_active?batch_g_data:reg_wr_data),.reg_wr_strb(batch_active?4'hf:reg_wr_strb),
            .reg_rd_addr(batch_active?8'h0c:reg_rd_addr[7:0]),.reg_rd_data(gather_reg_rd_data),.busy_out(gather_busy),
            .mem_req_valid(raw_g_req_valid),.mem_req_ready(local_select?local_req_ready:gather_req_ready),
            .mem_req_write(raw_g_req_write),.mem_req_addr(raw_g_req_addr),.mem_req_len(raw_g_req_len),
            .mem_w_valid(raw_g_w_valid),.mem_w_ready(local_owned?local_w_ready:gather_w_ready),.mem_w_data(raw_g_w_data),
            .mem_w_strb(raw_g_w_strb),.mem_w_last(raw_g_w_last),
            .mem_rsp_valid(local_owned?local_rsp_valid:memory_owner==3'd4 && mem_rsp_valid),.mem_rsp_ready(raw_g_rsp_ready),
            .mem_rsp_rdata(local_owned?local_rsp_data:mem_rsp_rdata),.mem_rsp_last(local_owned?local_rsp_last:mem_rsp_last),.mem_rsp_error(local_owned?local_rsp_error:mem_rsp_error),
            .stream_begin(gather_stream_begin),.stream_valid(gather_stream_valid),.stream_commit(gather_stream_commit),
            .stream_abort(gather_stream_abort),.stream_view(gather_stream_view),.stream_tag(gather_stream_tag),
            .stream_data(gather_stream_data),.stream_index(gather_stream_index)
        );
    end else begin : g_no_pff1
        assign gather_stream_begin=0;assign gather_stream_valid=0;assign gather_stream_commit=0;
        assign gather_stream_abort=0;assign gather_stream_view=0;assign gather_stream_tag=0;
        assign gather_stream_data=0;assign gather_stream_index=0;
        assign gather_reg_rd_data=0;
        assign gather_busy=0;
        assign raw_g_req_valid=0;
        assign raw_g_req_write=0;
        assign raw_g_req_addr=0;
        assign raw_g_req_len=0;
        assign raw_g_w_valid=0;
        assign raw_g_w_data=0;
        assign raw_g_w_strb=0;
        assign raw_g_w_last=0;
        assign raw_g_rsp_ready=0;
    end endgenerate

    generate if(ENABLE_NNUE_PIPELINE)begin:g_nnue
        nnue_pipeline_frontend #(.DDR_BASE(DDR_BASE),.DDR_BYTES(DDR_BYTES),.PIKAFISH_ONLY(PIKAFISH_ONLY)) u_nnue(
            .clk(clk),.resetn(resetn),.reg_wr_en(batch_active?batch_n_we:reg_wr_en && reg_wr_addr[8] && reg_wr_addr[7]),
            .reg_wr_addr(batch_active?batch_n_addr:reg_wr_addr[6:0]),.reg_rd_addr(batch_active?batch_n_read:reg_rd_addr[6:0]),
            .reg_wr_data(batch_active?batch_n_data:reg_wr_data),.reg_wr_strb(batch_active?4'hf:reg_wr_strb),.reg_rd_data(nnue_reg_rd_data),
            .gather_begin(gather_stream_begin),.gather_valid(gather_stream_valid),.gather_commit(gather_stream_commit),
            .gather_abort(gather_stream_abort),.gather_view(gather_stream_view),.gather_tag(gather_stream_tag),
            .gather_data(gather_stream_data),.gather_index(gather_stream_index),.active(nnue_active),
            .mac_reg_we(nnue_reg_we),.mac_reg_addr(nnue_reg_addr),.mac_reg_data(nnue_reg_data),.mac_status(dma_reg_rd_data),
            .link_input_we(link_input_we),.link_input_addr(link_input_addr),.link_input_data(link_input_data),
            .link_weight_we(link_weight_we),.link_weight_addr(link_weight_addr),.link_weight_word(link_weight_word),.link_weight_data(link_weight_data),
            .link_output_valid(link_output_valid),.link_output_ready(link_output_ready),.link_output_index(link_output_index),.link_output_data(link_output_data),
            .mem_req_valid(nnue_req_valid),.mem_req_ready(nnue_req_ready),.mem_req_addr(nnue_req_addr),.mem_req_len(nnue_req_len),
            .mem_rsp_valid(memory_owner==3'd5 && mem_rsp_valid),.mem_rsp_ready(nnue_rsp_ready),
            .mem_rsp_rdata(mem_rsp_rdata),.mem_rsp_last(mem_rsp_last),.mem_rsp_error(mem_rsp_error));
    end else begin:g_no_nnue
        assign nnue_active=0;assign nnue_reg_we=0;assign nnue_reg_addr=0;assign nnue_reg_data=0;assign nnue_reg_rd_data=0;
        assign nnue_req_valid=0;assign nnue_req_addr=0;assign nnue_req_len=0;assign nnue_rsp_ready=0;
        assign link_input_we=0;assign link_input_addr=0;assign link_input_data=0;
        assign link_weight_we=0;assign link_weight_addr=0;assign link_weight_word=0;assign link_weight_data=0;
        assign link_output_ready=0;
    end endgenerate

    generate if(ENABLE_NNUE_BATCH && PIKAFISH_ONLY && ENABLE_PFF1_GATHER && ENABLE_NNUE_PIPELINE && !ENABLE_H128_SPARSE)begin:g_batch
     pikafish_eval_batch #(.DDR_BASE(DDR_BASE),.DDR_BYTES(DDR_BYTES)) u_batch(
      .clk(clk),.resetn(resetn),.reg_wr_en(reg_wr_en && !reg_wr_addr[8] && reg_wr_addr[7]),
      .reg_wr_addr(reg_wr_addr[6:0]),.reg_rd_addr(reg_rd_addr[6:0]),.reg_wr_data(reg_wr_data),.reg_wr_strb(reg_wr_strb),
      .reg_rd_data(batch_reg_data),.active(batch_active),
      .engines_busy(nnue_active || gather_busy || memory_owner!=0 || conv_busy),
      .gather_we(batch_g_we),.gather_addr(batch_g_addr),.gather_data(batch_g_data),.gather_status(gather_reg_rd_data),
      .nnue_we(batch_n_we),.nnue_addr(batch_n_addr),.nnue_read_addr(batch_n_read),.nnue_data(batch_n_data),.nnue_read_data(nnue_reg_rd_data),
      .g_req_valid(raw_g_req_valid),.g_req_write(raw_g_req_write),.g_req_addr(raw_g_req_addr),.g_req_len(raw_g_req_len),.g_external_ready(gather_req_ready),
      .local_select(local_select),.local_owned(local_owned),.local_req_ready(local_req_ready),.local_w_ready(local_w_ready),
      .local_rsp_valid(local_rsp_valid),.local_rsp_data(local_rsp_data),.local_rsp_last(local_rsp_last),.local_rsp_error(local_rsp_error),
      .g_w_valid(raw_g_w_valid),.g_w_last(raw_g_w_last),.g_w_data(raw_g_w_data),.g_w_strb(raw_g_w_strb),.g_rsp_ready(raw_g_rsp_ready),
      .mem_req_valid(batch_req_valid),.mem_req_ready(batch_req_ready),.mem_req_write(batch_req_write),.mem_req_addr(batch_req_addr),.mem_req_len(batch_req_len),
      .mem_w_valid(batch_w_valid),.mem_w_ready(batch_w_ready),.mem_w_data(batch_w_data),.mem_w_strb(batch_w_strb),.mem_w_last(batch_w_last),
      .mem_rsp_valid(memory_owner==3'd6 && mem_rsp_valid),.mem_rsp_ready(batch_rsp_ready),.mem_rsp_rdata(mem_rsp_rdata),.mem_rsp_last(mem_rsp_last),.mem_rsp_error(mem_rsp_error));
    end else begin:g_no_batch
     assign batch_active=0;assign batch_reg_data=0;assign batch_g_we=0;assign batch_g_addr=0;assign batch_g_data=0;
     assign batch_n_we=0;assign batch_n_addr=0;assign batch_n_read=0;assign batch_n_data=0;
     assign batch_req_valid=0;assign batch_req_write=0;assign batch_req_addr=0;assign batch_req_len=0;
     assign batch_w_valid=0;assign batch_w_data=0;assign batch_w_strb=0;assign batch_w_last=0;assign batch_rsp_ready=0;
     assign local_select=0;assign local_owned=0;assign local_req_ready=0;assign local_w_ready=0;
     assign local_rsp_valid=0;assign local_rsp_data=0;assign local_rsp_last=0;assign local_rsp_error=0;
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
