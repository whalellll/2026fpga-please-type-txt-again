package e91c.core
import chisel3._
import chisel3.util._
import e91c.frontend._
import e91c.config.Params._
import e91c.mem.PhysicalMemoryAttributes
// Preserve assertion source-line identities after removing six unused imports.





class CoreFrontendIO extends Bundle {
    val instructionFaults = Input(UInt(e91c.config.Params.EXCP_NUM.W))
    val instructionReadError = Input(Bool())
    val instructionAccept = Output(Bool())
    val instructionCancel = Output(Bool())
    val cmt_ftq_br_type = Input(UInt(2.W))
    val cmt_ftq_id = Input(UInt(4.W))
    val cmt_ftq_is_branch = Input(UInt(1.W))
    val cmt_ftq_mispred = Input(UInt(1.W))
    val cmt_ftq_pc = Input(UInt(32.W))
    val cmt_ftq_query_id = Input(UInt(4.W))
    val cmt_ftq_release = Input(UInt(2.W))
    val cmt_ftq_taken = Input(UInt(1.W))
    val cmt_ftq_target = Input(UInt(32.W))
    val cmt_ftq_valid = Input(UInt(1.W))
    val cmt_ras_call = Input(UInt(1.W))
    val cmt_ras_ret = Input(UInt(1.W))
    val cmt_ras_retaddr = Input(UInt(32.W))
    val early_redirect_valid = Input(UInt(1.W))
    val early_redirect_pc = Input(UInt(32.W))
    val early_redirect_ftq_id = Input(UInt(FTQ_W.W))
    val early_redirect_taken = Input(UInt(1.W))
    val flush = Input(UInt(1.W))
    val flush_pc = Input(UInt(32.W))
    val ftq_cmt_blk_target = Output(UInt(32.W))
    val ftq_cmt_blk_target_next = Output(UInt(32.W))
    val ib_pop0_excp = Output(UInt(e91c.config.Params.EXCP_NUM.W))
    val ib_pop0_ftq_id = Output(UInt(4.W))
    val ib_pop0_inst = Output(UInt(32.W))
    val ib_pop0_is_last = Output(UInt(1.W))
    val ib_pop0_pc = Output(UInt(32.W))
    val ib_pop0_pred_taken = Output(UInt(1.W))
    val ib_pop0_ready = Input(UInt(1.W))
    val ib_pop0_valid = Output(UInt(1.W))
    val ib_pop1_excp = Output(UInt(e91c.config.Params.EXCP_NUM.W))
    val ib_pop1_ftq_id = Output(UInt(4.W))
    val ib_pop1_inst = Output(UInt(32.W))
    val ib_pop1_is_last = Output(UInt(1.W))
    val ib_pop1_pc = Output(UInt(32.W))
    val ib_pop1_pred_taken = Output(UInt(1.W))
    val ib_pop1_ready = Input(UInt(1.W))
    val ib_pop1_valid = Output(UInt(1.W))
    val ic_ifu_addr_ok = Input(UInt(1.W))
    val ic_ifu_addr_ok_raw = Output(UInt(1.W))
    val ic_ifu_data_ok = Input(UInt(1.W))
    val ic_ifu_data_ok_raw = Output(UInt(1.W))
    val ic_invalidate = Input(UInt(1.W))
    val ic_l2_rd_addr = Output(UInt(32.W))
    val ic_l2_rd_req = Output(UInt(1.W))
    val ic_l2_rd_type = Output(UInt(3.W))
    val ifu_pma_req = Output(UInt(1.W))
    val ifu_pma_vaddr = Output(UInt(32.W))
    val l2_ic_rd_rdy = Input(UInt(1.W))
    val l2_ic_ret_data = Input(UInt(128.W))
    val l2_ic_ret_last = Input(UInt(1.W))
    val l2_ic_ret_valid = Input(UInt(1.W))
    val pma_i_direct_excp = Input(UInt(1.W))
    val pma_i_direct_mat = Input(UInt(2.W))
    val pma_i_direct_ok = Input(UInt(1.W))
    val pma_i_direct_paddr = Input(UInt(32.W))
    val pma_i_inst_addr_misaligned = Input(UInt(1.W))
    val pma_i_mat = Input(UInt(2.W))
    val pma_i_paddr = Input(UInt(32.W))
    val pma_i_ready = Input(UInt(1.W))
    val resetn = Input(UInt(1.W))
    val resetVector = Input(UInt(32.W))
    val rv_fencei_hold = Input(UInt(1.W))
    val rv_fencei_issue = Input(UInt(1.W))
}

class CoreFrontend(val cacheableInstructionsOnly: Boolean = false) extends Module {
  val io = IO(new CoreFrontendIO)
  import e91c.config.BrType

