`timescale 1ns/1ps

// MMIO at the previously unused0x180..0x1ff MAC subwindow. StageA forwards
// complete accumulator words directly; manual uploads serve cache misses.
module nnue_pipeline_frontend #(
 parameter [31:0] DDR_BASE=32'h1b000000,parameter integer DDR_BYTES=1048576,
 parameter integer PIKAFISH_ONLY=0
)(
 input wire clk,resetn,reg_wr_en,input wire [6:0] reg_wr_addr,reg_rd_addr,
 input wire [31:0] reg_wr_data,input wire [3:0] reg_wr_strb,
 output reg [31:0] reg_rd_data,
 input wire gather_begin,gather_valid,gather_commit,gather_abort,gather_view,
 input wire [31:0] gather_tag,gather_data,input wire [8:0] gather_index,
 output wire active,
 output wire mac_reg_we,output wire [7:0] mac_reg_addr,output wire [31:0] mac_reg_data,
 input wire [31:0] mac_status,
 output wire link_input_we,output wire [10:0] link_input_addr,output wire [63:0] link_input_data,
 output wire link_weight_we,output wire [10:0] link_weight_addr,
 output wire [4:0] link_weight_word,output wire [31:0] link_weight_data,
 input wire link_output_valid,output wire link_output_ready,
 input wire [12:0] link_output_index,input wire [31:0] link_output_data,
 output wire mem_req_valid,input wire mem_req_ready,
 output wire [31:0] mem_req_addr,output wire [2:0] mem_req_len,
 input wire mem_rsp_valid,output wire mem_rsp_ready,
 input wire [31:0] mem_rsp_rdata,input wire mem_rsp_last,mem_rsp_error
);
 reg [31:0] stack_q,expected0,expected1,upload_tag;
 reg swap_q,upload_view;
 reg [9:0] upload_index;
 reg [31:0] upload_data;
 reg start_q,abort_q,begin_q,commit_q,valid_q,upload_abort_q;
 reg model_invalidate_q;
 wire model_cache_valid,model_cache_hit;
 wire [31:0] model_read_words;
 wire ft_busy,ft_done,ft_error,ft_ready,ft_valid;
 wire [8:0] ft_index;
 wire [15:0] ft_data;
 wire [31:0] ft_cycles,chain_cycles;
 wire chain_busy,chain_done,chain_error;
 wire signed [31:0] chain_score;
 wire [3:0] chain_jobs;
 reg done_q,error_q,cache_error_q,chain_done_seen;
 wire chain_completed=chain_done && !chain_done_seen;
 wire upload_selected=begin_q || valid_q || commit_q || upload_abort_q;
 assign active=chain_busy || ft_busy || start_q;
 nnue_stream_transform u_transform(
  .clk(clk),.resetn(resetn),
  .write_begin(upload_selected?begin_q:gather_begin),
  .write_valid(upload_selected?valid_q:gather_valid),
  .write_commit(upload_selected?commit_q:gather_commit),
  .write_abort(upload_abort_q || gather_abort || abort_q || (chain_completed&&chain_error)),
  .write_view(upload_selected?upload_view:gather_view),
  .write_tag(upload_selected?upload_tag:gather_tag),
  .write_data(upload_selected?upload_data:gather_data),
  .write_index(upload_selected?(upload_index[8:0]-9'd1):gather_index),
  .write_ready(),.start(start_q),.swap_views(swap_q),.expected_tag0(expected0),.expected_tag1(expected1),
  .busy(ft_busy),.done(ft_done),.error(ft_error),
  .feature_valid(ft_valid),.feature_ready(ft_ready),.feature_index(ft_index),.feature_data(ft_data),.cycles(ft_cycles));
 generate if(!PIKAFISH_ONLY)begin:g_generic
 assign model_cache_valid=0;assign model_cache_hit=0;assign model_read_words=0;
 nnue_mlp_chain #(.DDR_BASE(DDR_BASE),.DDR_BYTES(DDR_BYTES)) u_chain(
  .clk(clk),.resetn(resetn),.start(start_q),.abort(abort_q || (ft_done&&ft_error)),.stack_source(stack_q),
  .busy(chain_busy),.done(chain_done),.error(chain_error),.score(chain_score),.cycles(chain_cycles),.jobs(chain_jobs),
  .feature_valid(ft_valid),.feature_ready(ft_ready),.feature_index(ft_index),.feature_data(ft_data),
  .mac_reg_we(mac_reg_we),.mac_reg_addr(mac_reg_addr),.mac_reg_data(mac_reg_data),.mac_status(mac_status),
  .link_input_we(link_input_we),.link_input_addr(link_input_addr),.link_input_data(link_input_data),
  .link_weight_we(link_weight_we),.link_weight_addr(link_weight_addr),.link_weight_word(link_weight_word),.link_weight_data(link_weight_data),
  .link_output_valid(link_output_valid),.link_output_ready(link_output_ready),.link_output_index(link_output_index),.link_output_data(link_output_data),
  .mem_req_valid(mem_req_valid),.mem_req_ready(mem_req_ready),.mem_req_addr(mem_req_addr),.mem_req_len(mem_req_len),
  .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_rdata(mem_rsp_rdata),.mem_rsp_last(mem_rsp_last),.mem_rsp_error(mem_rsp_error));
 end else begin:g_dedicated
 assign mac_reg_we=0;assign mac_reg_addr=0;assign mac_reg_data=0;
 assign link_input_we=0;assign link_input_addr=0;assign link_input_data=0;
 assign link_weight_we=0;assign link_weight_addr=0;assign link_weight_word=0;assign link_weight_data=0;
 assign link_output_ready=0;
 pikafish_mlp_dedicated #(.DDR_BASE(DDR_BASE),.DDR_BYTES(DDR_BYTES)) u_chain(
  .clk(clk),.resetn(resetn),.start(start_q),.abort(abort_q || (ft_done&&ft_error)),
  .invalidate(model_invalidate_q),.stack_source(stack_q),
  .busy(chain_busy),.done(chain_done),.error(chain_error),.score(chain_score),.cycles(chain_cycles),.jobs(chain_jobs),
  .feature_valid(ft_valid),.feature_ready(ft_ready),.feature_index(ft_index),.feature_data(ft_data),
  .mem_req_valid(mem_req_valid),.mem_req_ready(mem_req_ready),.mem_req_addr(mem_req_addr),.mem_req_len(mem_req_len),
  .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_rdata(mem_rsp_rdata),
  .mem_rsp_last(mem_rsp_last),.mem_rsp_error(mem_rsp_error),
  .cache_valid(model_cache_valid),.cache_hit(model_cache_hit),.read_words(model_read_words));
 end endgenerate
 always @*begin
  reg_rd_data=0;
  case(reg_rd_addr)
   7'h00:reg_rd_data=32'h4e4e5031;
   7'h04:reg_rd_data=PIKAFISH_ONLY?32'h00020000:32'h00010000;
   7'h0c:reg_rd_data={28'b0,cache_error_q,error_q,done_q,active};
   7'h10:reg_rd_data=stack_q;
   7'h14:reg_rd_data=expected0;
   7'h18:reg_rd_data=expected1;
   7'h1c:reg_rd_data={23'b0,upload_view,7'b0,swap_q};
   7'h20:reg_rd_data=upload_tag;
   7'h24:reg_rd_data={22'b0,upload_index};
   7'h2c:reg_rd_data=chain_score;
   7'h30:reg_rd_data=chain_cycles;
   7'h34:reg_rd_data={28'b0,chain_jobs};
   7'h38:reg_rd_data=ft_cycles;
   7'h3c:reg_rd_data=32'h000103ff;
   7'h40:reg_rd_data=PIKAFISH_ONLY?32'h00000001:0;
   7'h44:reg_rd_data={30'b0,model_cache_hit,model_cache_valid};
   7'h48:reg_rd_data=model_read_words;
   default:begin end
  endcase
 end
 always @(posedge clk)begin
  if(!resetn)begin
   stack_q<=DDR_BASE;expected0<=0;expected1<=0;upload_tag<=0;upload_view<=0;swap_q<=0;
   upload_index<=0;upload_data<=0;start_q<=0;abort_q<=0;begin_q<=0;commit_q<=0;
   valid_q<=0;upload_abort_q<=0;model_invalidate_q<=0;done_q<=0;error_q<=0;cache_error_q<=0;chain_done_seen<=0;
  end else begin
   start_q<=0;abort_q<=0;begin_q<=0;commit_q<=0;valid_q<=0;upload_abort_q<=0;model_invalidate_q<=0;
   chain_done_seen<=chain_done;
   if(ft_done && ft_error)cache_error_q<=1;
   if(chain_completed && !start_q)begin done_q<=1;error_q<=chain_error;end
   if(reg_wr_en && reg_wr_strb==4'hf)begin
    if(reg_wr_addr==7'h08 && reg_wr_data[2])abort_q<=1;
    if(!active)case(reg_wr_addr)
     7'h08:begin
      if(reg_wr_data[0])begin start_q<=1;done_q<=0;error_q<=0;cache_error_q<=0;end
      if(reg_wr_data[1])begin done_q<=0;error_q<=0;cache_error_q<=0;end
      if(reg_wr_data[3])begin begin_q<=1;upload_index<=0;end
      if(reg_wr_data[4])commit_q<=1;
      if(reg_wr_data[5])upload_abort_q<=1;
      if(reg_wr_data[6])model_invalidate_q<=1;
     end
     7'h10:stack_q<=reg_wr_data;
     7'h14:expected0<=reg_wr_data;
     7'h18:expected1<=reg_wr_data;
     7'h1c:begin swap_q<=reg_wr_data[0];upload_view<=reg_wr_data[8];end
     7'h20:upload_tag<=reg_wr_data;
     7'h28:if(upload_index<512)begin
      upload_data<=reg_wr_data;valid_q<=1;upload_index<=upload_index+1'b1;
     end else begin upload_abort_q<=1;error_q<=1;end
     default:begin end
    endcase
   end
  end
 end
endmodule
