// Single-beat compact output writer. Address and payload remain stable until
// the AXI adapter accepts them; a missing write response aborts ownership.
module mac_conv_compact_writer #(
    parameter [31:0] DDR_BASE=32'h0000_0000,
    parameter [31:0] DDR_BYTES=32'h2000_0000,
    parameter integer TIMEOUT_CYCLES=100000
) (
    input wire clk,
    input wire resetn,
    input wire word_valid,
    output wire word_ready,
    input wire [31:0] word_addr,
    input wire [31:0] word_data,
    input wire [3:0] word_strb,
    output wire mem_req_valid,
    input wire mem_req_ready,
    output wire mem_req_write,
    output wire [31:0] mem_req_addr,
    output wire [2:0] mem_req_len,
    output wire mem_w_valid,
    input wire mem_w_ready,
    output wire [31:0] mem_w_data,
    output wire [3:0] mem_w_strb,
    output wire mem_w_last,
    input wire mem_rsp_valid,
    output wire mem_rsp_ready,
    input wire mem_rsp_last,
    input wire mem_rsp_error,
    output reg mem_abort,
    output reg error
);
    localparam S_IDLE=3'd0,S_REQ=3'd1,S_DATA=3'd2,
               S_RESP=3'd3,S_HOLD=3'd4;
    localparam [32:0] DDR_LIMIT={1'b0,DDR_BASE}+DDR_BYTES;
    localparam integer TIMEOUT_WIDTH=TIMEOUT_CYCLES > 1 ? $clog2(TIMEOUT_CYCLES) : 1;
    reg [2:0] state;
    reg [31:0] addr_r,data_r;
    reg [3:0] strb_r;
    reg [TIMEOUT_WIDTH-1:0] timeout;
    wire [32:0] word_end={1'b0,word_addr}+33'd4;
    wire bad_word=word_addr[1:0]!=0 || word_strb==0 ||
                  {1'b0,word_addr}<{1'b0,DDR_BASE} ||
                  word_end>DDR_LIMIT;

    assign mem_req_valid=state==S_REQ;
    assign mem_req_write=1'b1;
    assign mem_req_addr=addr_r;
    assign mem_req_len=3'b0;
    assign mem_w_valid=state==S_DATA;
    assign mem_w_data=data_r;
    assign mem_w_strb=strb_r;
    assign mem_w_last=1'b1;
    assign mem_rsp_ready=state==S_RESP;
    assign word_ready=state==S_RESP && mem_rsp_valid &&
                      mem_rsp_last && !mem_rsp_error;

    always @(posedge clk) begin
        if (!resetn) begin
            state<=S_IDLE;addr_r<=0;data_r<=0;strb_r<=0;
            timeout<=0;mem_abort<=0;error<=0;
        end else begin
            mem_abort<=0;error<=0;
            case (state)
                S_IDLE: if (word_valid) begin
                    if (bad_word) begin error<=1;state<=S_HOLD;end
                    else begin
                        addr_r<=word_addr;data_r<=word_data;
                        strb_r<=word_strb;timeout<=0;state<=S_REQ;
                    end
                end
                S_REQ: if (mem_req_ready) begin
                    timeout<=0;state<=S_DATA;
                end else if (timeout==TIMEOUT_CYCLES-1) begin
                    error<=1;state<=S_HOLD;
                end else timeout<=timeout+1'b1;
                S_DATA: if (mem_w_ready) begin
                    timeout<=0;state<=S_RESP;
                end else if (timeout==TIMEOUT_CYCLES-1) begin
                    error<=1;mem_abort<=1;state<=S_HOLD;
                end else timeout<=timeout+1'b1;
                S_RESP: if (mem_rsp_valid) begin
                    if (!mem_rsp_last || mem_rsp_error) begin
                        error<=1;
                        if (!mem_rsp_last) mem_abort<=1;
                        state<=S_HOLD;
                    end else state<=S_IDLE;
                end else if (timeout==TIMEOUT_CYCLES-1) begin
                    error<=1;mem_abort<=1;state<=S_HOLD;
                end else timeout<=timeout+1'b1;
                S_HOLD: if (!word_valid) state<=S_IDLE;
                default: state<=S_IDLE;
            endcase
        end
    end
endmodule