  // PF owns the only speculative next-PC register. S2 never writes this PC.
  val pfPc = RegInit(io.resetVector)
  val epoch = RegInit(0.U(32.W))
  val nextGroup = RegInit(0.U(32.W))
  val flush = io.flush.asBool
  val earlyRedirect = io.early_redirect_valid.asBool
  val pdRepair = Wire(Bool())
  val pfAdvance = Wire(Bool())
  val fcToPd = Wire(Bool())
  val fcTransferCandidate = Wire(Bool())
  val pdAccept = Wire(Bool())
  val fallback = Module(new FallbackBtb(FALLBACK_SETS, FALLBACK_HASH))
  val ftb = Module(new Ftb)
  val tage = Module(new Tage)
  val ras = Module(new Ras)
  val cache = Module(new Icache(cacheableOnly = cacheableInstructionsOnly))
  val buffer = Module(new InstBuffer)

  // FTQ is allocated only for accepted PD groups. Killed FC groups cannot
  // alias a recycled four-bit architectural FTQ id.
  val ftqAlloc = RegInit(0.U(FTQ_W.W))
  val ftqCommit = RegInit(0.U(FTQ_W.W))
  val ftqPc = Mem(FTQ_SIZE,UInt(32.W))
  val ftqTarget = Mem(FTQ_SIZE,UInt(32.W))
  val ftqMeta = Mem(FTQ_SIZE,UInt(BPU_META_W.W))
  val ftqFull = ftqAlloc+1.U === ftqCommit
  val queryId = io.cmt_ftq_query_id
  io.ftq_cmt_blk_target := ftqTarget(queryId)
  io.ftq_cmt_blk_target_next := ftqTarget((queryId+1.U)(FTQ_W-1,0))
  when(flush) { ftqAlloc:=0.U; ftqCommit:=0.U }.otherwise {
    when(earlyRedirect) { ftqAlloc:=(io.early_redirect_ftq_id+1.U)(FTQ_W-1,0) }
      .elsewhen(pdAccept) { ftqAlloc:=ftqAlloc+1.U }
    when(io.cmt_ftq_release.orR) { ftqCommit:=ftqCommit+io.cmt_ftq_release }
  }

  // FC owns an accepted PF request. A hit response may transfer directly to
  // PD while PF replaces FC on the same edge; blocked responses are retained.
  val fcValid = RegInit(false.B)
  val fcPc = Reg(UInt(32.W)); val fcEpoch = Reg(UInt(32.W)); val fcGroup = Reg(UInt(32.W))
  val fcP0Length = Reg(UInt(BLK_LEN_W.W)); val fcP0Taken = Reg(Bool()); val fcP0Target = Reg(UInt(32.W))
  val fcP0Cond = Reg(Bool())
  val fcP0Next = Reg(UInt(32.W))
  val fcPredictionReady = RegInit(false.B)
  val fcS2Length = Reg(UInt(BLK_LEN_W.W)); val fcS2Taken = Reg(Bool()); val fcS2Target = Reg(UInt(32.W))
  val fcS2Cond = Reg(Bool())
  val fcMeta = Reg(UInt(BPU_META_W.W))
  val fcTranslated = RegInit(false.B); val fcPaddr = Reg(UInt(32.W))
  val fcFaults = Reg(UInt(EXCP_NUM.W))
  val fcCacheSent = RegInit(false.B); val fcDataReady = RegInit(false.B)
  val fcLine = Reg(UInt(128.W))

  // PD is a real held register boundary, independent of the cache FSM.
  val pdValid = RegInit(false.B)
  val pdPc = Reg(UInt(32.W)); val pdEpoch = Reg(UInt(32.W)); val pdGroup = Reg(UInt(32.W))
  val pdPcNextLineHi = Reg(UInt(27.W))
  val pdLength = Reg(UInt(BLK_LEN_W.W)); val pdTaken = Reg(Bool()); val pdTarget = Reg(UInt(32.W))
  val pdHistCond = Reg(Bool()); val pdHistTaken = Reg(Bool())
  val pdP0Next = Reg(UInt(32.W)); val pdMeta = Reg(UInt(BPU_META_W.W))
  val pdFaults = Reg(UInt(EXCP_NUM.W))
  // Extract instruction boundaries on the FC-to-PD edge.  The late PD
  // redirect then starts from registered instructions instead of walking
  // four variable-length instructions from the raw line register.
  val pdInsts = Reg(Vec(FETCH_WIDTH, UInt(32.W)))

