// RsMem: 访存保留站（参数化 FIFO + 有限 load 越过）。
// 移植自 cpu/rs_mem.v。要点：
// - 默认按程序序发射；普通可缓存 load 可越过前方未就绪普通 load（发射拍
//   选中项与队头交换，再按 head 出队，经一级 swap 缓冲延一拍完成搬移）；
// - store 是顺序屏障（不可被越过、不越过别人）；
// - 正式写回由ROB/Dispatch在入站前最终化；resident entry保留5路写回与early0/1/2唤醒；
// - 队头镜像 head_s0/s1_robid_q 随环指针推进；scan_count_mask 免桶形移位；
// - fused-pair 通道结构性不存在（输出恒 0，端口保留）。
package e91c.backend

import chisel3._
import chisel3.util.{Cat, Fill, MuxCase, PriorityEncoder, ValidIO, is, log2Ceil, switch}
import e91c.config.Params._
import e91c.config.MemOp
import e91c.mem.PhysicalMemoryAttributes

class RsMem extends Module {
  val io = IO(new Bundle {
    val flush = Input(Bool())
    // An early VA cacheability hint is valid only on an identity/direct path.
    val dataTranslationActive = Input(Bool())
    // 入站（dispatch）×2
    val pushValid = Input(Bool()); val pushRobid = Input(UInt(ROB_W.W)); val pushMemOp = Input(UInt(MemOp.NUM.W))
    val pushSrc0Ready = Input(Bool()); val pushSrc0Val = Input(UInt(32.W)); val pushSrc0Robid = Input(UInt(ROB_W.W))
    val pushSrc0KeyVal = Input(UInt(32.W)); val pushSrc0RobWait = Input(Bool())
    val pushSrc1Ready = Input(Bool()); val pushSrc1Val = Input(UInt(32.W)); val pushSrc1Robid = Input(UInt(ROB_W.W))
    val pushImm = Input(UInt(32.W))
    val push1Valid = Input(Bool()); val push1Robid = Input(UInt(ROB_W.W)); val push1MemOp = Input(UInt(MemOp.NUM.W))
    val push1Src0Ready = Input(Bool()); val push1Src0Val = Input(UInt(32.W)); val push1Src0Robid = Input(UInt(ROB_W.W))
    val push1Src0KeyVal = Input(UInt(32.W)); val push1Src0RobWait = Input(Bool())
    val push1Src1Ready = Input(Bool()); val push1Src1Val = Input(UInt(32.W)); val push1Src1Robid = Input(UInt(ROB_W.W))
    val push1Imm = Input(UInt(32.W))
    val canAccept = Output(Bool()); val canAcceptTwo = Output(Bool()); val occupancy = Output(UInt(3.W))
    // 写回唤醒总线 ×6
    val wb = Vec(5, Flipped(ValidIO(new Bundle {
      val robid = UInt(ROB_W.W); val data = UInt(32.W)
    })))
    // LSU miss/pending 描述符（已寄存）
    val missWaitValid = Input(UInt(LSU_MISS_DEPTH.W))
    val missWaitRobids = Input(UInt((LSU_MISS_DEPTH * ROB_W).W))
    val pendingLoadValid = Input(UInt(LSU_TOKEN_DEPTH.W))
    val pendingLoadRobids = Input(UInt((LSU_TOKEN_DEPTH * ROB_W).W))
    // 提前唤醒 ×3
    val early = Vec(3, Flipped(ValidIO(UInt(ROB_W.W))))
    // 发射口
    val issueValid = Output(Bool()); val issueRobid = Output(UInt(ROB_W.W)); val issueMemOp = Output(UInt(MemOp.NUM.W))
    val issueBase = Output(UInt(32.W)); val issueBaseReady = Output(Bool()); val issueBaseRobid = Output(UInt(ROB_W.W))
    val issueWdata = Output(UInt(32.W)); val issueWdataReady = Output(Bool()); val issueWdataRobid = Output(UInt(ROB_W.W))
    val issueImm = Output(UInt(32.W))
    val issueOrderSpeculative = Output(Bool()); val issueOrderStoreTag = Output(UInt(ROB_W.W))
    val lsuReady = Input(Bool()); val lsuPlainOnly = Input(Bool())
    val issuePairValid = Output(Bool()); val issuePairRobid = Output(UInt(ROB_W.W))
    val issuePairMemOp = Output(UInt(MemOp.NUM.W)); val issuePairBase = Output(UInt(32.W)); val issuePairImm = Output(UInt(32.W))
    val lsuPairReady = Input(Bool())
  })

  private val SZ = RS_MEM_SIZE
  require(SZ == 2 || SZ == 4)
  private val IDW = log2Ceil(SZ)

