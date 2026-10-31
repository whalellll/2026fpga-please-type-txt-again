package e91c.core
import chisel3._
import chisel3.util._
import e91c.mem._
// Wiring boundary extracted from rv32_core.v; cycle behavior is unchanged.
class CoreMemory extends Module {
  val io = IO(new Bundle {
    val memoryStoreData = Output(UInt(32.W))
    val memoryReplayValid = Output(Bool())
    val memoryReplayTag = Output(UInt(5.W))
    val retireMask = Input(UInt(32.W))
    val fatalStoreError = Output(Bool())
    val readResponseStatus = Input(UInt(2.W))
    val instructionReadError = Output(Bool())
    val memoryRetireValid = Input(Vec(2, Bool()))
    val memoryRetireTag = Input(Vec(2, UInt(5.W)))
    val privilege = Input(UInt(2.W))
    val dataPrivilege = Input(UInt(2.W))
    val vmSatp = Input(UInt(32.W))
    val vmStatus = Input(UInt(32.W))
    val translationFence = Input(Bool())
    val instructionAccept = Input(Bool())
    val instructionCancel = Input(Bool())
    val instructionFaults = Output(UInt(e91c.config.Params.EXCP_NUM.W))
    val arready = Input(UInt(1.W))
    val awready = Input(UInt(1.W))
    val axi_araddr_line = Output(UInt(32.W))
    val axi_arid_line = Output(UInt(4.W))
    val axi_arlen_line = Output(UInt(4.W))
    val axi_arsize_line = Output(UInt(3.W))
    val axi_arvalid_line = Output(UInt(1.W))
    val axi_awaddr_line = Output(UInt(32.W))
    val axi_awlen_line = Output(UInt(4.W))
    val axi_awsize_line = Output(UInt(3.W))
    val axi_awvalid_line = Output(UInt(1.W))
    val axi_bready_line = Output(UInt(1.W))
    val axi_rready_line = Output(UInt(1.W))
    val axi_wdata_line = Output(UInt(32.W))
    val axi_wlast_line = Output(UInt(1.W))
    val axi_wstrb_line = Output(UInt(4.W))
    val axi_wvalid_line = Output(UInt(1.W))
    val bvalid = Input(UInt(1.W))
    val cmt_sb_push_data = Input(UInt(32.W))
    val cmt_sb_push_paddr = Input(UInt(32.W))
    val cmt_sb_push_robid = Input(UInt(5.W))
    val cmt_sb_push_size = Input(UInt(3.W))
    val cmt_sb_push_uncached = Input(UInt(1.W))
    val cmt_sb_push_valid = Input(UInt(1.W))
    val cmt_sb_push_wstrb = Input(UInt(4.W))
    val dc_full_flush_done = Output(UInt(1.W))
    val flush = Input(UInt(1.W))
    val ic_l2_rd_addr = Input(UInt(32.W))
    val ic_l2_rd_req = Input(UInt(1.W))
    val ic_l2_rd_type = Input(UInt(3.W))
    val ifu_pma_req = Input(UInt(1.W))
    val ifu_pma_vaddr = Input(UInt(32.W))
    val l2_ic_rd_rdy = Output(UInt(1.W))
    val l2_ic_ret_data = Output(UInt(128.W))
    val l2_ic_ret_last = Output(UInt(1.W))
    val l2_ic_ret_valid = Output(UInt(1.W))
    val lsu_a_base_probe_robid = Output(UInt(5.W))
    val lsu_early_robid_raw = Output(UInt(5.W))
    val lsu_early_valid_raw = Output(UInt(1.W))
    val lsu_pair_ready = Output(UInt(1.W))
    val lsu_plain_only = Output(UInt(1.W))
    val lsu_q_base_probe_robid = Output(UInt(5.W))
    val lsu_ready = Output(UInt(1.W))
    val lsu_rob_head_enc = Input(UInt(5.W))
    val lsu_unc_inflight = Output(UInt(1.W))
    val mem2_wb_data = Output(UInt(32.W))
    val mem2_wb_paddr = Output(UInt(32.W))
    val mem2_wb_robid = Output(UInt(5.W))
    val mem2_wb_size = Output(UInt(3.W))
    val mem2_wb_vaddr = Output(UInt(32.W))
    val mem2_wb_valid = Output(UInt(1.W))
    val mem_fast_wb_data = Output(UInt(32.W))
    val mem_fast_wb_robid = Output(UInt(5.W))
    val mem_fast_wb_valid = Output(UInt(1.W))
    val mem_miss_wait_robids = Output(UInt(10.W))
    val mem_miss_wait_valid = Output(UInt(2.W))
    val mem_pending_load_robids = Output(UInt(20.W))
    val mem_pending_load_valid = Output(UInt(4.W))
    val mem_wb_data_raw = Output(UInt(32.W))
    val mem_wb_excp_raw = Output(UInt(e91c.config.Params.EXCP_NUM.W))
    val mem_wb_paddr_raw = Output(UInt(32.W))
    val mem_wb_robid_raw = Output(UInt(5.W))
    val mem_wb_size_raw = Output(UInt(3.W))
    val mem_wb_uncached_raw = Output(UInt(1.W))
    val mem_wb_vaddr_raw = Output(UInt(32.W))
    val mem_wb_valid_raw = Output(UInt(1.W))
    val mem_wb_wstrb_raw = Output(UInt(4.W))
    val pma_i_direct_excp = Output(UInt(1.W))
    val pma_i_direct_mat = Output(UInt(2.W))
    val pma_i_direct_ok = Output(UInt(1.W))
    val pma_i_direct_paddr = Output(UInt(32.W))
    val pma_i_inst_addr_misaligned = Output(UInt(1.W))
    val pma_i_mat = Output(UInt(2.W))
    val pma_i_paddr = Output(UInt(32.W))
    val pma_i_ready = Output(UInt(1.W))
    val rdata = Input(UInt(32.W))
    val resetn = Input(UInt(1.W))
    val rid = Input(UInt(4.W))
    val rlast = Input(UInt(1.W))
    val rob_a_base_data = Input(UInt(32.W))
    val rob_a_base_ready = Input(UInt(1.W))
    val rob_empty = Input(UInt(1.W))
    val rob_q_base_data = Input(UInt(32.W))
    val rob_q_base_ready = Input(UInt(1.W))
    val rsm_issue_base = Input(UInt(32.W))
    val rsm_issue_base_ready = Input(UInt(1.W))
    val rsm_issue_base_robid = Input(UInt(5.W))
    val rsm_issue_imm = Input(UInt(32.W))
    val rsm_issue_mem_op = Input(UInt(e91c.config.MemOp.NUM.W))
    val rsm_issue_pair_base = Input(UInt(32.W))
    val rsm_issue_pair_imm = Input(UInt(32.W))
    val rsm_issue_pair_mem_op = Input(UInt(e91c.config.MemOp.NUM.W))
    val rsm_issue_pair_robid = Input(UInt(5.W))
    val rsm_issue_pair_valid = Input(UInt(1.W))
    val rsm_issue_robid = Input(UInt(5.W))
    val rsm_issue_valid = Input(UInt(1.W))
    val rsm_issue_order_speculative = Input(UInt(1.W))
    val rsm_issue_order_store_tag = Input(UInt(5.W))
    val rsm_issue_wdata = Input(UInt(32.W))
    val rsm_issue_wdata_ready = Input(UInt(1.W))
    val rsm_issue_wdata_robid = Input(UInt(5.W))
    val rv_fencei_issue = Input(UInt(1.W))
    val rvalid = Input(UInt(1.W))
    val sb_empty = Output(UInt(1.W))
    val sb_full = Output(UInt(1.W))
    val wready = Input(UInt(1.W))
  })
  val arready = Wire(UInt(1.W))
  val awready = Wire(UInt(1.W))
  val axi_araddr_line = Wire(UInt(32.W))
  val axi_arid_line = Wire(UInt(4.W))
  val axi_arlen_line = Wire(UInt(4.W))
  val axi_arsize_line = Wire(UInt(3.W))
  val axi_arvalid_line = Wire(UInt(1.W))
  val axi_awaddr_line = Wire(UInt(32.W))
  val axi_awlen_line = Wire(UInt(4.W))
  val axi_awsize_line = Wire(UInt(3.W))
  val axi_awvalid_line = Wire(UInt(1.W))
  val axi_bready_line = Wire(UInt(1.W))
  val axi_rready_line = Wire(UInt(1.W))
  val axi_wdata_line = Wire(UInt(32.W))
  val axi_wlast_line = Wire(UInt(1.W))
  val axi_wstrb_line = Wire(UInt(4.W))
  val axi_wvalid_line = Wire(UInt(1.W))
  val bvalid = Wire(UInt(1.W))
  val cmt_sb_push_data = Wire(UInt(32.W))
  val cmt_sb_push_paddr = Wire(UInt(32.W))
  val cmt_sb_push_robid = Wire(UInt(5.W))
  val cmt_sb_push_size = Wire(UInt(3.W))
  val cmt_sb_push_uncached = Wire(UInt(1.W))
  val cmt_sb_push_valid = Wire(UInt(1.W))
  val cmt_sb_push_wstrb = Wire(UInt(4.W))
  val dc_full_flush_done = Wire(UInt(1.W))
  val dc_l2_rd_addr = Wire(UInt(32.W))
  val dc_l2_rd_req = Wire(UInt(1.W))
  val dc_l2_rd_type = Wire(UInt(3.W))
  val dc_l2_wr_addr = Wire(UInt(32.W))
  val dc_l2_wr_data = Wire(UInt(128.W))
  val dc_l2_wr_req = Wire(UInt(1.W))
  val dc_l2_wr_strb = Wire(UInt(4.W))
  val dc_l2_wr_type = Wire(UInt(3.W))
  val dc_l2_wr_write_through = Wire(UInt(1.W))
  val dc_ldq_addr_ok = Wire(UInt(1.W))
  val dc_ldq_load_op = Wire(UInt(4.W))
  val dc_ldq_paddr = Wire(UInt(32.W))
  val dc_ldq_pair_paddr = Wire(UInt(32.W))
  val dc_ldq_pair_valid = Wire(UInt(1.W))
  val dc_ldq_pair_word = Wire(UInt(3.W))
  val dc_ldq_req = Wire(UInt(1.W))
  val dc_ldq_robid = Wire(UInt(5.W))
  val dc_ldq_size = Wire(UInt(3.W))
  val dc_ldq_uncached = Wire(UInt(1.W))
  val dc_ldq_vindex = Wire(UInt(7.W))
  val dc_lsu_addr_ok = Wire(UInt(1.W))
  val dc_lsu_data_ok = Wire(UInt(1.W))
  val dc_lsu_miss = Wire(UInt(1.W))
  val dc_lsu_mshr_ok = Wire(UInt(1.W))
  val dc_lsu_mshr_rdata = Wire(UInt(32.W))
  val dc_lsu_mshr_robid = Wire(UInt(5.W))
  val dc_lsu_pair_miss = Wire(UInt(1.W))
  val dc_lsu_pair_ok = Wire(UInt(1.W))
  val dc_lsu_pair_rdata = Wire(UInt(32.W))
  val dc_lsu_rdata = Wire(UInt(32.W))
  val dc_lsu_resp_robid = Wire(UInt(5.W))
  val dc_sb_addr_ok = Wire(UInt(1.W))
  val dc_sb_done = Wire(UInt(1.W))
  val flush = Wire(UInt(1.W))
  val ic_l2_rd_addr = Wire(UInt(32.W))
  val ic_l2_rd_req = Wire(UInt(1.W))
  val ic_l2_rd_type = Wire(UInt(3.W))
  val ifu_pma_req = Wire(UInt(1.W))
  val ifu_pma_vaddr = Wire(UInt(32.W))
  val l2_dc_rd_rdy = Wire(UInt(1.W))
  val l2_dc_ret_data = Wire(UInt(128.W))
  val l2_dc_ret_last = Wire(UInt(1.W))
  val l2_dc_ret_valid = Wire(UInt(1.W))
  val l2_dc_wr_rdy = Wire(UInt(1.W))
  val l2_ic_rd_rdy = Wire(UInt(1.W))
  val l2_ic_ret_data = Wire(UInt(128.W))
  val l2_ic_ret_last = Wire(UInt(1.W))
  val l2_ic_ret_valid = Wire(UInt(1.W))
  val l2_mem2_rd_addr = Wire(UInt(32.W))
  val l2_mem2_rd_req = Wire(UInt(1.W))
  val l2_mem2_rd_type = Wire(UInt(3.W))
  val l2_mem_rd_addr = Wire(UInt(32.W))
  val l2_mem_rd_req = Wire(UInt(1.W))
  val l2_mem_rd_type = Wire(UInt(3.W))
  val l2_mem_wr_addr = Wire(UInt(32.W))
  val l2_mem_wr_data = Wire(UInt(128.W))
  val l2_mem_wr_req = Wire(UInt(1.W))
  val l2_mem_wr_strb = Wire(UInt(4.W))
  val l2_mem_wr_type = Wire(UInt(3.W))
  val lsu_a_base_probe_robid = Wire(UInt(5.W))
  val lsu_dc_cancel = Wire(UInt(1.W))
  val lsu_dc_load_op = Wire(UInt(4.W))
  val lsu_dc_paddr = Wire(UInt(32.W))
  val lsu_dc_pair_paddr = Wire(UInt(32.W))
  val lsu_dc_pair_valid = Wire(UInt(1.W))
  val lsu_dc_pair_word = Wire(UInt(3.W))
  val lsu_dc_req = Wire(UInt(1.W))
  val lsu_dc_resp_ready = Wire(UInt(1.W))
  val lsu_dc_robid = Wire(UInt(5.W))
  val lsu_dc_size = Wire(UInt(3.W))
  val lsu_dc_uncached = Wire(UInt(1.W))
  val lsu_dc_vindex = Wire(UInt(7.W))
  val lsu_early_robid_raw = Wire(UInt(5.W))
  val lsu_early_valid_raw = Wire(UInt(1.W))
  val lsu_pair_ready = Wire(UInt(1.W))
  val lsu_plain_only = Wire(UInt(1.W))
  val lsu_pma_is_store = Wire(UInt(1.W))
  val lsu_pma_req = Wire(UInt(1.W))
  val lsu_pma_vaddr = Wire(UInt(32.W))
  val lsu_q_base_probe_robid = Wire(UInt(5.W))
  val lsu_ready = Wire(UInt(1.W))
  val lsu_rob_head_enc = Wire(UInt(5.W))
  val lsu_sb_pair_qpaddr = Wire(UInt(30.W))
  val lsu_sb_qpaddr = Wire(UInt(30.W))
  val lsu_sb_quncached = Wire(UInt(1.W))
  val lsu_sb_qvalid = Wire(UInt(1.W))
  val lsu_unc_inflight = Wire(UInt(1.W))
  val mem2_l2_rd_rdy = Wire(UInt(1.W))
  val mem2_l2_ret_data = Wire(UInt(128.W))
  val mem2_l2_ret_last = Wire(UInt(1.W))
  val mem2_l2_ret_valid = Wire(UInt(1.W))
  val mem2_wb_data = Wire(UInt(32.W))
  val mem2_wb_paddr = Wire(UInt(32.W))
  val mem2_wb_robid = Wire(UInt(5.W))
  val mem2_wb_size = Wire(UInt(3.W))
  val mem2_wb_vaddr = Wire(UInt(32.W))
  val mem2_wb_valid = Wire(UInt(1.W))
  val mem_fast_mdu_data = Wire(UInt(32.W))
  val mem_fast_mdu_robid = Wire(UInt(5.W))
  val mem_fast_mdu_valid = Wire(UInt(1.W))
  val mem_fast_wb_data = Wire(UInt(32.W))
  val mem_fast_wb_robid = Wire(UInt(5.W))
  val mem_fast_wb_valid = Wire(UInt(1.W))
  val mem_hold_wb_data = Wire(UInt(32.W))
  val mem_hold_wb_robid = Wire(UInt(5.W))
  val mem_hold_wb_valid = Wire(UInt(1.W))
  val mem_l2_rd_rdy = Wire(UInt(1.W))
  val mem_l2_ret_data = Wire(UInt(128.W))
  val mem_l2_ret_last = Wire(UInt(1.W))
  val mem_l2_ret_valid = Wire(UInt(1.W))
  val mem_l2_wr_rdy = Wire(UInt(1.W))
  val mem_miss_wait_robids = Wire(UInt(10.W))
  val mem_miss_wait_valid = Wire(UInt(2.W))
  val mem_pending_load_robids = Wire(UInt(20.W))
  val mem_pending_load_valid = Wire(UInt(4.W))
  val mem_wb_data_raw = Wire(UInt(32.W))
  val mem_wb_excp_raw = Wire(UInt(e91c.config.Params.EXCP_NUM.W))
  val mem_wb_paddr_raw = Wire(UInt(32.W))
  val mem_wb_robid_raw = Wire(UInt(5.W))
  val mem_wb_size_raw = Wire(UInt(3.W))
  val mem_wb_uncached_raw = Wire(UInt(1.W))
  val mem_wb_vaddr_raw = Wire(UInt(32.W))
  val mem_wb_valid_raw = Wire(UInt(1.W))
  val mem_wb_wstrb_raw = Wire(UInt(4.W))
  val pma_d_load_store_access_fault = Wire(UInt(1.W))
  val pma_d_mat = Wire(UInt(2.W))
  val pma_d_paddr = Wire(UInt(32.W))
  val pma_d_ready = Wire(UInt(1.W))
  val pma_i_direct_excp = Wire(UInt(1.W))
  val pma_i_direct_mat = Wire(UInt(2.W))
  val pma_i_direct_ok = Wire(UInt(1.W))
  val pma_i_direct_paddr = Wire(UInt(32.W))
  val pma_i_inst_addr_misaligned = Wire(UInt(1.W))
  val pma_i_mat = Wire(UInt(2.W))
  val pma_i_paddr = Wire(UInt(32.W))
  val pma_i_ready = Wire(UInt(1.W))
  val rdata = Wire(UInt(32.W))
  val resetn = Wire(UInt(1.W))
  val rid = Wire(UInt(4.W))
  val rlast = Wire(UInt(1.W))
  val rob_a_base_data = Wire(UInt(32.W))
  val rob_a_base_ready = Wire(UInt(1.W))
  val rob_empty = Wire(UInt(1.W))
  val rob_q_base_data = Wire(UInt(32.W))
  val rob_q_base_ready = Wire(UInt(1.W))
  val rsm_issue_base = Wire(UInt(32.W))
  val rsm_issue_base_ready = Wire(UInt(1.W))
  val rsm_issue_base_robid = Wire(UInt(5.W))
  val rsm_issue_imm = Wire(UInt(32.W))
  val rsm_issue_mem_op = Wire(UInt(e91c.config.MemOp.NUM.W))
  val rsm_issue_pair_base = Wire(UInt(32.W))
  val rsm_issue_pair_imm = Wire(UInt(32.W))
  val rsm_issue_pair_mem_op = Wire(UInt(e91c.config.MemOp.NUM.W))
  val rsm_issue_pair_robid = Wire(UInt(5.W))
  val rsm_issue_pair_valid = Wire(UInt(1.W))
  val rsm_issue_robid = Wire(UInt(5.W))
  val rsm_issue_valid = Wire(UInt(1.W))
  val rsm_issue_order_speculative = Wire(UInt(1.W))
  val rsm_issue_order_store_tag = Wire(UInt(5.W))
  val rsm_issue_wdata = Wire(UInt(32.W))
  val rsm_issue_wdata_ready = Wire(UInt(1.W))
  val rsm_issue_wdata_robid = Wire(UInt(5.W))
  val rv_fencei_issue = Wire(UInt(1.W))
  val rvalid = Wire(UInt(1.W))
  val sb_dc_wr_data = Wire(UInt(32.W))
  val sb_dc_wr_paddr = Wire(UInt(32.W))
  val sb_dc_wr_req = Wire(UInt(1.W))
  val sb_dc_wr_size = Wire(UInt(3.W))
  val sb_dc_wr_strb = Wire(UInt(4.W))
  val sb_dc_wr_uncached = Wire(UInt(1.W))
  val sb_empty = Wire(UInt(1.W))
  val sb_full = Wire(UInt(1.W))
  val sb_pair_qmaybe = Wire(UInt(1.W))
  val sb_q_data = Wire(UInt(32.W))
  val sb_q_hit = Wire(UInt(1.W))
  val sb_q_maybe = Wire(UInt(1.W))
  val sb_q_partial = Wire(UInt(1.W))
  val sb_q_resp_paddr = Wire(UInt(30.W))
  val sb_q_resp_uncached = Wire(UInt(1.W))
  val sb_q_resp_valid = Wire(UInt(1.W))
  val wready = Wire(UInt(1.W))
  arready := io.arready
  awready := io.awready
  io.axi_araddr_line := axi_araddr_line
  io.axi_arid_line := axi_arid_line
  io.axi_arlen_line := axi_arlen_line
  io.axi_arsize_line := axi_arsize_line
  io.axi_arvalid_line := axi_arvalid_line
  io.axi_awaddr_line := axi_awaddr_line
  io.axi_awlen_line := axi_awlen_line
  io.axi_awsize_line := axi_awsize_line
  io.axi_awvalid_line := axi_awvalid_line
  io.axi_bready_line := axi_bready_line
  io.axi_rready_line := axi_rready_line
  io.axi_wdata_line := axi_wdata_line
  io.axi_wlast_line := axi_wlast_line
  io.axi_wstrb_line := axi_wstrb_line
  io.axi_wvalid_line := axi_wvalid_line
  bvalid := io.bvalid
  cmt_sb_push_data := io.cmt_sb_push_data
  cmt_sb_push_paddr := io.cmt_sb_push_paddr
  cmt_sb_push_robid := io.cmt_sb_push_robid
  cmt_sb_push_size := io.cmt_sb_push_size
  cmt_sb_push_uncached := io.cmt_sb_push_uncached
  cmt_sb_push_valid := io.cmt_sb_push_valid
  cmt_sb_push_wstrb := io.cmt_sb_push_wstrb
  io.dc_full_flush_done := dc_full_flush_done
  flush := io.flush
  ic_l2_rd_addr := io.ic_l2_rd_addr
  ic_l2_rd_req := io.ic_l2_rd_req
  ic_l2_rd_type := io.ic_l2_rd_type
  ifu_pma_req := io.ifu_pma_req
  ifu_pma_vaddr := io.ifu_pma_vaddr
  io.l2_ic_rd_rdy := l2_ic_rd_rdy
  io.l2_ic_ret_data := l2_ic_ret_data
  io.l2_ic_ret_last := l2_ic_ret_last
  io.l2_ic_ret_valid := l2_ic_ret_valid
  io.lsu_a_base_probe_robid := lsu_a_base_probe_robid
  io.lsu_early_robid_raw := lsu_early_robid_raw
  io.lsu_early_valid_raw := lsu_early_valid_raw
  io.lsu_pair_ready := lsu_pair_ready
  io.lsu_plain_only := lsu_plain_only
  io.lsu_q_base_probe_robid := lsu_q_base_probe_robid
  io.lsu_ready := lsu_ready
  lsu_rob_head_enc := io.lsu_rob_head_enc
  io.lsu_unc_inflight := lsu_unc_inflight
  io.mem2_wb_data := mem2_wb_data
  io.mem2_wb_paddr := mem2_wb_paddr
  io.mem2_wb_robid := mem2_wb_robid
  io.mem2_wb_size := mem2_wb_size
  io.mem2_wb_vaddr := mem2_wb_vaddr
  io.mem2_wb_valid := mem2_wb_valid
  io.mem_fast_wb_data := mem_fast_wb_data
  io.mem_fast_wb_robid := mem_fast_wb_robid
  io.mem_fast_wb_valid := mem_fast_wb_valid
  io.mem_miss_wait_robids := mem_miss_wait_robids
  io.mem_miss_wait_valid := mem_miss_wait_valid
  io.mem_pending_load_robids := mem_pending_load_robids
  io.mem_pending_load_valid := mem_pending_load_valid
  io.mem_wb_data_raw := mem_wb_data_raw
  io.mem_wb_excp_raw := mem_wb_excp_raw
  io.mem_wb_paddr_raw := mem_wb_paddr_raw
  io.mem_wb_robid_raw := mem_wb_robid_raw
  io.mem_wb_size_raw := mem_wb_size_raw
  io.mem_wb_uncached_raw := mem_wb_uncached_raw
  io.mem_wb_vaddr_raw := mem_wb_vaddr_raw
  io.mem_wb_valid_raw := mem_wb_valid_raw
  io.mem_wb_wstrb_raw := mem_wb_wstrb_raw
  io.pma_i_direct_excp := pma_i_direct_excp
  io.pma_i_direct_mat := pma_i_direct_mat
  io.pma_i_direct_ok := pma_i_direct_ok
  io.pma_i_direct_paddr := pma_i_direct_paddr
  io.pma_i_inst_addr_misaligned := pma_i_inst_addr_misaligned
  io.pma_i_mat := pma_i_mat
  io.pma_i_paddr := pma_i_paddr
  io.pma_i_ready := pma_i_ready
  rdata := io.rdata
  resetn := io.resetn
  rid := io.rid
  rlast := io.rlast
  rob_a_base_data := io.rob_a_base_data
  rob_a_base_ready := io.rob_a_base_ready
  rob_empty := io.rob_empty
  rob_q_base_data := io.rob_q_base_data
  rob_q_base_ready := io.rob_q_base_ready
  rsm_issue_base := io.rsm_issue_base
  rsm_issue_base_ready := io.rsm_issue_base_ready
  rsm_issue_base_robid := io.rsm_issue_base_robid
  rsm_issue_imm := io.rsm_issue_imm
  rsm_issue_mem_op := io.rsm_issue_mem_op
  rsm_issue_pair_base := io.rsm_issue_pair_base
  rsm_issue_pair_imm := io.rsm_issue_pair_imm
  rsm_issue_pair_mem_op := io.rsm_issue_pair_mem_op
  rsm_issue_pair_robid := io.rsm_issue_pair_robid
  rsm_issue_pair_valid := io.rsm_issue_pair_valid
  rsm_issue_robid := io.rsm_issue_robid
  rsm_issue_valid := io.rsm_issue_valid
  rsm_issue_order_speculative := io.rsm_issue_order_speculative
  rsm_issue_order_store_tag := io.rsm_issue_order_store_tag
  rsm_issue_wdata := io.rsm_issue_wdata
  rsm_issue_wdata_ready := io.rsm_issue_wdata_ready
  rsm_issue_wdata_robid := io.rsm_issue_wdata_robid
  rv_fencei_issue := io.rv_fencei_issue
  rvalid := io.rvalid
  io.sb_empty := sb_empty
  io.sb_full := sb_full
  wready := io.wready
  val pmaDataAccept = Wire(Bool())
  val dcReadError = Wire(Bool()); val dcMissError = Wire(Bool())
  val l2DataReadError = Wire(Bool())
  val memoryReadError = Wire(Bool()); val memoryInstructionReadError = Wire(Bool())
  val atomic = Module(new AtomicSequencer)
  // Translation/PMA completion is a command boundary. Keep the accepted
  // physical address and operand in a one-entry owner until AtomicSequencer
  // consumes it; the frontend/shared-translation ready cone must not reach the
  // atomic result registers in the same cycle.
  val atomicCommandValid = RegInit(false.B)
  val atomicCommand = Reg(new AtomicRequest)
  atomic.io.flush := io.flush.asBool
  atomic.io.invalidateReservation := io.cmt_sb_push_valid.asBool
  val atomicRetireHits = VecInit((0 until 2).map(i =>
    io.memoryRetireValid(i) && io.memoryRetireTag(i) === atomic.io.result.bits.robid))
  atomic.io.commit := atomicRetireHits.asUInt.orR
  atomic.io.commitRobid := atomic.io.result.bits.robid
  val pmaDataPageFault = Wire(Bool())
  val pageRequest = Wire(Decoupled(UInt(34.W)))
  val pageResponse = Wire(Decoupled(new PageTableReadResponse))
  private def connect_u_dc_load_req_fifo(): Unit = {
    val u_dc_load_req_fifo = Module(new DcacheLoadReqFifo)
    u_dc_load_req_fifo.io.flush := (lsu_dc_cancel).asBool
    u_dc_load_req_fifo.io.sValid := (lsu_dc_req).asBool
    u_dc_load_req_fifo.io.sVindex := lsu_dc_vindex
    u_dc_load_req_fifo.io.sPaddr := lsu_dc_paddr
    u_dc_load_req_fifo.io.sSize := lsu_dc_size
    u_dc_load_req_fifo.io.sLoadOp := lsu_dc_load_op
    u_dc_load_req_fifo.io.sUncached := (lsu_dc_uncached).asBool
    u_dc_load_req_fifo.io.sRobid := lsu_dc_robid
    u_dc_load_req_fifo.io.sPairValid := (lsu_dc_pair_valid).asBool
    u_dc_load_req_fifo.io.sPairWord := lsu_dc_pair_word
    u_dc_load_req_fifo.io.sPairPaddr := lsu_dc_pair_paddr
    dc_lsu_addr_ok := u_dc_load_req_fifo.io.sReady.asUInt
    dc_ldq_req := u_dc_load_req_fifo.io.mValid.asUInt
    dc_ldq_vindex := u_dc_load_req_fifo.io.mVindex.asUInt
    dc_ldq_paddr := u_dc_load_req_fifo.io.mPaddr.asUInt
    dc_ldq_size := u_dc_load_req_fifo.io.mSize.asUInt
    dc_ldq_load_op := u_dc_load_req_fifo.io.mLoadOp.asUInt
    dc_ldq_uncached := u_dc_load_req_fifo.io.mUncached.asUInt
    dc_ldq_robid := u_dc_load_req_fifo.io.mRobid.asUInt
    dc_ldq_pair_valid := u_dc_load_req_fifo.io.mPairValid.asUInt
    dc_ldq_pair_word := u_dc_load_req_fifo.io.mPairWord.asUInt
    dc_ldq_pair_paddr := u_dc_load_req_fifo.io.mPairPaddr.asUInt
    u_dc_load_req_fifo.io.mReady := (dc_ldq_addr_ok).asBool
  }
  connect_u_dc_load_req_fifo()

