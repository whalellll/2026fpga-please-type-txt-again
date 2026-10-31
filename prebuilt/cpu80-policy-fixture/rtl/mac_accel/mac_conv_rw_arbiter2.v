// Serializes convolution input/weight reads with compact output writes.
// One accepted command owns the shared AXI adapter through its final response.
module mac_conv_rw_arbiter2 (
    input wire clk,input wire resetn,
    input wire r_req_valid,output wire r_req_ready,
    input wire [31:0] r_req_addr,input wire [2:0] r_req_len,
    output wire r_rsp_valid,input wire r_rsp_ready,
    output wire [31:0] r_rsp_rdata,
    output wire r_rsp_last,output wire r_rsp_error,input wire r_abort,
    input wire w_req_valid,output wire w_req_ready,
    input wire [31:0] w_req_addr,input wire [2:0] w_req_len,
    input wire w_w_valid,output wire w_w_ready,
    input wire [31:0] w_w_data,input wire [3:0] w_w_strb,
    input wire w_w_last,
    output wire w_rsp_valid,input wire w_rsp_ready,
    output wire w_rsp_last,output wire w_rsp_error,input wire w_abort,
    output wire mem_req_valid,input wire mem_req_ready,
    output wire mem_req_write,output wire [31:0] mem_req_addr,
    output wire [2:0] mem_req_len,
    output wire mem_w_valid,input wire mem_w_ready,
    output wire [31:0] mem_w_data,output wire [3:0] mem_w_strb,
    output wire mem_w_last,
    input wire mem_rsp_valid,output wire mem_rsp_ready,
    input wire [31:0] mem_rsp_rdata,input wire mem_rsp_last,
    input wire mem_rsp_error,output wire mem_abort
);
    reg [1:0] owner;
    reg prefer_write;
    wire choose_write = w_req_valid && (!r_req_valid || prefer_write);
    wire choose_read = r_req_valid && !choose_write;
    assign mem_req_valid=owner==0 && (choose_read || choose_write);
    assign mem_req_write=choose_write;
    assign mem_req_addr=choose_write ? w_req_addr : r_req_addr;
    assign mem_req_len=choose_write ? w_req_len : r_req_len;
    assign r_req_ready=owner==0 && choose_read && mem_req_ready;
    assign w_req_ready=owner==0 && choose_write && mem_req_ready;
    assign mem_w_valid=owner==2 && w_w_valid;
    assign mem_w_data=w_w_data;
    assign mem_w_strb=w_w_strb;
    assign mem_w_last=w_w_last;
    assign w_w_ready=owner==2 && mem_w_ready;
    assign r_rsp_valid=owner==1 && mem_rsp_valid;
    assign w_rsp_valid=owner==2 && mem_rsp_valid;
    assign r_rsp_rdata=mem_rsp_rdata;
    assign r_rsp_last=mem_rsp_last;
    assign w_rsp_last=mem_rsp_last;
    assign r_rsp_error=mem_rsp_error;
    assign w_rsp_error=mem_rsp_error;
    assign mem_rsp_ready=owner==1 ? r_rsp_ready :
                         owner==2 ? w_rsp_ready : 1'b0;
    assign mem_abort=(owner==1 && r_abort) || (owner==2 && w_abort);

    always @(posedge clk) begin
        if (!resetn) begin owner<=0;prefer_write<=0;end
        else if (mem_abort) owner<=0;
        else if (owner==0 && mem_req_valid && mem_req_ready)
            owner<=choose_write ? 2'd2 : 2'd1;
        else if (owner!=0 && mem_rsp_valid && mem_rsp_ready && mem_rsp_last) begin
            prefer_write<=owner==1;
            owner<=0;
        end
    end
endmodule
