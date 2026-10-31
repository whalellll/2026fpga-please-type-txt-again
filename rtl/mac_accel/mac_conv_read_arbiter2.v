// Two read-only DMA clients share one ordered memory command/response port.
// Grant alternates when both clients request; ownership lasts through the
// accepted final response or a client timeout abort.
module mac_conv_read_arbiter2 (
    input wire clk,
    input wire resetn,
    input wire a_req_valid,
    output wire a_req_ready,
    input wire [31:0] a_req_addr,
    input wire [2:0] a_req_len,
    output wire a_rsp_valid,
    input wire a_rsp_ready,
    output wire [31:0] a_rsp_rdata,
    output wire a_rsp_last,
    output wire a_rsp_error,
    input wire a_abort,
    input wire b_req_valid,
    output wire b_req_ready,
    input wire [31:0] b_req_addr,
    input wire [2:0] b_req_len,
    output wire b_rsp_valid,
    input wire b_rsp_ready,
    output wire [31:0] b_rsp_rdata,
    output wire b_rsp_last,
    output wire b_rsp_error,
    input wire b_abort,
    output wire mem_req_valid,
    input wire mem_req_ready,
    output wire [31:0] mem_req_addr,
    output wire [2:0] mem_req_len,
    input wire mem_rsp_valid,
    output wire mem_rsp_ready,
    input wire [31:0] mem_rsp_rdata,
    input wire mem_rsp_last,
    input wire mem_rsp_error,
    output wire mem_abort
);
    reg [1:0] owner;
    reg last_grant_b;
    wire choose_a = a_req_valid && (!b_req_valid || last_grant_b);
    wire choose_b = b_req_valid && !choose_a;
    assign mem_req_valid = owner == 0 && (choose_a || choose_b);
    assign mem_req_addr = choose_a ? a_req_addr : b_req_addr;
    assign mem_req_len = choose_a ? a_req_len : b_req_len;
    assign a_req_ready = owner == 0 && choose_a && mem_req_ready;
    assign b_req_ready = owner == 0 && choose_b && mem_req_ready;
    assign a_rsp_valid = owner == 1 && mem_rsp_valid;
    assign b_rsp_valid = owner == 2 && mem_rsp_valid;
    assign a_rsp_rdata = mem_rsp_rdata;
    assign b_rsp_rdata = mem_rsp_rdata;
    assign a_rsp_last = mem_rsp_last;
    assign b_rsp_last = mem_rsp_last;
    assign a_rsp_error = mem_rsp_error;
    assign b_rsp_error = mem_rsp_error;
    assign mem_rsp_ready = owner == 1 ? a_rsp_ready :
                           owner == 2 ? b_rsp_ready : 1'b0;
    assign mem_abort = (owner == 1 && a_abort) ||
                       (owner == 2 && b_abort);
    always @(posedge clk) begin
        if (!resetn) begin
            owner <= 0;
            last_grant_b <= 1;
        end else if (mem_abort) begin
            owner <= 0;
        end else if (owner == 0 && mem_req_valid && mem_req_ready) begin
            owner <= choose_a ? 1 : 2;
            last_grant_b <= choose_b;
        end else if (owner != 0 && mem_rsp_valid &&
                     mem_rsp_ready && mem_rsp_last) begin
            owner <= 0;
        end
    end
endmodule
