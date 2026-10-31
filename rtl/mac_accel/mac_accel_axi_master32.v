`timescale 1ns / 1ps

// Converts the kernel's command/data DDR port into 32-bit AXI4 INCR bursts.
// One command contains between one and eight beats. Only one AXI transaction
// is outstanding, which keeps ordering and error handling deterministic.
module mac_accel_axi_master32 (
    input  wire        clk,
    input  wire        resetn,

    input  wire        mem_req_valid,
    output wire        mem_req_ready,
    input  wire        mem_req_write,
    input  wire [31:0] mem_req_addr,
    input  wire [2:0]  mem_req_len,

    input  wire        mem_w_valid,
    output wire        mem_w_ready,
    input  wire [31:0] mem_w_data,
    input  wire [3:0]  mem_w_strb,
    input  wire        mem_w_last,

    output wire        mem_rsp_valid,
    input  wire        mem_rsp_ready,
    output wire [31:0] mem_rsp_rdata,
    output wire        mem_rsp_last,
    output wire        mem_rsp_error,

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

    localparam [2:0] S_IDLE   = 3'd0;
    localparam [2:0] S_R_ADDR = 3'd1;
    localparam [2:0] S_R_DATA = 3'd2;
    localparam [2:0] S_W_DATA = 3'd3;
    localparam [2:0] S_W_RESP = 3'd4;

    reg [2:0] state;
    reg [31:0] request_addr;
    reg [2:0] request_len;
    reg [2:0] beat_index;
    reg aw_pending;
    reg write_data_done;
    reg read_error_seen;
    reg write_stream_error;

    wire read_expected_last = beat_index == request_len;
    wire read_transaction_end = read_expected_last || m_axi_rlast;
    wire write_expected_last = beat_index == request_len;
    wire aw_handshake = m_axi_awvalid && m_axi_awready;
    wire w_handshake = m_axi_wvalid && m_axi_wready;
    wire write_address_done = !aw_pending || aw_handshake;
    wire write_payload_done = write_data_done ||
        (w_handshake && write_expected_last);

    assign mem_req_ready = state == S_IDLE;
    assign mem_w_ready = (state == S_W_DATA) && !write_data_done &&
                         m_axi_wready;

    assign mem_rsp_valid = (state == S_R_DATA) ? m_axi_rvalid :
                           (state == S_W_RESP) ? m_axi_bvalid : 1'b0;
    assign mem_rsp_rdata = (state == S_R_DATA) ? m_axi_rdata : 32'b0;
    assign mem_rsp_last = (state == S_R_DATA) ? read_transaction_end :
                          (state == S_W_RESP);
    assign mem_rsp_error = (state == S_R_DATA) ?
        (read_transaction_end &&
         (read_error_seen || (m_axi_rresp != 2'b00) ||
          (m_axi_rlast != read_expected_last))) :
        ((state == S_W_RESP) &&
         ((m_axi_bresp != 2'b00) || write_stream_error));

    assign m_axi_awaddr = request_addr;
    assign m_axi_awlen = {5'b0, request_len};
    assign m_axi_awsize = 3'd2;
    assign m_axi_awburst = 2'b01;
    assign m_axi_awvalid = (state == S_W_DATA) && aw_pending;

    assign m_axi_wdata = mem_w_data;
    assign m_axi_wstrb = mem_w_strb;
    assign m_axi_wlast = write_expected_last;
    assign m_axi_wvalid = (state == S_W_DATA) && !write_data_done &&
                          mem_w_valid;
    assign m_axi_bready = (state == S_W_RESP) && mem_rsp_ready;

    // Launch a new read while accepting its command. If AR is stalled,
    // the same payload is held in request_* until the address handshakes.
    // Only one transaction remains outstanding; responses cannot bypass it.
    wire read_launch = resetn && state == S_IDLE && mem_req_valid && !mem_req_write;
    assign m_axi_araddr = read_launch ? mem_req_addr : request_addr;
    assign m_axi_arlen = {5'b0, read_launch ? mem_req_len : request_len};
    assign m_axi_arsize = 3'd2;
    assign m_axi_arburst = 2'b01;
    assign m_axi_arvalid = state == S_R_ADDR || read_launch;
    assign m_axi_rready = (state == S_R_DATA) && mem_rsp_ready;

    always @(posedge clk) begin
        if (!resetn) begin
            state <= S_IDLE;
            request_addr <= 32'b0;
            request_len <= 3'b0;
            beat_index <= 3'b0;
            aw_pending <= 1'b0;
            write_data_done <= 1'b0;
            read_error_seen <= 1'b0;
            write_stream_error <= 1'b0;
        end else begin
            case (state)
                S_IDLE: begin
                    if (mem_req_valid) begin
                        request_addr <= mem_req_addr;
                        request_len <= mem_req_len;
                        beat_index <= 3'b0;
                        read_error_seen <= 1'b0;
                        write_stream_error <= 1'b0;
                        if (mem_req_write) begin
                            aw_pending <= 1'b1;
                            write_data_done <= 1'b0;
                            state <= S_W_DATA;
                        end else begin
                            state <= m_axi_arready ? S_R_DATA : S_R_ADDR;
                        end
                    end
                end

                S_R_ADDR: begin
                    if (m_axi_arvalid && m_axi_arready)
                        state <= S_R_DATA;
                end

                S_R_DATA: begin
                    if (m_axi_rvalid && mem_rsp_ready) begin
                        if (m_axi_rresp != 2'b00)
                            read_error_seen <= 1'b1;
                        if (read_transaction_end) begin
                            state <= S_IDLE;
                        end else begin
                            beat_index <= beat_index + 3'd1;
                        end
                    end
                end

                S_W_DATA: begin
                    if (aw_handshake)
                        aw_pending <= 1'b0;

                    if (w_handshake) begin
                        if (mem_w_last != write_expected_last)
                            write_stream_error <= 1'b1;
                        if (write_expected_last) begin
                            write_data_done <= 1'b1;
                        end else begin
                            beat_index <= beat_index + 3'd1;
                        end
                    end

                    if (write_address_done && write_payload_done)
                        state <= S_W_RESP;
                end

                S_W_RESP: begin
                    if (m_axi_bvalid && mem_rsp_ready)
                        state <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