  // ---------------- 项阵列 ----------------
  val validA = Seq.fill(SZ)(RegInit(false.B))
  val robidA = Seq.fill(SZ)(Reg(UInt(ROB_W.W)))
  val memOpA = Seq.fill(SZ)(Reg(UInt(MemOp.NUM.W)))
  val plainLoadA = Seq.fill(SZ)(RegInit(false.B))
  val plainStoreA = Seq.fill(SZ)(RegInit(false.B))
  val s0ValValidA = Seq.fill(SZ)(Reg(Bool()))
  val s0Alu0PredA = Seq.fill(SZ)(RegInit(false.B))
  val s0Alu1PredA = Seq.fill(SZ)(RegInit(false.B))
  val s0MemPredA = Seq.fill(SZ)(RegInit(false.B))
  val s0ValA = Seq.fill(SZ)(RegInit(0.U(32.W)))
  val s0RobidA = Seq.fill(SZ)(Reg(UInt(ROB_W.W)))
  val s1ValValidA = Seq.fill(SZ)(Reg(Bool()))
  val s1Alu0PredA = Seq.fill(SZ)(RegInit(false.B))
  val s1Alu1PredA = Seq.fill(SZ)(RegInit(false.B))
  val s1MemPredA = Seq.fill(SZ)(RegInit(false.B))
  val s1ValA = Seq.fill(SZ)(Reg(UInt(32.W)))
  val s1RobidA = Seq.fill(SZ)(Reg(UInt(ROB_W.W)))
  val immA = Seq.fill(SZ)(Reg(UInt(12.W)))
  val pairKeyA = Seq.fill(SZ)(RegInit(0.U(27.W)))
  val s0KeyRefreshA = Seq.fill(SZ)(RegInit(false.B))

  // Vec 视图（硬件索引读）
  def bv(seq: Seq[Bool]) = VecInit(seq)
  val validV = bv(validA); val plainLoadV = bv(plainLoadA); val plainStoreV = bv(plainStoreA)
  val s0ValValidV = bv(s0ValValidA); val s0Alu0PredV = bv(s0Alu0PredA); val s0Alu1PredV = bv(s0Alu1PredA)
  val s0MemPredV = bv(s0MemPredA); val s0ValV = VecInit(s0ValA); val s0RobidV = VecInit(s0RobidA)
  val s1ValValidV = bv(s1ValValidA); val s1Alu0PredV = bv(s1Alu0PredA); val s1Alu1PredV = bv(s1Alu1PredA)
  val s1MemPredV = bv(s1MemPredA); val s1ValV = VecInit(s1ValA); val s1RobidV = VecInit(s1RobidA)
  val immV = VecInit(immA); val pairKeyV = VecInit(pairKeyA); val robidV = VecInit(robidA)
  val memOpV = VecInit(memOpA)
  val s0KeyRefV = bv(s0KeyRefreshA)

  val head = RegInit(0.U(IDW.W)); val tail = RegInit(0.U(IDW.W))
  val count = RegInit(0.U(3.W))
  val queueNonempty = count =/= 0.U
  val headS0RobidQ = RegInit(0.U(ROB_W.W)); val headS1RobidQ = RegInit(0.U(ROB_W.W))
  val scanCountMask = RegInit(0.U(SZ.W))

  // Conservative early hint only. Final PA/MAT is always recomputed after Sv32
  // in PmaMmu before any cache/bus side effect. Under translation no VA can be
  // called known-cacheable; the queue therefore retains program order.
  val scanKnownCached = VecInit((0 until SZ).map { sc =>
    val directAddress = Cat(pairKeyA(sc), 0.U(5.W))
    // A writeback makes the operand ready one cycle before pairKey refreshes.
    // Never use that stale key to let MMIO bypass an older unready store.
    s0ValValidA(sc) && !s0KeyRefreshA(sc) && !io.dataTranslationActive &&
      (PhysicalMemoryAttributes.dataMat(directAddress) === PhysicalMemoryAttributes.MatCacheable)
  })

  // 非队头发射后保留原有一拍气泡；两项配置在发射沿直接完成槽搬移。
  val swapPending = RegInit(false.B)

  // ---------------- WB / early 命中（逐项）----------------
  private def wbMatch(t: UInt): Bool = io.wb.map(w => w.valid && w.bits.robid === t).reduce(_ || _)
  private def wbDataOf(t: UInt): UInt = {
    val matches = io.wb.map(w => w.valid && w.bits.robid === t)
    val mask = VecInit(matches).asUInt
    val index = Mux(mask.orR, PriorityEncoder(mask), 0.U)
    val data = VecInit(io.wb.map(_.bits.data))(index)
    if (!sys.props.get("e91c.synthesis").contains("true")) {
      val reference = MuxCase(0.U, (0 until 5).map(i => matches(i) -> io.wb(i).bits.data))
      val checkArmed = RegNext(true.B, false.B)
      when(checkArmed && mask.orR) { assert(data === reference, "MEM WB priority mismatch") }
    }
    data // every consumer is guarded by the matching hit
  }