  val baseLength = Mux(8.U-pfPc(4,2) > FETCH_WIDTH.U,FETCH_WIDTH.U,8.U-pfPc(4,2))
  fallback.io.queryValid := pfAdvance; fallback.io.queryPc := pfPc
  val useFallback = fallback.io.hit && fallback.io.length =/= 0.U && fallback.io.length <= baseLength
  val p0Cond = useFallback && fallback.io.brType===BrType.COND.U
  val p0Length = Mux(useFallback, fallback.io.length, baseLength)
  val p0Ret = useFallback && fallback.io.brType===BrType.RET.U
  val p0Taken = useFallback && ((fallback.io.brType===BrType.COND.U && fallback.io.taken) ||
    ((fallback.io.brType===BrType.UNCOND.U || fallback.io.brType===BrType.CALL.U) && fallback.io.staticDirect) ||
    (fallback.io.brType===BrType.RET.U && !ras.io.empty))
  val p0Target = Mux(p0Ret && !ras.io.empty, ras.io.topAddr, fallback.io.target)
  val p0Next = Mux(p0Taken,p0Target,pfPc+(p0Length<<2))
  ftb.io.queryValid := pfAdvance; ftb.io.queryPc := pfPc
  tage.io.queryValid := pfAdvance; tage.io.queryPc := pfPc(21,2)
  val queryValid = RegNext(pfAdvance,false.B)
  val queryEpoch = RegEnable(epoch,pfAdvance); val queryGroup = RegEnable(nextGroup,pfAdvance)
  // The predictor response is exactly one cycle after PF allocation. FC is
  // either that allocation or invalidated by the same edge's redirect.
  val s2Owned = fcValid && queryValid && tage.io.respValid
  val s2MaxLength = Mux(8.U-fcPc(4,2)>FETCH_WIDTH.U,FETCH_WIDTH.U,8.U-fcPc(4,2))
  val s2RawLength = (ftb.io.fallThrough(4,2)-fcPc(4,2))(2,0)
  val s2Hit = ftb.io.respValid && ftb.io.hit && s2RawLength=/=0.U && s2RawLength<=s2MaxLength
  val s2Taken = Mux(ftb.io.brType===BrType.COND.U,tage.io.taken,true.B)
  val s2Target = ftb.io.jumpTarget
  val responseLength = Mux(s2Hit,s2RawLength,fcP0Length)
  val responseTaken = Mux(s2Hit,s2Taken,fcP0Taken)
  val responseTarget = Mux(s2Hit,s2Target,fcP0Target)
  val responseCond = Mux(s2Hit,ftb.io.brType===BrType.COND.U,fcP0Cond)
  val responseMeta = Cat(tage.io.taken,tage.io.meta(62,59),0.U(FTQ_W.W),tage.io.meta(54,43),
    ftb.io.hitWay,ftb.io.hit,ftb.io.respValid,tage.io.respValid,tage.io.meta(37,0))
  when(s2Owned) {
    fcPredictionReady := true.B
    fcS2Length := responseLength
    fcS2Taken := responseTaken
    fcS2Target := responseTarget
    fcS2Cond := responseCond
    fcMeta := responseMeta
  }

  // Translation is requested from the registered PF PC, not after allocating
  // FC. A translated response remains held until the cache/fault slot accepts.
  // Do not feed the late PD repair decision back through PMA request admission.
  // A direct-path request that is accepted in the repair cycle is tagged killed
  // below and drained under its original cache owner; the repaired PC wins the
  // sequential PF update.  Translated requests are suppressed by PmaMmu while
  // instructionCancel is asserted, so a cancelled walk cannot acquire an owner.
  val pfCanRequest = (!fcValid || fcTransferCandidate) && !ftqFull && !flush && !earlyRedirect &&
    !io.rv_fencei_hold.asBool && !io.ic_invalidate.asBool
  io.ifu_pma_req := pfCanRequest.asUInt
  io.ifu_pma_vaddr := pfPc
  val translationReady = pfCanRequest && io.pma_i_ready.asBool
  io.instructionAccept := pfAdvance
  // Redirect/repair state (epoch, PF PC, FC/cache owner kill) changes on this
  // edge. Cancel an unfinished Sv32 instruction owner on the following cycle
  // so the late predecode decision cannot feed back through PmaMmu.iReady into
  // the next-PC adder in the same combinational cone.
  val instructionCancel = RegNext(pdRepair || earlyRedirect, false.B)
  io.instructionCancel := instructionCancel