  private def connect_u_lsu(): Unit = {
    val u_lsu = Module(new Lsu)
    u_lsu.io.dcError := dcReadError
    u_lsu.io.dcMshrError := dcMissError
    val atomicCommandEnqueue = u_lsu.io.atomicRequest.valid &&
      !atomicCommandValid && !io.flush.asBool
    u_lsu.io.atomicRequest.ready := !atomicCommandValid && !io.flush.asBool
    atomic.io.request.valid := atomicCommandValid && !io.flush.asBool
    atomic.io.request.bits := atomicCommand
    // A translated command waiting in this boundary register owns the atomic
    // path just like a command already accepted by AtomicSequencer. This keeps
    // younger memory operations behind it during the added cycle.
    u_lsu.io.atomicBusy := atomic.io.busy || atomicCommandValid
    when(io.flush.asBool) {
      atomicCommandValid := false.B
    }.otherwise {
      when(atomic.io.request.fire) {
        atomicCommandValid := false.B
      }
      when(atomicCommandEnqueue) {
        atomicCommandValid := true.B
        atomicCommand := u_lsu.io.atomicRequest.bits
      }
    }
    u_lsu.io.retireMask := io.retireMask
    io.memoryReplayValid := u_lsu.io.replayValid
    io.memoryReplayTag := u_lsu.io.replayTag
    atomic.io.result.ready := !u_lsu.io.wbValid
    u_lsu.io.pmaDPageFault := pmaDataPageFault
    pmaDataAccept := u_lsu.io.pmaDAccept
    u_lsu.io.flush := (flush).asBool
    u_lsu.io.issueValid := (rsm_issue_valid).asBool
    u_lsu.io.issueRobid := rsm_issue_robid
    u_lsu.io.issueMemOp := rsm_issue_mem_op
    u_lsu.io.issueOrderSpeculative := rsm_issue_order_speculative.asBool
    u_lsu.io.issueOrderStoreTag := rsm_issue_order_store_tag
    u_lsu.io.issueBase := rsm_issue_base
    u_lsu.io.issueBaseReady := (rsm_issue_base_ready).asBool
    u_lsu.io.issueBaseRobid := rsm_issue_base_robid
    u_lsu.io.issueWdata := rsm_issue_wdata
    u_lsu.io.issueWdataReady := (rsm_issue_wdata_ready).asBool
    u_lsu.io.issueWdataRobid := rsm_issue_wdata_robid
    u_lsu.io.issueImm := rsm_issue_imm
    lsu_ready := u_lsu.io.lsuReady.asUInt
    lsu_plain_only := u_lsu.io.lsuPlainOnly.asUInt
    u_lsu.io.issuePairValid := (rsm_issue_pair_valid).asBool
    u_lsu.io.issuePairRobid := rsm_issue_pair_robid
    u_lsu.io.issuePairMemOp := rsm_issue_pair_mem_op
    u_lsu.io.issuePairBase := rsm_issue_pair_base
    u_lsu.io.issuePairImm := rsm_issue_pair_imm
    lsu_pair_ready := u_lsu.io.lsuPairReady.asUInt
    lsu_pma_req := u_lsu.io.pmaDReq.asUInt
    lsu_pma_vaddr := u_lsu.io.pmaDVaddr.asUInt
    lsu_pma_is_store := u_lsu.io.pmaDIsStore.asUInt
    u_lsu.io.pmaDPaddr := pma_d_paddr
    u_lsu.io.pmaDMat := pma_d_mat
    u_lsu.io.pmaDReady := (pma_d_ready).asBool
    u_lsu.io.pmaDExcpAfault := (pma_d_load_store_access_fault).asBool
    lsu_dc_req := u_lsu.io.dcReq.asUInt
    lsu_dc_vindex := u_lsu.io.dcVindex.asUInt
    lsu_dc_paddr := u_lsu.io.dcPaddr.asUInt
    lsu_dc_size := u_lsu.io.dcSize.asUInt
    lsu_dc_load_op := u_lsu.io.dcLoadOp.asUInt
    lsu_dc_uncached := u_lsu.io.dcUncached.asUInt
    lsu_dc_robid := u_lsu.io.dcRobid.asUInt
    u_lsu.io.dcAddrOk := (dc_lsu_addr_ok).asBool
    u_lsu.io.dcDataOk := (dc_lsu_data_ok).asBool
    u_lsu.io.dcRdata := dc_lsu_rdata
    u_lsu.io.dcRespRobid := dc_lsu_resp_robid
    lsu_dc_resp_ready := u_lsu.io.dcRespReady.asUInt
    lsu_dc_cancel := u_lsu.io.dcCancel.asUInt
    u_lsu.io.dcMiss := (dc_lsu_miss).asBool
    u_lsu.io.dcMshrDataOk := (dc_lsu_mshr_ok).asBool
    u_lsu.io.dcMshrRdata := dc_lsu_mshr_rdata
    u_lsu.io.dcMshrRobid := dc_lsu_mshr_robid
    lsu_dc_pair_valid := u_lsu.io.dcPairValid.asUInt
    lsu_dc_pair_word := u_lsu.io.dcPairWord.asUInt
    lsu_dc_pair_paddr := u_lsu.io.dcPairPaddr.asUInt
    u_lsu.io.dcPairDataOk := (dc_lsu_pair_ok).asBool
    u_lsu.io.dcPairMiss := (dc_lsu_pair_miss).asBool
    u_lsu.io.dcPairRdata := dc_lsu_pair_rdata
    lsu_sb_qvalid := u_lsu.io.sbQueryValid.asUInt
    lsu_sb_qpaddr := u_lsu.io.sbQueryPaddr.asUInt
    lsu_sb_quncached := u_lsu.io.sbQueryUncached.asUInt
    u_lsu.io.sbQueryRespValid := (sb_q_resp_valid).asBool
    u_lsu.io.sbQueryRespPaddr := sb_q_resp_paddr
    u_lsu.io.sbQueryRespUncached := (sb_q_resp_uncached).asBool
    u_lsu.io.sbQueryMaybe := (sb_q_maybe).asBool
    u_lsu.io.sbQueryHit := (sb_q_hit).asBool
    u_lsu.io.sbQueryData := sb_q_data
    u_lsu.io.sbQueryPartial := (sb_q_partial).asBool
    u_lsu.io.sbEmpty := (sb_empty).asBool
    lsu_sb_pair_qpaddr := u_lsu.io.sbPairQueryPaddr.asUInt
    u_lsu.io.sbPairQueryMaybe := (sb_pair_qmaybe).asBool
    u_lsu.io.robHeadRobid := lsu_rob_head_enc
    u_lsu.io.robHeadValid := ((~(rob_empty))).asBool
    u_lsu.io.stRetireValid := (cmt_sb_push_valid).asBool
    u_lsu.io.stRetireRobid := cmt_sb_push_robid
    lsu_a_base_probe_robid := u_lsu.io.aBaseProbeRobid.asUInt
    u_lsu.io.robABaseReady := (rob_a_base_ready).asBool
    u_lsu.io.robABaseData := rob_a_base_data
    lsu_q_base_probe_robid := u_lsu.io.qBaseProbeRobid.asUInt
    u_lsu.io.robQBaseReady := (rob_q_base_ready).asBool
    u_lsu.io.robQBaseData := rob_q_base_data
    lsu_unc_inflight := u_lsu.io.uncachedLdInflight.asUInt
    mem_wb_valid_raw := u_lsu.io.wbValid.asUInt
    mem_wb_robid_raw := u_lsu.io.wbRobid.asUInt
    mem_wb_data_raw := u_lsu.io.wbData.asUInt
    io.memoryStoreData := u_lsu.io.wbData
    mem_wb_paddr_raw := u_lsu.io.wbPaddr.asUInt
    mem_wb_vaddr_raw := u_lsu.io.wbVaddr.asUInt
    mem_wb_wstrb_raw := u_lsu.io.wbWstrb.asUInt
    mem_wb_size_raw := u_lsu.io.wbSize.asUInt
    mem_wb_uncached_raw := u_lsu.io.wbUncached.asUInt
    mem_wb_excp_raw := u_lsu.io.wbExcp.asUInt
    mem2_wb_valid := u_lsu.io.pairWbValid.asUInt
    mem2_wb_robid := u_lsu.io.pairWbRobid.asUInt
    mem2_wb_data := u_lsu.io.pairWbData.asUInt
    mem2_wb_paddr := u_lsu.io.pairWbPaddr.asUInt
    mem2_wb_vaddr := u_lsu.io.pairWbVaddr.asUInt
    mem2_wb_size := u_lsu.io.pairWbSize.asUInt
    mem_fast_wb_valid := u_lsu.io.fastWbValid.asUInt
    mem_fast_wb_robid := u_lsu.io.fastWbRobid.asUInt
    mem_fast_wb_data := u_lsu.io.fastWbData.asUInt
    mem_fast_mdu_valid := u_lsu.io.fastMduValid.asUInt
    mem_fast_mdu_robid := u_lsu.io.fastMduRobid.asUInt
    mem_fast_mdu_data := u_lsu.io.fastMduData.asUInt
    mem_miss_wait_valid := u_lsu.io.missWaitValid.asUInt
    mem_miss_wait_robids := u_lsu.io.missWaitRobids.asUInt
    mem_pending_load_valid := u_lsu.io.pendingLoadValid.asUInt
    mem_pending_load_robids := u_lsu.io.pendingLoadRobids.asUInt
    mem_hold_wb_valid := u_lsu.io.holdWbValid.asUInt
    mem_hold_wb_robid := u_lsu.io.holdWbRobid.asUInt
    mem_hold_wb_data := u_lsu.io.holdWbData.asUInt
    // Predict at the cache lookup acceptance, after the decoupling FIFO.
    // Normal L1 hit data is available in the following selection cycle.
    lsu_early_valid_raw := (dc_ldq_req.asBool && dc_ldq_addr_ok.asBool &&
      !dc_ldq_uncached.asBool && !flush.asBool).asUInt
    lsu_early_robid_raw := dc_ldq_robid
    when(atomic.io.result.fire) {
      mem_wb_valid_raw := 1.U
      mem_wb_robid_raw := atomic.io.result.bits.robid
      mem_wb_data_raw := atomic.io.result.bits.data
      io.memoryStoreData := atomic.io.result.bits.storeData
      mem_wb_paddr_raw := atomic.io.result.bits.physicalAddress
      mem_wb_vaddr_raw := atomic.io.result.bits.virtualAddress
      mem_wb_wstrb_raw := atomic.io.result.bits.storeMask
      mem_wb_size_raw := 2.U
      mem_wb_uncached_raw := 0.U
      mem_wb_excp_raw := Mux(atomic.io.result.bits.accessFault,32.U,0.U)
    }
  }
  connect_u_lsu()