  val s0WbMatch = VecInit((0 until SZ).map(gw => wbMatch(s0RobidA(gw))))
  val s1WbMatch = VecInit((0 until SZ).map(gw => wbMatch(s1RobidA(gw))))
  val s0Wbhit = VecInit((0 until SZ).map(gw => !s0ValValidA(gw) && s0WbMatch(gw)))
  val s1Wbhit = VecInit((0 until SZ).map(gw => !s1ValValidA(gw) && s1WbMatch(gw)))
  private def earlyHit(t: UInt, k: Int): Bool = io.early(k).valid && io.early(k).bits === t
  val s0Alu1Eh = VecInit((0 until SZ).map(gw => !s0ValValidA(gw) && earlyHit(s0RobidA(gw), 1)))
  val s1Alu1Eh = VecInit((0 until SZ).map(gw => !s1ValValidA(gw) && earlyHit(s1RobidA(gw), 1)))
  val s0Alu0Eh = VecInit((0 until SZ).map(gw => !s0ValValidA(gw) && earlyHit(s0RobidA(gw), 0)))
  val s1Alu0Eh = VecInit((0 until SZ).map(gw => !s1ValValidA(gw) && earlyHit(s1RobidA(gw), 0)))
  val s0MemEh = VecInit((0 until SZ).map(gw => !s0ValValidA(gw) && earlyHit(s0RobidA(gw), 2)))
  val s1MemEh = VecInit((0 until SZ).map(gw => !s1ValValidA(gw) && earlyHit(s1RobidA(gw), 2)))
  // A WB hit already wins the later when/elsewhen chain. Keep the early
  // producer comparison off the WB priority path to the prediction registers.
  val s0Earlyhit = VecInit((0 until SZ).map(gw =>
    s0Alu0Eh(gw) || s0Alu1Eh(gw) || s0MemEh(gw)))
  val s1Earlyhit = VecInit((0 until SZ).map(gw =>
    s1Alu0Eh(gw) || s1Alu1Eh(gw) || s1MemEh(gw)))
  val s0Wbdat = VecInit((0 until SZ).map(gw => wbDataOf(s0RobidA(gw))))
  val s1Wbdat = VecInit((0 until SZ).map(gw => wbDataOf(s1RobidA(gw))))

  val issueBaseCand = VecInit((0 until SZ).map(gw =>
    Mux(!s0ValValidA(gw) && io.wb(0).valid && io.wb(0).bits.robid === s0RobidA(gw), io.wb(0).bits.data,
    Mux(!s0ValValidA(gw) && io.wb(1).valid && io.wb(1).bits.robid === s0RobidA(gw), io.wb(1).bits.data,
    Mux(!s0ValValidA(gw) && io.wb(2).valid && io.wb(2).bits.robid === s0RobidA(gw), io.wb(2).bits.data,
      s0ValA(gw))))))

  val entryReady = VecInit((0 until SZ).map(gw =>
    validA(gw) &&
      (s0ValValidA(gw) || s0Alu0PredA(gw) || s0Alu1PredA(gw) || s0MemPredA(gw)) &&
      (s1ValValidA(gw) || s1Alu0PredA(gw) || s1Alu1PredA(gw) || s1MemPredA(gw))))
  val isOrdBarrier = VecInit((0 until SZ).map(gw => !plainLoadA(gw) && !plainStoreA(gw)))
  val isPlainLoadV = plainLoadV

  val s0RefKey = VecInit((0 until SZ).map { gw =>
    val immExt = Cat(Fill(20, immA(gw)(11)), immA(gw))
    val lo = Cat(0.U(1.W), s0ValA(gw)(4, 0)) +& Cat(0.U(1.W), immExt(4, 0))
    s0ValA(gw)(31, 5) + immExt(31, 5) + Cat(0.U(26.W), lo(5))
  })

  // ---------------- 队头快速就绪 ----------------
  val headS0Wb0Hit = !s0ValValidV(head) && io.wb(0).valid && io.wb(0).bits.robid === headS0RobidQ
  val headS1Wb0Hit = !s1ValValidV(head) && io.wb(0).valid && io.wb(0).bits.robid === headS1RobidQ
  val headS0Wb1Hit = !s0ValValidV(head) && io.wb(1).valid && io.wb(1).bits.robid === headS0RobidQ
  val headS1Wb1Hit = !s1ValValidV(head) && io.wb(1).valid && io.wb(1).bits.robid === headS1RobidQ
  val headS0Wb2Hit = !s0ValValidV(head) && io.wb(2).valid && io.wb(2).bits.robid === headS0RobidQ
  val headS1Wb2Hit = !s1ValValidV(head) && io.wb(2).valid && io.wb(2).bits.robid === headS1RobidQ
  val headS0FastHit = false.B
  val headDirectReady = queueNonempty && validV(head) &&
    (headS0Wb0Hit || headS1Wb0Hit || headS0Wb1Hit || headS1Wb1Hit ||
      headS0Wb2Hit || headS1Wb2Hit || headS0FastHit) &&
    (s0ValValidV(head) || s0Alu0PredV(head) || s0Alu1PredV(head) || s0MemPredV(head) ||
      headS0Wb0Hit || headS0Wb1Hit || headS0Wb2Hit || headS0FastHit) &&
    (s1ValValidV(head) || s1Alu0PredV(head) || s1Alu1PredV(head) || s1MemPredV(head) ||
      headS1Wb0Hit || headS1Wb1Hit || headS1Wb2Hit)