  // One refill owner is retained through cancellation and drained. Physical
  // address equality alone is never sufficient to authorize a late response.
  val cacheOutstanding = RegInit(false.B)
  val cacheKilled = RegInit(false.B)
  val cacheEpoch = Reg(UInt(32.W)); val cacheGroup = Reg(UInt(32.W))
  val cacheResponse = io.ic_ifu_data_ok.asBool
  // There is one non-cancelable cache owner. FC cannot advance before that
  // owner's response; redirects mark it killed until it drains. A replacement
  // is installed only on the edge consuming the previous response.
  val cacheResponseOwned = cacheResponse && cacheOutstanding && !cacheKilled && fcValid
  // The cache supports response/next-request replacement on hits and refill
  // completion. Old response identity is checked against pre-edge registers.
  cache.io.ifuReq := translationReady && !io.instructionFaults.orR &&
    (!cacheOutstanding || cacheResponse)
  cache.io.ifuVindex := pfPc(11,5); cache.io.ifuPaddr := io.pma_i_paddr
  // The integrated physical map permits instruction execution only from RAM.
  // MMIO gets an access fault before any cache request; assert that contract.
  cache.io.ifuUncached := !cacheableInstructionsOnly.B && io.pma_i_mat =/= PhysicalMemoryAttributes.MatCacheable
  require(L1_INDEX_W + CACHE_LINE_W <= 12, "VIPT index must fit a Sv32 page offset")
  cache.io.invalidate := io.ic_invalidate.asBool
  io.ic_ifu_addr_ok_raw := cache.io.ifuAddrOk.asUInt
  io.ic_ifu_data_ok_raw := cache.io.ifuDataOk.asUInt
  io.ic_l2_rd_req:=cache.io.axiRdReq.asUInt; io.ic_l2_rd_type:=cache.io.axiRdType; io.ic_l2_rd_addr:=cache.io.axiRdAddr
  cache.io.axiRdRdy:=io.l2_ic_rd_rdy.asBool; cache.io.axiRetValid:=io.l2_ic_ret_valid.asBool
  cache.io.axiRetLast:=io.l2_ic_ret_last.asBool; cache.io.axiRetData:=io.l2_ic_ret_data
  cache.io.axiRetError:=io.instructionReadError
  val cacheFire = cache.io.ifuReq && io.ic_ifu_addr_ok.asBool
  // Extract the owned fetch window before holding it. FC PC still belongs to
  // the returning owner even when PF installs a replacement on this edge.
  val responseWindow = (cache.io.ifuRline >> (fcPc(4,2) << 5))(127,0)
  when(cacheResponse) {
    cacheOutstanding:=false.B
    when(cacheResponseOwned) {
      fcLine:=responseWindow; fcDataReady:=true.B
      when(cache.io.ifuError) { fcFaults:=64.U }
    }
  }
  // Replacement wins over clearing the consumed old owner.
  when(cacheFire) {
    cacheOutstanding:=true.B; cacheKilled:=false.B; cacheEpoch:=epoch; cacheGroup:=nextGroup
  }
  when(flush || earlyRedirect || pdRepair || io.ic_invalidate.asBool) {
    when(cacheOutstanding || cacheFire) { cacheKilled:=true.B }
  }