  if (!sys.props.get("e91c.synthesis").contains("true")) {
    val atomicCommandWasBlocked = RegNext(
      atomicCommandValid && !atomic.io.request.ready && !io.flush.asBool, false.B)
    val atomicCommandPrevious = RegNext(atomicCommand.asUInt)
    when(atomicCommandWasBlocked) {
      assert(atomicCommandValid && atomicCommand.asUInt === atomicCommandPrevious,
        "translated atomic PA/owner/payload must remain stable under backpressure")
    }
    assert(!(atomicCommandValid && atomic.io.busy),
      "atomic boundary register and sequencer must not own two commands")
    when(atomic.io.request.fire) {
      assert(atomicCommandValid && !io.flush.asBool,
        "AtomicSequencer may only consume the registered translated owner")
    }
  }

  private def connect_u_store_buffer(): Unit = {
    val u_store_buffer = Module(new StoreBuffer)
    u_store_buffer.io.pushValid := (cmt_sb_push_valid).asBool
    u_store_buffer.io.pushPaddr := cmt_sb_push_paddr
    u_store_buffer.io.pushData := cmt_sb_push_data
    u_store_buffer.io.pushWstrb := cmt_sb_push_wstrb
    u_store_buffer.io.pushSize := cmt_sb_push_size
    u_store_buffer.io.pushUncached := (cmt_sb_push_uncached).asBool
    sb_full := u_store_buffer.io.sbFull.asUInt
    sb_empty := u_store_buffer.io.sbEmpty.asUInt
    sb_dc_wr_req := u_store_buffer.io.dcWrReq.asUInt
    sb_dc_wr_paddr := u_store_buffer.io.dcWrPaddr.asUInt
    sb_dc_wr_data := u_store_buffer.io.dcWrData.asUInt
    sb_dc_wr_strb := u_store_buffer.io.dcWrStrb.asUInt
    sb_dc_wr_size := u_store_buffer.io.dcWrSize.asUInt
    sb_dc_wr_uncached := u_store_buffer.io.dcWrUncached.asUInt
    u_store_buffer.io.dcWrAddrOk := (dc_sb_addr_ok).asBool
    u_store_buffer.io.dcWrDone := (dc_sb_done).asBool
    u_store_buffer.io.queryValid := (lsu_sb_qvalid).asBool
    u_store_buffer.io.queryPaddr := lsu_sb_qpaddr
    u_store_buffer.io.queryUncached := (lsu_sb_quncached).asBool
    sb_q_resp_valid := u_store_buffer.io.queryRespValid.asUInt
    sb_q_resp_paddr := u_store_buffer.io.queryRespPaddr.asUInt
    sb_q_resp_uncached := u_store_buffer.io.queryRespUncached.asUInt
    sb_q_maybe := u_store_buffer.io.queryMaybe.asUInt
    sb_q_hit := u_store_buffer.io.queryHit.asUInt
    sb_q_data := u_store_buffer.io.queryData.asUInt
    sb_q_partial := u_store_buffer.io.queryPartial.asUInt
    u_store_buffer.io.pairQueryPaddr := lsu_sb_pair_qpaddr
    sb_pair_qmaybe := u_store_buffer.io.pairQueryMaybe.asUInt
  }
  connect_u_store_buffer()

