`timescale 1ns/1ps

// Validate/cache descriptors, stream full model rows, accumulate modulo int16
// in synchronous RAMs. No multiplier or full-width register array is needed.
module pff1_stagea_gather #(
    parameter [31:0] THREAT_BASE=32'h10002000,
    parameter [15:0] THREAT_ROWS=16'd45547,
    parameter [31:0] PSQ_BASE=32'h12f45000,
    parameter [15:0] PSQ_ROWS=16'd16536,
    parameter [31:0] SCRATCH_BASE=32'h1b000000,
    parameter integer SCRATCH_BYTES=1024*1024
) (
    input wire clk,resetn,reg_wr_en,
    input wire [7:0] reg_wr_addr,
    input wire [31:0] reg_wr_data,
    input wire [3:0] reg_wr_strb,
    input wire [7:0] reg_rd_addr,
    output reg [31:0] reg_rd_data,
    output reg mem_req_valid,
    input wire mem_req_ready,
    output reg mem_req_write,
    output reg [31:0] mem_req_addr,
    output reg [2:0] mem_req_len,
    output reg mem_w_valid,
    input wire mem_w_ready,
    output reg [31:0] mem_w_data,
    output reg [3:0] mem_w_strb,
    output reg mem_w_last,
    input wire mem_rsp_valid,
    output reg mem_rsp_ready,
    input wire [31:0] mem_rsp_rdata,
    input wire mem_rsp_last,mem_rsp_error
);
    localparam [3:0] IDLE=0,DESC_REQ=1,DESC_DATA=2,BASE_REQ=3,
        BASE_DATA=4,ROW_SELECT=5,ROW_REQ=6,ROW_DATA=7,ROW_FLUSH=8,
        OUT_REQ=9,OUT_DATA=10,OUT_RESP=11,ERROR_DRAIN=12,DESC_LOOKUP=13;
    localparam [3:0] ERR_CONFIG=1,ERR_RANGE=2,ERR_DESCRIPTOR=3,ERR_DDR=4;
    reg [3:0] state;
    reg busy,done,error;
    reg [3:0] error_code;
    reg [19:0] parent_src,descriptor_src,output_dst;
    reg [2:0] scratch_high_valid;
    reg [8:0] term_count,descriptors_loaded;
    reg count_encoding_valid;
    reg [31:0] cycle_count;
    reg [8:0] base_index,output_index;
    reg [7:0] term_index,row_index;
    reg [3:0] burst_remaining;
    reg [17:0] descriptor_q;
    // One 36 Kibit RAM: lower half holds 256 four-lane accumulators,
    // upper half holds the validated 18-bit descriptors. Their read
    // phases do not overlap, so one synchronous read port suffices.
    reg [63:0] gather_ram[0:511];
    reg [63:0] gather_q;
    reg [31:0] base_half;
    wire [31:0] acc_low_q=gather_q[31:0],acc_high_q=gather_q[63:32];
    reg update_pending;
    reg [7:0] update_index;
    reg [31:0] update_data;
    reg update_subtract;
    wire command_start=reg_wr_en && reg_wr_addr==8'h08 && reg_wr_strb[0] && reg_wr_data[0];
    wire command_clear=reg_wr_en && reg_wr_addr==8'h08 && reg_wr_strb[0] && reg_wr_data[1];
    wire config_valid=count_encoding_valid && term_count!=0 && term_count<=256 &&
        (parent_src[1:0]|descriptor_src[1:0]|output_dst[1:0])==0;
    // Scratch is an aligned aperture of at most 1 MiB. Reject high bits
    // before using narrower offsets; this preserves overflow protection.
    wire ranges_valid=THREAT_BASE[31:26]==PSQ_BASE[31:26] &&
        THREAT_BASE[9:0]==0 && PSQ_BASE[9:0]==0 &&
        ({1'b0,THREAT_BASE[25:0]}+({11'b0,THREAT_ROWS}<<10))<=27'h4000000 &&
        ({1'b0,PSQ_BASE[25:0]}+({11'b0,PSQ_ROWS}<<10))<=27'h4000000 &&
        SCRATCH_BASE[19:0]==0 && SCRATCH_BYTES>=2048 && SCRATCH_BYTES<=1048576 &&
        (&scratch_high_valid) &&
        parent_src[19:0]<=SCRATCH_BYTES-2048 && output_dst[19:0]<=SCRATCH_BYTES-2048 &&
        SCRATCH_BYTES%1024==0 &&
        (descriptor_src[19:10] < ((SCRATCH_BYTES-1)>>10) ||
         (descriptor_src[19:10] == ((SCRATCH_BYTES-1)>>10) &&
          ({1'b0,descriptor_src[9:2]}+term_count)<=9'd256));
    wire descriptor_valid=mem_rsp_rdata[29:16]==0 &&
        (mem_rsp_rdata[30] ? mem_rsp_rdata[15:0]<PSQ_ROWS : mem_rsp_rdata[15:0]<THREAT_ROWS);
    wire [15:0] model_row=(descriptor_q[16]?PSQ_BASE[25:10]:THREAT_BASE[25:10])+descriptor_q[15:0];
    wire [31:0] row_address={THREAT_BASE[31:26],model_row,row_index,2'b0};
    wire [19:0] descriptor_offset=descriptor_src[19:0]+{9'b0,descriptors_loaded,2'b0};
    wire [19:0] base_offset=parent_src[19:0]+{9'b0,base_index,2'b0};
    wire [19:0] output_offset=output_dst[19:0]+{9'b0,output_index,2'b0};
    wire [31:0] descriptor_address={SCRATCH_BASE[31:20],descriptor_offset};
    wire [31:0] base_address={SCRATCH_BASE[31:20],base_offset};
    wire [31:0] output_address={SCRATCH_BASE[31:20],output_offset};
    wire [8:0] descriptor_left=term_count-descriptors_loaded;
    wire [9:0] base_left=10'd512-{1'b0,base_index};
    wire [9:0] output_left=10'd512-{1'b0,output_index};
    // Former burst_size function: end at a 32-byte boundary (which also
    // prevents a 4 KiB crossing) or when fewer bytes remain.
    wire [3:0] descriptor_boundary = 4'd8-{1'b0,descriptor_address[4:2]};
    wire [3:0] descriptor_beats =
        {1'b0,descriptor_left}>=descriptor_boundary ? descriptor_boundary :
        descriptor_left[3:0];
    wire [3:0] base_boundary = 4'd8-{1'b0,base_address[4:2]};
    wire [3:0] base_beats =
        base_left>=base_boundary ? base_boundary : base_left[3:0];
    wire [3:0] output_boundary = 4'd8-{1'b0,output_address[4:2]};
    wire [3:0] output_beats =
        output_left>=output_boundary ? output_boundary : output_left[3:0];

    wire response=mem_rsp_valid && mem_rsp_ready;
    wire good_base=response && state==BASE_DATA && !mem_rsp_error &&
                   mem_rsp_last==(burst_remaining==1);
    wire good_row=response && state==ROW_DATA && !mem_rsp_error &&
                  mem_rsp_last==(burst_remaining==1);
    wire [8:0] next_output_index=output_index+9'd1;
    wire [7:0] acc_read_index=state==ROW_DATA ? row_index :
        ((state==OUT_DATA && mem_w_ready) ? next_output_index[8:1] : output_index[8:1]);
    wire [8:0] gather_read_index=state==ROW_SELECT ?
        {1'b1,term_index} : {1'b0,acc_read_index};
    // Former add_byte function: sign-extended saturating-free byte add.
    wire signed [8:0] update_delta0 = update_subtract ?
        -$signed({update_data[31],update_data[31:24]}) :
        $signed({update_data[31],update_data[31:24]});
    wire signed [8:0] update_delta1 = update_subtract ?
        -$signed({update_data[23],update_data[23:16]}) :
        $signed({update_data[23],update_data[23:16]});
    wire signed [8:0] update_delta2 = update_subtract ?
        -$signed({update_data[15],update_data[15:8]}) :
        $signed({update_data[15],update_data[15:8]});
    wire signed [8:0] update_delta3 = update_subtract ?
        -$signed({update_data[7],update_data[7:0]}) :
        $signed({update_data[7],update_data[7:0]});
    wire [15:0] update_byte0 =
        acc_high_q[31:16]+{{7{update_delta0[8]}},update_delta0};
    wire [15:0] update_byte1 =
        acc_high_q[15:0]+{{7{update_delta1[8]}},update_delta1};
    wire [15:0] update_byte2 =
        acc_low_q[31:16]+{{7{update_delta2[8]}},update_delta2};
    wire [15:0] update_byte3 =
        acc_low_q[15:0]+{{7{update_delta3[8]}},update_delta3};

    // Single full-width write port avoids byte-write fragmentation.
    always @(posedge clk) begin
        gather_q<=gather_ram[gather_read_index];
        if(state==DESC_LOOKUP)descriptor_q<=gather_q[17:0];
        if(good_base && !base_index[0])base_half<=mem_rsp_rdata;
        if(response && state==DESC_DATA && descriptor_valid && !mem_rsp_error)
            gather_ram[{1'b1,descriptors_loaded[7:0]}]<=
                {46'b0,mem_rsp_rdata[31:30],mem_rsp_rdata[15:0]};
        else if(good_base && base_index[0])
            gather_ram[{1'b0,base_index[8:1]}]<={mem_rsp_rdata,base_half};
        else if(update_pending)gather_ram[{1'b0,update_index}]<=
            {update_byte0,update_byte1,update_byte2,update_byte3};
    end
    always @* begin
        reg_rd_data=0;
        case(reg_rd_addr)
            8'h00:reg_rd_data=32'h50464741;
            8'h04:reg_rd_data=32'h00020000;
            8'h0c:reg_rd_data={20'b0,error_code,5'b0,error,done,busy};
            8'h10:reg_rd_data={SCRATCH_BASE[31:20],parent_src};
            8'h14:reg_rd_data={SCRATCH_BASE[31:20],descriptor_src};
            8'h18:reg_rd_data={SCRATCH_BASE[31:20],output_dst};
            8'h1c:reg_rd_data={23'b0,term_count};
            8'h20:reg_rd_data=cycle_count;
            8'h24:reg_rd_data=0; // reserved: avoid a redundant run counter
            8'h28:reg_rd_data={16'b0,THREAT_ROWS};
            8'h2c:reg_rd_data={16'b0,PSQ_ROWS};
            default:begin end
        endcase
        mem_req_valid=0;mem_req_write=0;mem_req_addr=0;mem_req_len=0;
        mem_w_valid=0;mem_w_data=output_index[0]?acc_high_q:acc_low_q;
        mem_w_strb=4'hf;mem_w_last=burst_remaining==1;mem_rsp_ready=0;
        case(state)
            DESC_REQ:begin mem_req_valid=1;mem_req_addr=descriptor_address;mem_req_len=descriptor_beats-1;end
            BASE_REQ:begin mem_req_valid=1;mem_req_addr=base_address;mem_req_len=base_beats-1;end
            ROW_REQ:begin mem_req_valid=1;mem_req_addr=row_address;mem_req_len=7;end
            OUT_REQ:begin mem_req_valid=1;mem_req_write=1;mem_req_addr=output_address;mem_req_len=output_beats-1;end
            DESC_DATA,BASE_DATA,ROW_DATA,OUT_RESP,ERROR_DRAIN:mem_rsp_ready=1;
            OUT_DATA:mem_w_valid=1;
            default:begin end
        endcase
    end
    // Finish accepted reads before exposing an error or permitting a new job.
    task fail_read;
        input [3:0] code;
        begin
            error<=1;error_code<=code;
            if(mem_rsp_last)begin state<=IDLE;busy<=0;done<=1;end
            else state<=ERROR_DRAIN;
        end
    endtask
    always @(posedge clk) begin
        if(!resetn)begin
            state<=IDLE;busy<=0;done<=0;error<=0;error_code<=0;
            parent_src<=0;descriptor_src<=0;output_dst<=0;scratch_high_valid<=3'b111;
            term_count<=1;count_encoding_valid<=1;cycle_count<=0;
            descriptors_loaded<=0;base_index<=0;output_index<=0;term_index<=0;row_index<=0;
            burst_remaining<=0;update_pending<=0;update_index<=0;update_data<=0;update_subtract<=0;
        end else begin
            if(busy)cycle_count<=cycle_count+1;
            update_pending<=good_row;
            if(good_row)begin update_index<=row_index;update_data<=mem_rsp_rdata;update_subtract<=descriptor_q[17];end
            if(reg_wr_en && !busy && reg_wr_strb==4'hf)case(reg_wr_addr)
                8'h10:begin parent_src<=reg_wr_data[19:0];scratch_high_valid[0]<=reg_wr_data[31:20]==SCRATCH_BASE[31:20];end
                8'h14:begin descriptor_src<=reg_wr_data[19:0];scratch_high_valid[1]<=reg_wr_data[31:20]==SCRATCH_BASE[31:20];end
                8'h18:begin output_dst<=reg_wr_data[19:0];scratch_high_valid[2]<=reg_wr_data[31:20]==SCRATCH_BASE[31:20];end
                8'h1c:begin term_count<=reg_wr_data[8:0];count_encoding_valid<=reg_wr_data[31:9]==0;end
                default:begin end
            endcase
            if(command_clear && !busy)begin done<=0;error<=0;error_code<=0;end
            case(state)
                IDLE:if(command_start)begin
                    cycle_count<=0;done<=0;error<=0;error_code<=0;descriptors_loaded<=0;
                    base_index<=0;output_index<=0;term_index<=0;row_index<=0;
                    if(!config_valid)begin done<=1;error<=1;error_code<=ERR_CONFIG;end
                    else if(!ranges_valid)begin done<=1;error<=1;error_code<=ERR_RANGE;end
                    else begin busy<=1;state<=DESC_REQ;end
                end
                DESC_REQ:if(mem_req_valid && mem_req_ready)begin state<=DESC_DATA;burst_remaining<=descriptor_beats;end
                DESC_DATA:if(response)begin
                    if(mem_rsp_error || mem_rsp_last!=(burst_remaining==1))fail_read(ERR_DDR);
                    else if(!descriptor_valid)fail_read(ERR_DESCRIPTOR);
                    else begin descriptors_loaded<=descriptors_loaded+1;burst_remaining<=burst_remaining-1;
                        if(descriptors_loaded+9'd1==term_count)state<=BASE_REQ;
                        else if(mem_rsp_last)state<=DESC_REQ;
                    end
                end
                BASE_REQ:if(mem_req_valid && mem_req_ready)begin state<=BASE_DATA;burst_remaining<=base_beats;end
                BASE_DATA:if(response)begin
                    if(!good_base)fail_read(ERR_DDR);
                    else begin base_index<=base_index+1;burst_remaining<=burst_remaining-1;
                        if(base_index==511)state<=ROW_SELECT;
                        else if(mem_rsp_last)state<=BASE_REQ;
                    end
                end
                ROW_SELECT:state<=DESC_LOOKUP;
                DESC_LOOKUP:state<=ROW_REQ;
                ROW_REQ:if(mem_req_valid && mem_req_ready)begin state<=ROW_DATA;burst_remaining<=8;end
                ROW_DATA:if(response)begin
                    if(!good_row)fail_read(ERR_DDR);
                    else begin row_index<=row_index+1;burst_remaining<=burst_remaining-1;
                        if(row_index==255)state<=ROW_FLUSH;
                        else if(mem_rsp_last)state<=ROW_REQ;
                    end
                end
                ROW_FLUSH:begin
                    if({1'b0,term_index}+9'd1==term_count)state<=OUT_REQ;
                    else begin term_index<=term_index+1;state<=ROW_SELECT;end
                end
                OUT_REQ:if(mem_req_valid && mem_req_ready)begin state<=OUT_DATA;burst_remaining<=output_beats;end
                OUT_DATA:if(mem_w_valid && mem_w_ready)begin
                    output_index<=output_index+1;burst_remaining<=burst_remaining-1;
                    if(burst_remaining==1)state<=OUT_RESP;
                end
                OUT_RESP:if(response)begin
                    if(mem_rsp_error || !mem_rsp_last)fail_read(ERR_DDR);
                    else if(output_index==0)begin state<=IDLE;busy<=0;done<=1;end
                    else state<=OUT_REQ;
                end
                ERROR_DRAIN:if(response && mem_rsp_last)begin state<=IDLE;busy<=0;done<=1;end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