  // Final predecode selects the actual earliest branch. JAL targets and RAS
  // returns override stale target predictions only at the PD acceptance point.
  // Every instruction occupies one word. Register four constant-indexed
  // words on FC-to-PD, retaining the existing fetch/accept pipeline boundaries.
  val incomingLine = Mux(cacheResponseOwned,responseWindow,fcLine)
  val incomingInsts = VecInit((0 until FETCH_WIDTH).map(i => incomingLine(32*i+31,32*i)))
  val remaining = 8.U(4.W) - pdPc(4,2)
  val available = Mux(remaining > FETCH_WIDTH.U,FETCH_WIDTH.U,remaining)
  val slotValid = Wire(Vec(FETCH_WIDTH, Bool()))
  val pcs = Wire(Vec(FETCH_WIDTH, UInt(32.W)))
  val insts = pdInsts
  val jal = Wire(Vec(FETCH_WIDTH, Bool()))
  val cond = Wire(Vec(FETCH_WIDTH, Bool()))
  val jalr = Wire(Vec(FETCH_WIDTH, Bool()))
  for (i <- 0 until FETCH_WIDTH) {
    slotValid(i) := i.U < available && i.U < pdLength
    // Valid groups never cross a cache line. Retain the original fault PC's
    // bit 1 for precise instruction-address exceptions, without a wide adder.
    pcs(i) := Cat(pdPc(31,5),(pdPc(4,2) + i.U)(2,0),pdPc(1),0.U(1.W))
    jal(i) := insts(i)(6,0) === "h6f".U
    cond(i) := insts(i)(6,0) === "h63".U && (insts(i)(14) || !insts(i)(13))
    jalr(i) := insts(i)(6,0) === "h67".U && insts(i)(14,12) === 0.U
  }
  // PDS-safe first-branch selection: no variable-indexed vector read feeds
  // predecode or redirect control. Scala elaborates the lanes to fixed wires.
  require(FETCH_WIDTH == 4)
  val branch0 = slotValid(0) && (jal(0) || cond(0) || jalr(0))
  val branch1 = slotValid(1) && (jal(1) || cond(1) || jalr(1))
  val branch2 = slotValid(2) && (jal(2) || cond(2) || jalr(2))
  val branch3 = slotValid(3) && (jal(3) || cond(3) || jalr(3))
  val found = (branch0 || branch1 || branch2 || branch3) && !pdFaults.orR
  val index = Mux(branch0,0.U(2.W),Mux(branch1,1.U(2.W),Mux(branch2,2.U(2.W),Mux(branch3,3.U(2.W),0.U(2.W)))))
  val select1 = !branch0 && branch1
  val select2 = !branch0 && !branch1 && branch2
  val select3 = !branch0 && !branch1 && !branch2 && branch3
  val selectedInst = MuxCase(insts(0),Seq(select1 -> insts(1),select2 -> insts(2),select3 -> insts(3)))
  val selectedPc = MuxCase(pcs(0),Seq(select1 -> pcs(1),select2 -> pcs(2),select3 -> pcs(3)))
  val selectedJal = MuxCase(jal(0),Seq(select1 -> jal(1),select2 -> jal(2),select3 -> jal(3)))
  val selectedCond = MuxCase(cond(0),Seq(select1 -> cond(1),select2 -> cond(2),select3 -> cond(3)))
  val selectedJalr = MuxCase(jalr(0),Seq(select1 -> jalr(1),select2 -> jalr(2),select3 -> jalr(3)))
  val isReturn = found && selectedJalr && selectedInst(11,7) === 0.U &&
    (selectedInst(19,15) === 1.U || selectedInst(19,15) === 5.U)
  val isCall = found && !isReturn && (selectedJal || selectedJalr) &&
    (selectedInst(11,7) === 1.U || selectedInst(11,7) === 5.U)
  val actualJumpOffset = Cat(Fill(12,selectedInst(31)),selectedInst(19,12),
    selectedInst(20),selectedInst(30,21),0.U(1.W))
  val directTarget = selectedPc + actualJumpOffset
  val condTarget = selectedPc + Cat(Fill(20,selectedInst(31)),selectedInst(7),
    selectedInst(30,25),selectedInst(11,8),0.U(1.W))
  val validCount = PopCount(slotValid)
  val finalLength = Mux(pdFaults.orR,1.U,Mux(found,index+&1.U,validCount))
  val descriptorMatches = pdLength === index+&1.U
  val finalTaken = found && (selectedJal || (isReturn && !ras.io.empty) || (descriptorMatches && pdTaken))
  val finalTarget = Mux(found && selectedJal,directTarget,
    Mux(isReturn && !ras.io.empty,ras.io.topAddr,pdTarget))
  val seqLowSum = (pdPc(4,2) +& finalLength)(3,0)
  val seqNext = Cat(Mux(seqLowSum(3),pdPcNextLineHi,pdPc(31,5)),
    seqLowSum(2,0),0.U(2.W))
  val finalNext = Mux(finalTaken,finalTarget,seqNext)
  val predictedSeqDelta = pdP0Next - pdPc
  val seqMismatch = predictedSeqDelta(31,5).orR || predictedSeqDelta(1,0).orR ||
    predictedSeqDelta(4,2) =/= finalLength
  // Subtract the selected word offset before comparing a direct JAL target.
  val expectedJumpLow = (predictedSeqDelta(3,2) - index)(1,0)
  val jumpBorrow = predictedSeqDelta(3,2) < index
  val expectedJumpOffset = Cat(Mux(jumpBorrow,predictedSeqDelta(31,4)-1.U,
    predictedSeqDelta(31,4)),expectedJumpLow,predictedSeqDelta(1,0))
  val targetMismatch = Mux(selectedJal,actualJumpOffset =/= expectedJumpOffset,
    Mux(isReturn && !ras.io.empty,ras.io.topAddr =/= pdP0Next,pdTarget =/= pdP0Next))
  val branchTarget = Mux(selectedJal,directTarget,Mux(selectedCond,condTarget,finalTarget))
  val branchType = Mux(isReturn,BrType.RET.U,Mux(isCall,BrType.CALL.U,Mux(selectedJal||selectedJalr,BrType.UNCOND.U,BrType.COND.U)))
  val actualCond = found && selectedCond
  val histDescriptorDiff = (pdHistCond =/= actualCond) ||
    (pdHistCond && actualCond && pdHistTaken =/= finalTaken)
  pdAccept := pdValid && (slotValid(0) || pdFaults.orR) &&
    buffer.io.canPush && !ftqFull && !flush && !earlyRedirect
  pdRepair := pdAccept && !pdFaults.orR &&
    (Mux(finalTaken,targetMismatch,seqMismatch) || histDescriptorDiff)
  val settledHistCond = Mux(s2Owned,responseCond,fcS2Cond)
  val settledHistTaken = Mux(s2Owned,responseTaken,fcS2Taken)
  fcTransferCandidate := fcValid && fcTranslated && (fcPredictionReady || s2Owned) &&
    (fcDataReady || cacheResponseOwned) &&
    (!pdValid || pdAccept) && !earlyRedirect && !flush
  fcToPd := fcTransferCandidate && !pdRepair
  pfAdvance := translationReady && (io.instructionFaults.orR || cacheFire)