  private def connect_u_pma(): Unit = {
    val u_pma = Module(new PmaMmu)
    u_pma.io.privilege := io.privilege
    u_pma.io.dataPrivilege := io.dataPrivilege
    u_pma.io.satp := io.vmSatp
    u_pma.io.status := io.vmStatus
    u_pma.io.flush := flush.asBool
    u_pma.io.instructionCancel := io.instructionCancel
    u_pma.io.fence := io.translationFence
    u_pma.io.iAccept := io.instructionAccept
    u_pma.io.dAccept := pmaDataAccept
    u_pma.io.dIsStore := lsu_pma_is_store.asBool
    pmaDataPageFault := u_pma.io.dPageFault
    io.instructionFaults := u_pma.io.iFaults
    pageRequest.valid := u_pma.io.pageRequest.valid
    pageRequest.bits := u_pma.io.pageRequest.bits
    u_pma.io.pageRequest.ready := pageRequest.ready
    u_pma.io.pageResponse.valid := pageResponse.valid
    u_pma.io.pageResponse.bits := pageResponse.bits
    pageResponse.ready := u_pma.io.pageResponse.ready
    u_pma.io.iReq := (ifu_pma_req).asBool
    u_pma.io.iVaddr := ifu_pma_vaddr
    pma_i_ready := u_pma.io.iReady.asUInt
    pma_i_paddr := u_pma.io.iPaddr.asUInt
    pma_i_mat := u_pma.io.iMat.asUInt
    pma_i_inst_addr_misaligned := u_pma.io.iMisaligned.asUInt
    pma_i_direct_ok := u_pma.io.iDirectOk.asUInt
    pma_i_direct_paddr := u_pma.io.iDirectPaddr.asUInt
    pma_i_direct_mat := u_pma.io.iDirectMat.asUInt
    pma_i_direct_excp := u_pma.io.iDirectExcp.asUInt
    u_pma.io.dReq := (lsu_pma_req).asBool
    u_pma.io.dVaddr := lsu_pma_vaddr
    pma_d_ready := u_pma.io.dReady.asUInt
    pma_d_paddr := u_pma.io.dPaddr.asUInt
    pma_d_mat := u_pma.io.dMat.asUInt
    pma_d_load_store_access_fault := u_pma.io.dAccessFault.asUInt
  }
  connect_u_pma()