  // miss/pending 描述符放行（仅队头普通 load/store）
  val headS0MissMatch = VecInit((0 until LSU_MISS_DEPTH).map(m =>
    io.missWaitValid(m) && !s0ValValidV(head) &&
      io.missWaitRobids(m * ROB_W + ROB_W - 1, m * ROB_W) === headS0RobidQ)).asUInt
  val headS1MissMatch = VecInit((0 until LSU_MISS_DEPTH).map(m =>
    io.missWaitValid(m) && !s1ValValidV(head) &&
      io.missWaitRobids(m * ROB_W + ROB_W - 1, m * ROB_W) === headS1RobidQ)).asUInt
  val headIsPlainLoad = plainLoadV(head)
  val headIsPlainStore = plainStoreV(head)
  val headBasePresent = s0ValValidV(head) || s0Alu0PredV(head) || s0Alu1PredV(head) || s0MemPredV(head) ||
    headS0Wb0Hit || headS0Wb1Hit || headS0Wb2Hit
  val headDataPresent = s1ValValidV(head) || s1Alu0PredV(head) || s1Alu1PredV(head) || s1MemPredV(head) ||
    headS1Wb0Hit || headS1Wb1Hit || headS1Wb2Hit
  val headS0TokenMatch = VecInit((0 until LSU_TOKEN_DEPTH).map(t =>
    io.pendingLoadValid(t) && !s0ValValidV(head) &&
      io.pendingLoadRobids(t * ROB_W + ROB_W - 1, t * ROB_W) === headS0RobidQ)).asUInt
  val headS1TokenMatch = VecInit((0 until LSU_TOKEN_DEPTH).map(t =>
    io.pendingLoadValid(t) && !s1ValValidV(head) &&
      io.pendingLoadRobids(t * ROB_W + ROB_W - 1, t * ROB_W) === headS1RobidQ)).asUInt
  val headS0PendingMatch = headS0TokenMatch.orR
  val headS1PendingMatch = headS1TokenMatch.orR
  val headBaseRegProd = headS0PendingMatch || headS0MissMatch.orR
  val headDataRegProd = headS1PendingMatch || headS1MissMatch.orR
  val headLocalWaitReady = queueNonempty && validV(head) &&
    headIsPlainLoad &&
    (headBasePresent || headBaseRegProd) &&
    (headDataPresent || (headIsPlainStore && headDataRegProd)) &&
    (!headBasePresent || (headIsPlainStore && !headDataPresent))

  // head+1 直接就绪
  val head1Idx = Wire(UInt(IDW.W)); head1Idx := head + 1.U
  val head2Idx = Wire(UInt(IDW.W)); head2Idx := head + 2.U
  val head1KnownCached = scanKnownCached(head1Idx)
  val head1S0Wb2Hit = !s0ValValidV(head1Idx) && io.wb(2).valid && io.wb(2).bits.robid === s0RobidV(head1Idx)
  val head1S1Wb2Hit = !s1ValValidV(head1Idx) && io.wb(2).valid && io.wb(2).bits.robid === s1RobidV(head1Idx)
  val head1S0Wb1Hit = !s0ValValidV(head1Idx) && io.wb(1).valid && io.wb(1).bits.robid === s0RobidV(head1Idx)
  val head1S1Wb1Hit = !s1ValValidV(head1Idx) && io.wb(1).valid && io.wb(1).bits.robid === s1RobidV(head1Idx)
  val head1DirectReady = (count > 1.U) &&
    validV(head) && !isOrdBarrier(head) && scanKnownCached(head) &&
    !entryReady(head) && !headDirectReady &&
    validV(head1Idx) && plainLoadV(head1Idx) && head1KnownCached &&
    (head1S0Wb1Hit || head1S1Wb1Hit || head1S0Wb2Hit || head1S1Wb2Hit) &&
    (s0ValValidV(head1Idx) || s0Alu0PredV(head1Idx) || s0Alu1PredV(head1Idx) || s0MemPredV(head1Idx) ||
      head1S0Wb1Hit || head1S0Wb2Hit) &&
    (s1ValValidV(head1Idx) || s1Alu0PredV(head1Idx) || s1Alu1PredV(head1Idx) || s1MemPredV(head1Idx) ||
      head1S1Wb1Hit || head1S1Wb2Hit)