  buffer.io.flush := flush || earlyRedirect
  for (i <- 0 until FETCH_WIDTH) {
    buffer.io.pushValid(i):=pdAccept && i.U<finalLength
    buffer.io.pushPc(i):=pcs(i); buffer.io.pushInst(i):=Mux(pdFaults.orR,0.U,insts(i))
    buffer.io.pushPredTaken(i):=finalTaken && i.U===index
    buffer.io.pushIsLast(i):=i.U===finalLength-1.U
    buffer.io.pushFtqId(i):=ftqAlloc; buffer.io.pushExcp(i):=pdFaults
  }
  when(pdAccept) {
    ftqPc(ftqAlloc):=pdPc; ftqTarget(ftqAlloc):=finalTarget
    ftqMeta(ftqAlloc):=(pdMeta & ~("hf".U(64.W)<<55)) | (ftqAlloc<<55)
  }
  when(fcToPd) {
    pdValid:=true.B; pdPc:=fcPc
    pdPcNextLineHi := fcPc(31,5) + 1.U
    pdEpoch:=fcEpoch; pdGroup:=fcGroup
    pdLength:=Mux(s2Owned,responseLength,fcS2Length)
    pdTaken:=Mux(s2Owned,responseTaken,fcS2Taken)
    pdTarget:=Mux(s2Owned,responseTarget,fcS2Target)
    pdHistCond:=settledHistCond; pdHistTaken:=settledHistTaken
    pdMeta:=Mux(s2Owned,responseMeta,fcMeta)
    pdP0Next:=fcP0Next
    pdFaults:=Mux(cacheResponseOwned && cache.io.ifuError,64.U,fcFaults)
    pdInsts := incomingInsts
  }.elsewhen(pdAccept) { pdValid:=false.B }
  when(pfAdvance) {
    fcValid:=true.B; fcPc:=pfPc; fcEpoch:=epoch; fcGroup:=nextGroup
    fcP0Length:=p0Length; fcP0Taken:=p0Taken; fcP0Target:=p0Target; fcP0Next:=p0Next
    fcP0Cond:=p0Cond
    fcPredictionReady:=false.B; fcTranslated:=true.B; fcCacheSent:=cacheFire
    fcPaddr:=io.pma_i_paddr; fcFaults:=io.instructionFaults
    fcDataReady:=io.instructionFaults.orR
    when(io.instructionFaults.orR) { fcLine:=0.U }
    nextGroup:=nextGroup+1.U; pfPc:=p0Next
  }.elsewhen(fcToPd) { fcValid:=false.B }
  when(pdRepair) {
    epoch:=epoch+1.U; pfPc:=finalNext; fcValid:=false.B
  }
  when(earlyRedirect) {
    epoch:=epoch+1.U; pfPc:=io.early_redirect_pc; fcValid:=false.B; pdValid:=false.B
  }
  when(flush) {
    epoch:=epoch+1.U; pfPc:=io.flush_pc; fcValid:=false.B; pdValid:=false.B
  }