  private def connect_u_dcache(): Unit = {
    val u_dcache = withReset(!(resetn).asBool) { Module(new Dcache) }
    u_dcache.io.ldReq := (dc_ldq_req).asBool
    io.fatalStoreError := u_dcache.io.fatalStoreError
    u_dcache.io.ldVindex := dc_ldq_vindex
    u_dcache.io.ldPaddr := dc_ldq_paddr
    u_dcache.io.ldSize := dc_ldq_size
    u_dcache.io.ldOp := dc_ldq_load_op
    u_dcache.io.ldUncached := (dc_ldq_uncached).asBool
    u_dcache.io.ldRobid := dc_ldq_robid
    dc_ldq_addr_ok := u_dcache.io.ldAddrOk.asUInt
    dc_lsu_data_ok := u_dcache.io.ldDataOk.asUInt
    dc_lsu_rdata := u_dcache.io.ldRdata.asUInt
    dc_lsu_resp_robid := u_dcache.io.ldRespRobid.asUInt
    u_dcache.io.ldRespReady := (lsu_dc_resp_ready).asBool
    u_dcache.io.ldCancel := (lsu_dc_cancel).asBool
    dc_lsu_miss := u_dcache.io.ldMiss.asUInt
    dc_lsu_mshr_ok := u_dcache.io.ldMshrDataOk.asUInt
    dc_lsu_mshr_rdata := u_dcache.io.ldMshrRdata.asUInt
    dc_lsu_mshr_robid := u_dcache.io.ldMshrRobid.asUInt
    u_dcache.io.ldPairValid := (dc_ldq_pair_valid).asBool
    u_dcache.io.ldPairWord := dc_ldq_pair_word
    u_dcache.io.ldPairPaddr := dc_ldq_pair_paddr
    dc_lsu_pair_ok := u_dcache.io.ldPairDataOk.asUInt
    dc_lsu_pair_miss := u_dcache.io.ldPairMiss.asUInt
    dc_lsu_pair_rdata := u_dcache.io.ldPairRdata.asUInt
    u_dcache.io.stReq := (sb_dc_wr_req).asBool
    u_dcache.io.stPaddr := sb_dc_wr_paddr
    u_dcache.io.stData := sb_dc_wr_data
    u_dcache.io.stStrb := sb_dc_wr_strb
    u_dcache.io.stSize := sb_dc_wr_size
    u_dcache.io.stUncached := (sb_dc_wr_uncached).asBool
    dc_sb_addr_ok := u_dcache.io.stAddrOk.asUInt
    dc_sb_done := u_dcache.io.stDone.asUInt
    u_dcache.io.fenceI := (rv_fencei_issue).asBool
    dc_l2_rd_req := u_dcache.io.axiRdReq.asUInt
    dc_l2_rd_type := u_dcache.io.axiRdType.asUInt
    dc_l2_rd_addr := u_dcache.io.axiRdAddr.asUInt
    u_dcache.io.axiRdRdy := (l2_dc_rd_rdy).asBool
    u_dcache.io.axiRetValid := (l2_dc_ret_valid).asBool
    u_dcache.io.axiRetLast := (l2_dc_ret_last).asBool
    u_dcache.io.axiRetData := l2_dc_ret_data
    u_dcache.io.axiRetError := l2DataReadError
    dcReadError := u_dcache.io.ldError
    dcMissError := u_dcache.io.ldMshrError
    dc_l2_wr_req := u_dcache.io.axiWrReq.asUInt
    dc_l2_wr_type := u_dcache.io.axiWrType.asUInt
    dc_l2_wr_addr := u_dcache.io.axiWrAddr.asUInt
    dc_l2_wr_strb := u_dcache.io.axiWrStrb.asUInt
    dc_l2_wr_data := u_dcache.io.axiWrData.asUInt
    dc_l2_wr_write_through := u_dcache.io.axiWrWriteThrough.asUInt
    u_dcache.io.axiWrRdy := (l2_dc_wr_rdy).asBool
    dc_full_flush_done := u_dcache.io.fullFlushDone.asUInt

    // PTW borrows the coherent D-cache port only after older requests/stores
    // drain. It retains ownership until any refill is fully quiescent.
    val pageRequestQ = Module(new Queue(UInt(34.W), 1, pipe = false, flow = false))
    pageRequestQ.io.enq <> pageRequest
    val coherentRead = Module(new RRArbiter(UInt(34.W),2))
    coherentRead.io.in(0) <> pageRequestQ.io.deq
    coherentRead.io.in(1).valid := atomic.io.readRequest.valid
    coherentRead.io.in(1).bits := Cat(0.U(2.W),atomic.io.readRequest.bits)
    atomic.io.readRequest.ready := coherentRead.io.in(1).ready
    val walkIsAtomic = RegInit(false.B)
    val walkBusy = RegInit(false.B)
    val walkResponseValid = RegInit(false.B)
    val walkResponseConsumed = RegInit(false.B)
    val walkResponse = Reg(new PageTableReadResponse)
    val canWalk = coherentRead.io.out.valid && !walkBusy && u_dcache.io.quiescent &&
      sb_empty.asBool && !dc_ldq_req.asBool && !rv_fencei_issue.asBool
    val badPageAddress = coherentRead.io.out.bits(33,32).orR || !PhysicalMap.ram(coherentRead.io.out.bits(31,0))
    val walkSelected = walkBusy || canWalk
    coherentRead.io.out.ready := canWalk && (badPageAddress || u_dcache.io.ldAddrOk)
    pageResponse.valid := walkResponseValid && !walkIsAtomic
    pageResponse.bits := walkResponse
    atomic.io.readResponse.valid := walkResponseValid && walkIsAtomic
    atomic.io.readResponse.bits := walkResponse
    when(coherentRead.io.out.fire) {
      walkBusy := true.B
      walkIsAtomic := coherentRead.io.chosen.asBool
      walkResponseConsumed := false.B
      when(badPageAddress) {
        walkResponseValid := true.B
        walkResponse.data := 0.U
        walkResponse.error := true.B
      }
    }
    when(walkBusy && !walkResponseValid && !walkResponseConsumed &&
      (u_dcache.io.ldDataOk || u_dcache.io.ldMshrDataOk)) {
      walkResponseValid := true.B
      walkResponse.data := Mux(u_dcache.io.ldDataOk,u_dcache.io.ldRdata,u_dcache.io.ldMshrRdata)
      walkResponse.error := Mux(u_dcache.io.ldDataOk,u_dcache.io.ldError,u_dcache.io.ldMshrError)
    }
    when(pageResponse.fire || atomic.io.readResponse.fire) { walkResponseValid := false.B; walkResponseConsumed := true.B }
    when(walkBusy && walkResponseConsumed && u_dcache.io.quiescent) {
      walkBusy := false.B
      walkResponseConsumed := false.B
    }
    u_dcache.io.ldReq := Mux(walkSelected,canWalk && !badPageAddress,dc_ldq_req.asBool)
    u_dcache.io.ldVindex := Mux(walkSelected,coherentRead.io.out.bits(11,5),dc_ldq_vindex)
    u_dcache.io.ldPaddr := Mux(walkSelected,coherentRead.io.out.bits(31,0),dc_ldq_paddr)
    u_dcache.io.ldSize := Mux(walkSelected,2.U,dc_ldq_size)
    u_dcache.io.ldOp := Mux(walkSelected,0.U,dc_ldq_load_op)
    u_dcache.io.ldUncached := !walkSelected && dc_ldq_uncached.asBool
    u_dcache.io.ldRobid := Mux(walkSelected,31.U,dc_ldq_robid)
    u_dcache.io.ldPairValid := !walkSelected && dc_ldq_pair_valid.asBool
    u_dcache.io.ldRespReady := walkBusy || lsu_dc_resp_ready.asBool
    // 修复 E（133 潜在走页响应丢失死锁，2026-09-22 诊断定位）：ldCancel 的
    // 走页保护此前用寄存器 walkBusy——但授权拍（coherentRead.out.fire）walkBusy
    // 尚为 0，若该拍恰逢 flush（lsu_dc_cancel=io.flush=1），走页 load 以
    // reqLdKilled=1 出生（Dcache latchLoad 捕获 io.ldCancel），完成后 ldDataOk
    // 被抑制 → walkResponseValid 永不置位 → 被同一 flush 取消的 Sv32 永久困在
    // sWait 排空态（实测：ROB 空、总线静默、walkBusy=1 无响应）。改用组合态
    // walkSelected（授权拍即为 1）关闭该窗口；walkSelected 期间 LSU 请求不可能
    // 驻留 Dcache（canWalk 要求 quiescent 含 !pendValid），屏蔽其 cancel 无副作用。
    u_dcache.io.ldCancel := !walkSelected && lsu_dc_cancel.asBool
    dc_ldq_addr_ok := (u_dcache.io.ldAddrOk && !walkSelected).asUInt
    dc_lsu_data_ok := (u_dcache.io.ldDataOk && !walkBusy).asUInt
    dc_lsu_miss := (u_dcache.io.ldMiss && !walkBusy).asUInt
    dc_lsu_mshr_ok := (u_dcache.io.ldMshrDataOk && !walkBusy).asUInt
    dc_lsu_pair_ok := (u_dcache.io.ldPairDataOk && !walkBusy).asUInt
    dc_lsu_pair_miss := (u_dcache.io.ldPairMiss && !walkBusy).asUInt

    if (!sys.props.get("e91c.synthesis").contains("true")) {
      when(!walkSelected && dc_ldq_req.asBool &&
        PhysicalMemoryAttributes.dataMat(dc_ldq_paddr) === PhysicalMemoryAttributes.MatDevice) {
        assert(dc_ldq_uncached.asBool,
          "device or uncached-alias data must not enter the cached D-cache path")
      }
      when(sb_dc_wr_req.asBool &&
        PhysicalMemoryAttributes.dataMat(sb_dc_wr_paddr) === PhysicalMemoryAttributes.MatDevice) {
        assert(sb_dc_wr_uncached.asBool,
          "committed device or uncached-alias store must remain uncached in StoreBuffer")
      }
    }

  }
  connect_u_dcache()