  // ---------------- 年龄序扫描 ----------------
  val scanReadyAge = (Cat(entryReady.asUInt, entryReady.asUInt) >> head)(SZ - 1, 0)
  val scanBarrierAge = (Cat(isOrdBarrier.asUInt, isOrdBarrier.asUInt) >> head)(SZ - 1, 0)
  val scanPlainLoadAge = (Cat(isPlainLoadV.asUInt, isPlainLoadV.asUInt) >> head)(SZ - 1, 0)
  val scanValidAge = (Cat(validV.asUInt, validV.asUInt) >> head)(SZ - 1, 0)
  val scanCachedAge = (Cat(scanKnownCached.asUInt, scanKnownCached.asUInt) >> head)(SZ - 1, 0)
  val scanLiveAge = scanValidAge & scanCountMask
  val scanBlockerAge = scanLiveAge & scanBarrierAge
  val scanUnknownMatAge = scanLiveAge & ~scanCachedAge
  val scanCandidateAge = Wire(UInt(SZ.W))
  // Adjacent bypass preserves the relative order of all remaining stores.
  // Unknown-address stores stay in this RS until their operands are available.
  private val SCAN_LIMIT = 2
  scanCandidateAge := VecInit((0 until SZ).map { age =>
    if (age == 0) scanLiveAge(0) && scanReadyAge(0)
    else if (age == 1 && age < SCAN_LIMIT)
      scanPlainLoadAge(age) && scanCachedAge(age) && scanLiveAge(age) &&
        scanReadyAge(age) && !scanBlockerAge(age, 0).orR
    else if (age < SCAN_LIMIT)
      scanPlainLoadAge(age) && scanCachedAge(age) && !scanUnknownMatAge(age, 0).orR && scanLiveAge(age) &&
        scanReadyAge(age) && !scanBlockerAge(age, 0).orR
    else false.B
  }).asUInt

  val scanTreeValid = scanCandidateAge.orR
  val scanTreeAge = PriorityEncoder(scanCandidateAge)

  // 基础发射选择
  val headLocalWaitReadyW = WireDefault(headLocalWaitReady)
  val baseIssueIdx = WireDefault(head + scanTreeAge)
  val baseIssueAge = WireDefault(scanTreeAge)
  val baseIssueValid = WireDefault(scanTreeValid)
  when(headLocalWaitReady) {
    baseIssueIdx := head; baseIssueAge := 0.U; baseIssueValid := true.B
  }.elsewhen(headDirectReady) {
    baseIssueIdx := head; baseIssueAge := 0.U; baseIssueValid := true.B
  }.elsewhen(if (SCAN_LIMIT > 1) head1DirectReady && (!scanTreeValid || (scanTreeAge > 1.U)) else false.B) {
    baseIssueIdx := head1Idx; baseIssueAge := 1.U; baseIssueValid := true.B
  }
  val issueIdx = baseIssueIdx
  val issueSelValid = baseIssueValid
  val issuePastStore = queueNonempty && !swapPending && issueSelValid &&
    (issueIdx =/= head) && plainStoreV(head)
  io.issueOrderSpeculative := issuePastStore
  io.issueOrderStoreTag := robidV(head)

  io.issueValid := queueNonempty && !swapPending && issueSelValid && io.lsuReady &&
    (!io.lsuPlainOnly || ((baseIssueAge =/= 0.U) || headIsPlainLoad))
  val issueFire = io.issueValid
  val issueNeedSwap = issueFire && (issueIdx =/= head)
  if (!sys.props.get("e91c.synthesis").contains("true")) {
    when(issueNeedSwap) {
      assert(plainLoadV(issueIdx), "only a plain load may bypass the RsMem head")
      assert(scanKnownCached(issueIdx), "a non-head RsMem issue must have a conservative cacheable hint")
      assert(PhysicalMemoryAttributes.dataMat(io.issueBase + io.issueImm) ===
        PhysicalMemoryAttributes.MatCacheable,
        "a non-head RsMem issue must match the actual cacheable address")
      when(plainStoreV(head)) {
        assert(io.issueOrderSpeculative, "a load bypassing a store must reserve load-order ownership")
        assert(io.issueOrderStoreTag === robidV(head), "load-order barrier owner mismatch")
      }
    }
  }

  // ---------------- push 侧唤醒/键 ----------------
  private def opIsLoad(op: UInt) = !op(MemOp.ATOMIC) && (op(MemOp.LD_W) || op(MemOp.LD_B) || op(MemOp.LD_H) || op(MemOp.LD_BU) || op(MemOp.LD_HU))
  private def opIsStore(op: UInt) = !op(MemOp.ATOMIC) && (op(MemOp.ST_W) || op(MemOp.ST_B) || op(MemOp.ST_H))
  val push0PlainLoad = opIsLoad(io.pushMemOp)
  val push0PlainStore = opIsStore(io.pushMemOp)
  val push1PlainLoad = opIsLoad(io.push1MemOp)
  val push1PlainStore = opIsStore(io.push1MemOp)