  if (!sys.props.get("e91c.synthesis").contains("true")) {
    // Keep the former unbounded identity checks as an independent simulation
    // reference. They have no functional consumers in production, so the
    // epoch/group counters and their register copies disappear from RTL.
    when(s2Owned) {
      assert(queryEpoch === fcEpoch && queryGroup === fcGroup,
        "single-cycle predictor ownership differs from reference identity")
    }
    when(cacheResponseOwned) {
      assert(cacheEpoch === fcEpoch && cacheGroup === fcGroup,
        "single-outstanding cache ownership differs from reference identity")
    }
    when(pdAccept) { assert(pdEpoch === epoch, "PD valid survived a redirect") }
    when(cacheFire) {
      assert(pfAdvance && !flush)
      assert(!cacheOutstanding || cacheResponse, "new fetch overwrote a live cache owner")
      assert(cache.io.ifuUncached ===
        (io.pma_i_mat =/= PhysicalMemoryAttributes.MatCacheable),
        "I-cache routing must use translated PMA MAT")
    }
    when(cacheResponseOwned) { assert(!fcDataReady, "duplicate response for one fetch group") }
    // Probe-only comparison against the original register descriptor storage.
  if (!sys.props.get("e91c.synthesis").contains("true")) {
    val refPc = Reg(Vec(FTQ_SIZE, UInt(32.W)))
    val refTarget = Reg(Vec(FTQ_SIZE, UInt(32.W)))
    val refMeta = Reg(Vec(FTQ_SIZE, UInt(BPU_META_W.W)))
    val refSeen = RegInit(VecInit(Seq.fill(FTQ_SIZE)(false.B)))
    when(pdAccept) {
      refPc(ftqAlloc) := pdPc
      refTarget(ftqAlloc) := finalTarget
      refMeta(ftqAlloc) := (pdMeta & ~("hf".U(64.W)<<55)) | (ftqAlloc<<55)
      refSeen(ftqAlloc) := true.B
    }
    for (id <- Seq(queryId, (queryId+1.U)(FTQ_W-1,0), io.cmt_ftq_id)) {
      when(refSeen(id)) {
        assert(ftqPc(id) === refPc(id) && ftqTarget(id) === refTarget(id) && ftqMeta(id) === refMeta(id),
          "FTQ descriptor storage mismatch")
      }
    }
  }
  when(fcToPd) { assert(fcEpoch===epoch, "stale FC reached PD") }
    when(s2Owned) { assert(!fcPredictionReady, "duplicate predictor response") }
    when(pdRepair) {
      assert(!fcToPd, "a repaired PD group must not accept the stale FC group")
      when(pfAdvance) {
        assert(cacheFire || io.instructionFaults.orR,
          "repair-cycle PF advance must be an accepted cache request or precise fault")
      }
    }
    when(earlyRedirect || flush) { assert(!pfAdvance && !fcToPd) }
  }

  // RAS advances on final PD decode. TAGE history advances when the preceding
  // FC prediction settles so the next PF query receives that outcome in the
  // same cycle. PD repairs restore the pre-group checkpoint and append truth.
  ras.io.flush:=flush; ras.io.specPush:=pdAccept && isCall; ras.io.specPop:=pdAccept && isReturn
  ras.io.specPushAddr:=selectedPc+4.U
  ras.io.cpSave:=pdAccept; ras.io.cpId:=ftqAlloc; ras.io.cpQueryId:=0.U
  ras.io.restore:=earlyRedirect; ras.io.restoreId:=io.early_redirect_ftq_id
  ras.io.restorePush:=false.B; ras.io.restorePop:=false.B; ras.io.restorePushAddr:=0.U
  ras.io.cmtPush:=io.cmt_ras_call.asBool; ras.io.cmtPop:=io.cmt_ras_ret.asBool; ras.io.cmtPushAddr:=io.cmt_ras_retaddr
  tage.io.flush:=flush
  val fcTransferFault = fcFaults.orR || (cacheResponseOwned && cache.io.ifuError)
  // Write the checkpoint for the prospective PD slot as soon as FC is ready.
  // Repeated writes while PD stalls are safe: this slot has not been allocated
  // to an instruction group, and the accepted transfer rewrites it. The
  // address and enable therefore avoid late PD acceptance/repair logic.
  val histCpAlloc = (ftqAlloc + pdValid.asUInt)(FTQ_W-1,0)
  val fcCheckpointReady = fcValid && fcTranslated && (fcPredictionReady || s2Owned) &&
    (fcDataReady || cacheResponseOwned) && !ftqFull && !earlyRedirect && !flush
  tage.io.histCpSave:=fcCheckpointReady && !fcTransferFault; tage.io.histCpId:=histCpAlloc
  tage.io.histRestore:=pdRepair || earlyRedirect
  tage.io.histRestoreId:=Mux(earlyRedirect,io.early_redirect_ftq_id,ftqAlloc)
  tage.io.histRestoreAppend:=Mux(earlyRedirect,true.B,actualCond)
  tage.io.histRestoreTaken:=Mux(earlyRedirect,io.early_redirect_taken.asBool,finalTaken)
  // A repair makes the concurrent PF/predictor query stale, so its speculative
  // query history need not wait for the late repair decision.  Sequential
  // specGhr state is still restored by histRestore, whose priority in Tage is
  // above histUpdateValid; only the killed query address uses this candidate.
  tage.io.histUpdateValid:=fcTransferCandidate && !fcTransferFault && settledHistCond
  tage.io.histUpdateTaken:=settledHistTaken
  tage.io.cmtHistValid:=io.cmt_ftq_valid.asBool && io.cmt_ftq_is_branch.asBool && io.cmt_ftq_br_type===BrType.COND.U
  tage.io.cmtHistTaken:=io.cmt_ftq_taken.asBool