  // Both larger L1 caches retain page-offset indexing.  Their miss/writeback
  // ports connect directly to the existing independent bridge channels.
  io.instructionReadError := memoryInstructionReadError
  l2DataReadError := memoryReadError

  l2_ic_rd_rdy := mem2_l2_rd_rdy
  l2_ic_ret_valid := mem2_l2_ret_valid
  l2_ic_ret_last := mem2_l2_ret_last
  l2_ic_ret_data := mem2_l2_ret_data
  l2_mem2_rd_req := ic_l2_rd_req
  l2_mem2_rd_type := ic_l2_rd_type
  l2_mem2_rd_addr := ic_l2_rd_addr

  l2_dc_rd_rdy := mem_l2_rd_rdy
  l2_dc_ret_valid := mem_l2_ret_valid
  l2_dc_ret_last := mem_l2_ret_last
  l2_dc_ret_data := mem_l2_ret_data
  l2_dc_wr_rdy := mem_l2_wr_rdy
  l2_mem_rd_req := dc_l2_rd_req
  l2_mem_rd_type := dc_l2_rd_type
  l2_mem_rd_addr := dc_l2_rd_addr
  l2_mem_wr_req := dc_l2_wr_req
  l2_mem_wr_type := dc_l2_wr_type
  l2_mem_wr_addr := dc_l2_wr_addr
  l2_mem_wr_strb := dc_l2_wr_strb
  l2_mem_wr_data := dc_l2_wr_data