  val pushS0Alu0Pred = !io.pushSrc0Ready && earlyHit(io.pushSrc0Robid, 0)
  val pushS1Alu0Pred = !io.pushSrc1Ready && earlyHit(io.pushSrc1Robid, 0)
  val pushS0Alu1Pred = !io.pushSrc0Ready && earlyHit(io.pushSrc0Robid, 1)
  val pushS1Alu1Pred = !io.pushSrc1Ready && earlyHit(io.pushSrc1Robid, 1)
  val pushS0MemPred = !io.pushSrc0Ready && earlyHit(io.pushSrc0Robid, 2)
  val pushS1MemPred = !io.pushSrc1Ready && earlyHit(io.pushSrc1Robid, 2)
  val push1S0Alu0Pred = !io.push1Src0Ready && earlyHit(io.push1Src0Robid, 0)
  val push1S1Alu0Pred = !io.push1Src1Ready && earlyHit(io.push1Src1Robid, 0)
  val push1S0Alu1Pred = !io.push1Src0Ready && earlyHit(io.push1Src0Robid, 1)
  val push1S1Alu1Pred = !io.push1Src1Ready && earlyHit(io.push1Src1Robid, 1)
  val push1S0MemPred = !io.push1Src0Ready && earlyHit(io.push1Src0Robid, 2)
  val push1S1MemPred = !io.push1Src1Ready && earlyHit(io.push1Src1Robid, 2)

  val push0Wb0KeyHit = io.pushSrc0RobWait && io.wb(0).valid && io.wb(0).bits.robid === io.pushSrc0Robid
  val push0Wb1KeyHit = io.pushSrc0RobWait && io.wb(1).valid && io.wb(1).bits.robid === io.pushSrc0Robid &&
    !(io.wb(0).valid && io.wb(0).bits.robid === io.pushSrc0Robid)
  val push1Wb0KeyHit = io.push1Src0RobWait && io.wb(0).valid && io.wb(0).bits.robid === io.push1Src0Robid
  val push1Wb1KeyHit = io.push1Src0RobWait && io.wb(1).valid && io.wb(1).bits.robid === io.push1Src0Robid &&
    !(io.wb(0).valid && io.wb(0).bits.robid === io.push1Src0Robid)
  val push0KeyBase = Mux(push0Wb0KeyHit, io.wb(0).bits.data,
    Mux(push0Wb1KeyHit, io.wb(1).bits.data,
    io.pushSrc0KeyVal))
  val push1KeyBase = Mux(push1Wb0KeyHit, io.wb(0).bits.data,
    Mux(push1Wb1KeyHit, io.wb(1).bits.data,
    io.push1Src0KeyVal))
  val push0KeyVaddr = push0KeyBase + io.pushImm
  val push1KeyVaddr = push1KeyBase + io.push1Imm
  val push0Key = push0KeyVaddr(31, 5)
  val push1Key = push1KeyVaddr(31, 5)

  // ---------------- 接受 / 发射输出 ----------------
  io.occupancy := count
  io.canAccept := !swapPending && (count =/= SZ.U)
  io.canAcceptTwo := !swapPending && (count <= (SZ - 2).U)
  val push0Fire = io.pushValid && io.canAccept
  val push1Fire = io.push1Valid && io.canAcceptTwo && push0Fire

  if (!sys.props.get("e91c.synthesis").contains("true")) {
    when(push0Fire && !io.pushSrc0Ready) {
      assert(!wbMatch(io.pushSrc0Robid),
        "Dispatch must expose a same-cycle source-0 writeback before MEM push0")
    }
    when(push0Fire && !io.pushSrc1Ready) {
      assert(!wbMatch(io.pushSrc1Robid),
        "Dispatch must expose a same-cycle source-1 writeback before MEM push0")
    }
    when(push1Fire && !io.push1Src0Ready) {
      assert(!wbMatch(io.push1Src0Robid),
        "Dispatch must expose a same-cycle source-0 writeback before MEM push1")
    }
    when(push1Fire && !io.push1Src1Ready) {
      assert(!wbMatch(io.push1Src1Robid),
        "Dispatch must expose a same-cycle source-1 writeback before MEM push1")
    }
  }

  io.issueRobid := robidV(issueIdx)
  io.issueMemOp := memOpV(issueIdx)
  val issueLocalWait = (issueIdx === head) && headLocalWaitReady
  val issueBaseWait = issueLocalWait && !headBasePresent
  val issueStoreWait = issueLocalWait && headIsPlainStore && !headDataPresent
  io.issueBase := issueBaseCand(issueIdx)
  io.issueBaseReady := !issueBaseWait
  io.issueBaseRobid := s0RobidV(issueIdx)
  io.issueWdata := Mux(headS1Wb0Hit, io.wb(0).bits.data,
    Mux(headS1Wb1Hit, io.wb(1).bits.data,
    Mux(headS1Wb2Hit, io.wb(2).bits.data,
    Mux(s1Alu0PredV(head), io.wb(0).bits.data,
    Mux(s1Alu1PredV(head), io.wb(1).bits.data,
    Mux(s1MemPredV(head), io.wb(2).bits.data, s1ValV(head)))))))
  io.issueWdataReady := !issueStoreWait
  io.issueWdataRobid := headS1RobidQ
  io.issueImm := Cat(Fill(20, immV(issueIdx)(11)), immV(issueIdx))