  // Commit training survives the simultaneous recovery flush.
  val trainValid = RegNext(io.cmt_ftq_valid.asBool && io.cmt_ftq_is_branch.asBool,false.B)
  val trainPc = RegNext(ftqPc(io.cmt_ftq_id)); val trainTaken = RegNext(io.cmt_ftq_taken.asBool)
  val trainTarget = RegNext(io.cmt_ftq_target); val trainType = RegNext(io.cmt_ftq_br_type)
  val trainLength = RegNext((io.cmt_ftq_pc(4,2)+1.U-ftqPc(io.cmt_ftq_id)(4,2))(2,0))
  val trainMeta = RegNext(ftqMeta(io.cmt_ftq_id)); val trainMispred = RegNext(io.cmt_ftq_mispred.asBool)
  tage.io.trainValid:=trainValid && trainType===BrType.COND.U; tage.io.trainPc:=trainPc(21,2)
  tage.io.trainTaken:=trainTaken; tage.io.trainMispred:=trainMispred; tage.io.trainMeta:=trainMeta
  val earlyTrain = pdAccept && found && !trainValid
  val updateValid = trainValid || earlyTrain
  val updatePc = Mux(trainValid,trainPc,pdPc); val updateTarget = Mux(trainValid,trainTarget,branchTarget)
  val updateTaken = Mux(trainValid,trainTaken,finalTaken); val updateType = Mux(trainValid,trainType,branchType)
  val updateLength = Mux(trainValid,trainLength,finalLength)
  // PD predecode and commit training form one update command per cycle.  The
  // predictor memories consume a registered command so their concurrent P0
  // read ports cannot acquire a combinational path from PD instructions.
  val predictorUpdateValid = RegNext(updateValid, false.B)
  val predictorUpdatePc = RegEnable(updatePc, updateValid)
  val predictorUpdateTaken = RegEnable(updateTaken, updateValid)
  val predictorUpdateTarget = RegEnable(updateTarget, updateValid)
  val predictorUpdateType = RegEnable(updateType, updateValid)
  val predictorUpdateLength = RegEnable(updateLength, updateValid)
  val predictorUpdateEarly = RegEnable(earlyTrain, updateValid)
  fallback.io.updValid:=predictorUpdateValid; fallback.io.updBlockPc:=predictorUpdatePc
  fallback.io.updTaken:=predictorUpdateTaken; fallback.io.updTarget:=predictorUpdateTarget
  fallback.io.updLength:=predictorUpdateLength
  fallback.io.updBrType:=predictorUpdateType; fallback.io.updEarly:=predictorUpdateEarly
  ftb.io.updateValid:=predictorUpdateValid; ftb.io.updateBlockPc:=predictorUpdatePc(31,2)
  ftb.io.updateJumpTarget:=predictorUpdateTarget
  ftb.io.updateFallThrough:=predictorUpdatePc(4,2)+predictorUpdateLength
  ftb.io.updateBrType:=predictorUpdateType
  io.ib_pop0_valid := buffer.io.popValid(0).asUInt
  io.ib_pop0_pc := buffer.io.popPc(0).asUInt
  io.ib_pop0_inst := buffer.io.popInst(0).asUInt
  io.ib_pop0_pred_taken := buffer.io.popPredTaken(0).asUInt
  io.ib_pop0_is_last := buffer.io.popIsLast(0).asUInt
  io.ib_pop0_ftq_id := buffer.io.popFtqId(0).asUInt
  io.ib_pop0_excp := buffer.io.popExcp(0).asUInt
  buffer.io.popReady(0) := io.ib_pop0_ready.asBool
  io.ib_pop1_valid := buffer.io.popValid(1).asUInt
  io.ib_pop1_pc := buffer.io.popPc(1).asUInt
  io.ib_pop1_inst := buffer.io.popInst(1).asUInt
  io.ib_pop1_pred_taken := buffer.io.popPredTaken(1).asUInt
  io.ib_pop1_is_last := buffer.io.popIsLast(1).asUInt
  io.ib_pop1_ftq_id := buffer.io.popFtqId(1).asUInt
  io.ib_pop1_excp := buffer.io.popExcp(1).asUInt
  buffer.io.popReady(1) := io.ib_pop1_ready.asBool
}