  private def connect_u_axi_line_bridge(): Unit = {
    val u_axi_line_bridge = withReset(!(resetn).asBool) { Module(new AxiLineBridge) }
    u_axi_line_bridge.io.rResp := io.readResponseStatus
    memoryReadError := u_axi_line_bridge.io.dcRetError
    memoryInstructionReadError := u_axi_line_bridge.io.icRetError
    u_axi_line_bridge.io.icRdReq := (l2_mem2_rd_req).asBool
    u_axi_line_bridge.io.icRdType := l2_mem2_rd_type
    u_axi_line_bridge.io.icRdAddr := l2_mem2_rd_addr
    mem2_l2_rd_rdy := u_axi_line_bridge.io.icRdRdy.asUInt
    mem2_l2_ret_valid := u_axi_line_bridge.io.icRetValid.asUInt
    mem2_l2_ret_last := u_axi_line_bridge.io.icRetLast.asUInt
    mem2_l2_ret_data := u_axi_line_bridge.io.icRetData.asUInt
    u_axi_line_bridge.io.dcRdReq := (l2_mem_rd_req).asBool
    u_axi_line_bridge.io.dcRdType := l2_mem_rd_type
    u_axi_line_bridge.io.dcRdAddr := l2_mem_rd_addr
    mem_l2_rd_rdy := u_axi_line_bridge.io.dcRdRdy.asUInt
    mem_l2_ret_valid := u_axi_line_bridge.io.dcRetValid.asUInt
    mem_l2_ret_last := u_axi_line_bridge.io.dcRetLast.asUInt
    mem_l2_ret_data := u_axi_line_bridge.io.dcRetData.asUInt
    u_axi_line_bridge.io.dcWrReq := (l2_mem_wr_req).asBool
    u_axi_line_bridge.io.dcWrType := l2_mem_wr_type
    u_axi_line_bridge.io.dcWrAddr := l2_mem_wr_addr
    u_axi_line_bridge.io.dcWrStrb := l2_mem_wr_strb
    u_axi_line_bridge.io.dcWrData := l2_mem_wr_data
    mem_l2_wr_rdy := u_axi_line_bridge.io.dcWrRdy.asUInt
    axi_awvalid_line := u_axi_line_bridge.io.awValid.asUInt
    axi_awaddr_line := u_axi_line_bridge.io.awAddr.asUInt
    axi_awlen_line := u_axi_line_bridge.io.awLen.asUInt
    axi_awsize_line := u_axi_line_bridge.io.awSize.asUInt
    u_axi_line_bridge.io.awReady := (awready).asBool
    axi_wvalid_line := u_axi_line_bridge.io.wValid.asUInt
    axi_wdata_line := u_axi_line_bridge.io.wData.asUInt
    axi_wstrb_line := u_axi_line_bridge.io.wStrb.asUInt
    axi_wlast_line := u_axi_line_bridge.io.wLast.asUInt
    u_axi_line_bridge.io.wReady := (wready).asBool
    u_axi_line_bridge.io.bValid := (bvalid).asBool
    axi_bready_line := u_axi_line_bridge.io.bReady.asUInt
    axi_arvalid_line := u_axi_line_bridge.io.arValid.asUInt
    axi_arid_line := u_axi_line_bridge.io.arId.asUInt
    axi_araddr_line := u_axi_line_bridge.io.arAddr.asUInt
    axi_arlen_line := u_axi_line_bridge.io.arLen.asUInt
    axi_arsize_line := u_axi_line_bridge.io.arSize.asUInt
    u_axi_line_bridge.io.arReady := (arready).asBool
    u_axi_line_bridge.io.rValid := (rvalid).asBool
    u_axi_line_bridge.io.rId := rid
    u_axi_line_bridge.io.rData := rdata
    u_axi_line_bridge.io.rLast := (rlast).asBool
    axi_rready_line := u_axi_line_bridge.io.rReady.asUInt
  }
  connect_u_axi_line_bridge()
}