  // fused-pair 通道结构性不存在
  io.issuePairValid := false.B
  io.issuePairRobid := 0.U
  io.issuePairMemOp := 0.U
  io.issuePairBase := 0.U
  io.issuePairImm := 0.U
  val issuePairFire = false.B
  val issuePairAccept = false.B
  val issuePairIdx = head

  // ================= 时序 =================
  val headAfterIdx = Mux(issuePairFire, head2Idx, Mux(issueFire, head1Idx, head))
  val headAfterS0Robid = Mux(issuePairFire, s0RobidV(head2Idx), s0RobidV(head1Idx))
  val headAfterS1Robid = Mux(issuePairFire, s1RobidV(head2Idx), s1RobidV(head1Idx))
  val headAfterFromPush0 = push0Fire && (tail === headAfterIdx)
  val headAfterFromSwapMove = issueFire && !issuePairFire && issueNeedSwap && (issueIdx === headAfterIdx)

  when(io.flush) {
    head := 0.U; tail := 0.U; count := 0.U
    scanCountMask := 0.U
    swapPending := false.B
    headS0RobidQ := 0.U; headS1RobidQ := 0.U
    for (i <- 0 until SZ) {
      validA(i) := false.B
      plainLoadA(i) := false.B
      plainStoreA(i) := false.B
      s0Alu0PredA(i) := false.B
      s0Alu1PredA(i) := false.B
      s0MemPredA(i) := false.B
      s1Alu0PredA(i) := false.B
      s1Alu1PredA(i) := false.B
      s1MemPredA(i) := false.B
      pairKeyA(i) := 0.U
      s0KeyRefreshA(i) := false.B
      s0ValA(i) := 0.U
    }
  }.otherwise {
    // ---- 逐项唤醒 ----
    for (i <- 0 until SZ) {
      when(validA(i)) {
        when(s0Wbhit(i)) {
          s0ValValidA(i) := true.B
          s0ValA(i) := s0Wbdat(i)
          s0Alu0PredA(i) := false.B
          s0Alu1PredA(i) := false.B
          s0MemPredA(i) := false.B
          s0KeyRefreshA(i) := true.B
        }.elsewhen(s0KeyRefV(i)) {
          pairKeyA(i) := s0RefKey(i)
          s0KeyRefreshA(i) := false.B
        }.elsewhen(s0Earlyhit(i)) {
          s0Alu0PredA(i) := s0Alu0Eh(i)
          s0Alu1PredA(i) := s0Alu1Eh(i)
          s0MemPredA(i) := s0MemEh(i)
          s0ValA(i) := Mux(s0Alu0Eh(i), io.wb(0).bits.data,
            Mux(s0Alu1Eh(i), io.wb(1).bits.data,
            Mux(s0MemEh(i), io.wb(2).bits.data, s0ValA(i))))
        }
        when(s1Wbhit(i)) {
          s1ValValidA(i) := true.B
          s1ValA(i) := s1Wbdat(i)
          s1Alu0PredA(i) := false.B
          s1Alu1PredA(i) := false.B
          s1MemPredA(i) := false.B
        }.elsewhen(s1Earlyhit(i)) {
          s1Alu0PredA(i) := s1Alu0Eh(i)
          s1Alu1PredA(i) := s1Alu1Eh(i)
          s1MemPredA(i) := s1MemEh(i)
        }
      }
    }

    // ---- 队头镜像 ----
    when(headAfterFromPush0) {
      headS0RobidQ := io.pushSrc0Robid
      headS1RobidQ := io.pushSrc1Robid
    }.elsewhen(headAfterFromSwapMove) {
      // 保持：直接搬移的目标槽就是发射后的队头，标签未变。
    }.elsewhen(issuePairFire || issueFire) {
      headS0RobidQ := headAfterS0Robid
      headS1RobidQ := headAfterS1Robid
    }

    // The relocated entry remains in the ordinary array during this bubble, so
    // the normal per-entry wakeup loop above observes the second cycle's buses.
    when(swapPending) { swapPending := false.B }

    // ---- 发射出队 / 两项配置直接搬移 ----
    when(issueFire && !issuePairFire) {
      when(issueNeedSwap) {
        swapPending := true.B
        for (i <- 0 until SZ) when(issueIdx === i.U) {
          robidA(i) := robidV(head)
          memOpA(i) := memOpV(head)
          plainLoadA(i) := plainLoadV(head)
          plainStoreA(i) := plainStoreV(head)
          s0ValValidA(i) := s0ValValidV(head) || s0Wbhit(head)
          s0Alu0PredA(i) := (s0Alu0PredV(head) || s0Alu0Eh(head)) && !s0Wbhit(head)
          s0Alu1PredA(i) := (s0Alu1PredV(head) || s0Alu1Eh(head)) && !s0Wbhit(head)
          s0MemPredA(i) := (s0MemPredV(head) || s0MemEh(head)) && !s0Wbhit(head)
          s0ValA(i) := Mux(s0Wbhit(head), s0Wbdat(head), s0ValV(head))
          s0RobidA(i) := headS0RobidQ
          s1ValValidA(i) := s1ValValidV(head) || s1Wbhit(head)
          s1Alu0PredA(i) := (s1Alu0PredV(head) || s1Alu0Eh(head)) && !s1Wbhit(head)
          s1Alu1PredA(i) := (s1Alu1PredV(head) || s1Alu1Eh(head)) && !s1Wbhit(head)
          s1MemPredA(i) := (s1MemPredV(head) || s1MemEh(head)) && !s1Wbhit(head)
          s1ValA(i) := Mux(s1Wbhit(head), s1Wbdat(head), s1ValV(head))
          s1RobidA(i) := headS1RobidQ
          immA(i) := immV(head)
          when(s0Wbhit(head) || s0ValValidV(head)) {
            s0KeyRefreshA(i) := true.B
          }.otherwise {
            pairKeyA(i) := pairKeyV(head)
            s0KeyRefreshA(i) := false.B
          }
          validA(i) := true.B
        }
      }
      head := head + 1.U
    }

    // （fused-pair 压缩结构性不存在：issuePairAccept=false）

    // ---- push0 ----
    when(push0Fire) {
      for (i <- 0 until SZ) when(tail === i.U) {
        validA(i) := true.B
        robidA(i) := io.pushRobid
        memOpA(i) := io.pushMemOp
        plainLoadA(i) := push0PlainLoad
        plainStoreA(i) := push0PlainStore
        s0ValValidA(i) := io.pushSrc0Ready
        s0Alu0PredA(i) := pushS0Alu0Pred
        s0Alu1PredA(i) := pushS0Alu1Pred
        s0MemPredA(i) := pushS0MemPred
        s0ValA(i) := Mux(io.pushSrc0Ready, io.pushSrc0Val, 0.U)
        s0RobidA(i) := io.pushSrc0Robid
        s1ValValidA(i) := io.pushSrc1Ready
        s1Alu0PredA(i) := pushS1Alu0Pred
        s1Alu1PredA(i) := pushS1Alu1Pred
        s1MemPredA(i) := pushS1MemPred
        s1ValA(i) := Mux(io.pushSrc1Ready, io.pushSrc1Val, 0.U)
        s1RobidA(i) := io.pushSrc1Robid
        immA(i) := io.pushImm(11, 0)
        pairKeyA(i) := Mux(io.pushSrc0Ready, push0Key, 0.U)
        s0KeyRefreshA(i) := false.B
      }
    }

    // ---- push1 ----
    when(push1Fire) {
      val t1 = Wire(UInt(IDW.W)); t1 := tail + 1.U
      for (i <- 0 until SZ) when(t1 === i.U) {
        validA(i) := true.B
        robidA(i) := io.push1Robid
        memOpA(i) := io.push1MemOp
        plainLoadA(i) := push1PlainLoad
        plainStoreA(i) := push1PlainStore
        s0ValValidA(i) := io.push1Src0Ready
        s0Alu0PredA(i) := push1S0Alu0Pred
        s0Alu1PredA(i) := push1S0Alu1Pred
        s0MemPredA(i) := push1S0MemPred
        s0ValA(i) := Mux(io.push1Src0Ready, io.push1Src0Val, 0.U)
        s0RobidA(i) := io.push1Src0Robid
        s1ValValidA(i) := io.push1Src1Ready
        s1Alu0PredA(i) := push1S1Alu0Pred
        s1Alu1PredA(i) := push1S1Alu1Pred
        s1MemPredA(i) := push1S1MemPred
        s1ValA(i) := Mux(io.push1Src1Ready, io.push1Src1Val, 0.U)
        s1RobidA(i) := io.push1Src1Robid
        immA(i) := io.push1Imm(11, 0)
        pairKeyA(i) := Mux(io.push1Src0Ready, push1Key, 0.U)
        s0KeyRefreshA(i) := false.B
      }
    }

    when(push1Fire) { tail := tail + 2.U }
      .elsewhen(push0Fire) { tail := tail + 1.U }

    // ---- count / mask ----
    val comb = Cat(push1Fire, push0Fire, issueFire, issuePairFire)
    switch(comb) {
      is("b1100".U) { count := count + 2.U; scanCountMask := (scanCountMask << 2) | "b11".U }
      is("b1110".U) { count := count + 1.U; scanCountMask := (scanCountMask << 1) | "b1".U }
      is("b0100".U) { count := count + 1.U; scanCountMask := (scanCountMask << 1) | "b1".U }
      is("b0111".U) { count := count - 1.U; scanCountMask := scanCountMask >> 1 }
      is("b0010".U) { count := count - 1.U; scanCountMask := scanCountMask >> 1 }
      is("b0011".U) { count := count - 2.U; scanCountMask := scanCountMask >> 2 }
    }
  }
}

