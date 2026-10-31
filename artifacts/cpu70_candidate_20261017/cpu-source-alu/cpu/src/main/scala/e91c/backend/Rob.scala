// Rob: 重排序缓冲（奇偶双体环形队列，队列式重命名的核心）。
// 移植自 cpu/rob.v。要点：
// - 32 项 = 16 对 ×2 路；每拍最多分配 3 项（a0/a1/a2，tail_half 错位装填）；
// - ROB 编号三重角色：重命名标签 + 程序序 + 结果存储索引；
// - 结果按写回源分 bank（alu0/1/2、mem、mem2、mdu）+ owner 表选择，
//   静态区按奇偶 + pair[0] 拆 4 个体（每体单写口 LUTRAM）；
// - dispatch 读口 6 个（同拍写回旁路，无 valid 门控防 ABA）；
// - mem 原始完成经一拍 shadow 转持久 complete；quad 视图支持 4 宽提交。
package e91c.backend

import chisel3._
import chisel3.util.Cat
import e91c.config.Params._
import e91c.config.PrivType
import e91c.reg.RobTagRegisterFile

class RobAllocSlot extends Bundle {
  val valid = Bool(); val pc = UInt(32.W); val inst = UInt(32.W)
  val rfWe = Bool(); val rd = UInt(5.W)
  val isLoad = Bool(); val isStore = Bool(); val isBranch = Bool()
  val brType = UInt(2.W); val predTaken = Bool(); val isLast = Bool()
  val ftqId = UInt(FTQ_W.W); val privVec = UInt(6.W); val csrNum = UInt(12.W)
  val excp = UInt(EXCP_NUM.W); val isNop = Bool()
}

class AluWb extends Bundle {
  val valid = Bool(); val robid = UInt(ROB_W.W); val data = UInt(32.W)
  val brTaken = Bool(); val brTarget = UInt(32.W)
}

class MemWb extends Bundle {
  val valid = Bool(); val robid = UInt(ROB_W.W); val data = UInt(32.W)
  val storeData = UInt(32.W)
  val paddr = UInt(32.W); val vaddr = UInt(32.W); val wstrb = UInt(4.W)
  val size = UInt(3.W); val uncached = Bool(); val excp = UInt(EXCP_NUM.W)
}

class MemWb2 extends Bundle {
  val valid = Bool(); val robid = UInt(ROB_W.W); val data = UInt(32.W)
  val paddr = UInt(32.W); val vaddr = UInt(32.W); val size = UInt(3.W)
}

class MduWb extends Bundle {
  val valid = Bool(); val robid = UInt(ROB_W.W); val data = UInt(32.W); val data2 = UInt(32.W)
}

class Rob extends Module {
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val archRead = Input(Vec(4, UInt(5.W)))
    val archData = Output(Vec(4, UInt(32.W)))
    val commitRfWe = Input(Vec(2, Bool()))
    val commitRd = Input(Vec(2, UInt(5.W)))
    val commitTag = Input(Vec(2, UInt(ROB_W.W)))
    // 分配口（rename）
    val allocEn = Input(Bool())
    val a = Vec(2, Input(new RobAllocSlot))
    val robTail = Output(UInt(ROB_PAIR_W.W))
    val robFull = Output(Bool())
    val robTailHalf = Output(Bool()); val robEmpty = Output(Bool())
    // dispatch 读口 ×6
    val raddr = Vec(4, Input(UInt(ROB_W.W)))
    val rrdy = Vec(4, Output(Bool()))
    val rdata = Vec(4, Output(UInt(32.W)))
    val rdataNoAlu = Vec(2, Output(UInt(32.W)))   // 口 0/2/4
    // LSU base 探测 ×2
    val baseProbeRobid = Vec(2, Input(UInt(ROB_W.W)))
    val baseProbeReady = Vec(2, Output(Bool()))
    val baseProbeData = Vec(2, Output(UInt(32.W)))
    // FU 写回
    val alu = Vec(2, Input(new AluWb))
    val memWb = Input(new MemWb)
    val memFwd = Input(new MemWb)
    val mem2Wb = Input(new MemWb2)
    val mduWb = Input(new MduWb)
    // 提交口
    val headRobid0 = Output(UInt(ROB_W.W))
    val cmtValid = Vec(2, Output(Bool()))
    val cmtComplete = Vec(2, Output(Bool()))
    val cmtPc = Vec(2, Output(UInt(32.W)))
    val cmtIsJal = Vec(2, Output(Bool()))
    val cmtRfWe = Vec(2, Output(Bool()))
    val cmtRd = Vec(2, Output(UInt(5.W)))
    val cmtResult = Vec(2, Output(UInt(32.W)))
    val cmtStoreData = Output(Vec(2, UInt(32.W)))
    val cmtResult2 = Vec(2, Output(UInt(32.W)))
    val cmtIsLoad = Vec(2, Output(Bool()))
    val cmtIsStore = Vec(2, Output(Bool()))
    val cmtPaddr = Vec(2, Output(UInt(32.W)))
    val cmtVaddr = Vec(2, Output(UInt(32.W)))
    val cmtWstrb = Vec(2, Output(UInt(4.W)))
    val cmtSize = Vec(2, Output(UInt(3.W)))
    val cmtUncached = Vec(2, Output(Bool()))
    val cmtIsBranch = Vec(2, Output(Bool()))
    val cmtBrType = Vec(2, Output(UInt(2.W)))
    val cmtPredTaken = Vec(2, Output(Bool()))
    val cmtBrTaken = Vec(2, Output(Bool()))
    val cmtBrTarget = Vec(2, Output(UInt(32.W)))
    val cmtIsLast = Vec(2, Output(Bool()))
    val cmtFtqId = Vec(2, Output(UInt(FTQ_W.W)))
    val cmtPrivVec = Vec(2, Output(UInt(6.W)))
    val cmtCsrNum = Vec(2, Output(UInt(12.W)))
    val cmtExcp = Vec(2, Output(UInt(EXCP_NUM.W)))
    val cmtHasExcpFast = Vec(2, Output(Bool()))
    val cmtHasPrivFast = Vec(2, Output(Bool()))
    val cmtPop = Input(Bool())
    val cmtClear0 = Input(Bool()); val cmtClear1 = Input(Bool())
  })

  private val PW = ROB_PAIR_W   // 4
  // ---------------- 指针与状态 ----------------
  val head = RegInit(0.U(PW.W)); val tail = RegInit(0.U(PW.W))
  val tailHalf = RegInit(false.B)
  val headStaticEvenQ = RegInit(0.U(PW.W)); val headStaticOddQ = RegInit(0.U(PW.W))

  val validA = RegInit(VecInit(Seq.fill(32)(false.B)))
  val completeEven = RegInit(VecInit(Seq.fill(16)(false.B)))
  val completeOdd = RegInit(VecInit(Seq.fill(16)(false.B)))
  val memShadowValid = RegInit(false.B)
  val memShadowRobid = RegInit(0.U(ROB_W.W))

  // Active results use ROB-tag identity.  Committed values live in a separate
  // architectural file, so tag reuse cannot overwrite architectural state.
  // Store operands and CSR updates are retirement payload, not GPR results.
  val registerFile = Module(new RobTagRegisterFile(tagReads = 7))
  val storeData = Mem(32, UInt(32.W))
  val result2Mdu = Mem(32, UInt(32.W))
  registerFile.io.flush := io.flush
  registerFile.io.archRead := io.archRead
  io.archData := registerFile.io.archData
  registerFile.io.retire := io.commitRfWe
  registerFile.io.retireRd := io.commitRd
  registerFile.io.retireTag := io.commitTag
  registerFile.io.write := VecInit(Seq(io.alu(0).valid, io.alu(1).valid,
    io.memFwd.valid, io.mem2Wb.valid, io.mduWb.valid))
  registerFile.io.writeTag := VecInit(Seq(io.alu(0).robid, io.alu(1).robid,
    io.memFwd.robid, io.mem2Wb.robid, io.mduWb.robid))
  registerFile.io.writeData := VecInit(Seq(io.alu(0).data, io.alu(1).data,
    io.memFwd.data, io.mem2Wb.data, io.mduWb.data))

  // mem 负载 bank：fwd = {unc,size,wstrb,vaddr,paddr}(72b)，mem2 = {size,vaddr,paddr}(67b)
  val memPayloadFwd = Mem(32, UInt(72.W))
  val memPayloadMem2 = Mem(32, UInt(67.W))
  val memPayloadOwner = Reg(Vec(32, Bool()))

  // 分支负载：{target[31:1], taken}(32b)
  val brPayloadAlu0 = Mem(32, UInt(32.W))
  val brPayloadAlu1 = Mem(32, UInt(32.W))
  val brPayloadOwner = Reg(Vec(32, UInt(2.W)))

  // 动态异常（位 4..5，2b）
  val dynamicExcpBank = Seq.fill(2)(Mem(ROB_SIZE / 2, UInt(EXCP_NUM.W)))
  val dynamicExcpValid = RegInit(VecInit(Seq.fill(ROB_SIZE)(false.B)))
  val staticExcpBank = Seq.fill(2)(Mem(ROB_SIZE / 2, UInt(EXCP_NUM.W)))
  val staticExcpSeen = Seq.fill(2)(RegInit(VecInit(Seq.fill(ROB_SIZE / 2)(false.B))))

  // FTQ 头前递寄存器
  val headFtq0StayQ = RegInit(0.U(FTQ_W.W)); val headFtq1StayQ = RegInit(0.U(FTQ_W.W))
  val headFtq0AdvQ = RegInit(0.U(FTQ_W.W)); val headFtq1AdvQ = RegInit(0.U(FTQ_W.W))
  val headFtqAdvSelQ = RegInit(false.B)
  val headFtq0Q = Mux(headFtqAdvSelQ, headFtq0AdvQ, headFtq0StayQ)
  val headFtq1Q = Mux(headFtqAdvSelQ, headFtq1AdvQ, headFtq1StayQ)

  // ---------------- 分配索引 / 满判据 ----------------
  val alloc2Pair = tail + 1.U
  val alloc0Idx = Mux(tailHalf, Cat(1.U(1.W), tail), Cat(0.U(1.W), tail))
  val alloc1Idx = Mux(tailHalf, Cat(0.U(1.W), alloc2Pair), Cat(1.U(1.W), tail))
  val allocationTags = Seq(alloc0Idx, alloc1Idx)
  for (i <- 0 until 2) {
    registerFile.io.clear(i) := io.allocEn && io.a(i).valid && !io.flush
    registerFile.io.allocate(i) := io.allocEn && io.a(i).valid && io.a(i).rfWe &&
      io.a(i).rd =/= 0.U && !io.flush
    registerFile.io.allocateTag(i) := allocationTags(i)
  }
  for (i <- 0 until 2) {
    when(io.allocEn && io.a(i).valid && !io.flush) {
      dynamicExcpValid(allocationTags(i)) := false.B
    }
  }
  for (bank <- 0 until 2) {
    val fromSlot0 = allocationTags(0)(ROB_W - 1) === bank.U
    val writeEnable = io.allocEn && !io.flush && Mux(fromSlot0, io.a(0).valid, io.a(1).valid)
    val writeAddress = Mux(fromSlot0, allocationTags(0)(PW - 1, 0), allocationTags(1)(PW - 1, 0))
    val writeData = Mux(fromSlot0, io.a(0).excp, io.a(1).excp)
    when(writeEnable) {
      staticExcpBank(bank)(writeAddress) := writeData
      staticExcpSeen(bank)(writeAddress) := true.B
    }
  }
  val head0Idx = Cat(0.U(1.W), head)
  val head1Idx = Cat(1.U(1.W), head)
  val dynamicException0 = Mux(dynamicExcpValid(head0Idx), dynamicExcpBank(0)(head), 0.U(EXCP_NUM.W))
  val dynamicException1 = Mux(dynamicExcpValid(head1Idx), dynamicExcpBank(1)(head), 0.U(EXCP_NUM.W))
  if (!sys.props.get("e91c.synthesis").contains("true")) {
    val oldDynamicException = RegInit(VecInit(Seq.fill(ROB_SIZE)(0.U(EXCP_NUM.W))))
    for (i <- 0 until 2) {
      when(io.allocEn && io.a(i).valid && !io.flush) { oldDynamicException(allocationTags(i)) := 0.U }
    }
    when(reset.asBool || io.flush) { oldDynamicException.foreach(_ := 0.U) }
      .otherwise {
        when(io.memFwd.valid) { oldDynamicException(io.memFwd.robid) := io.memFwd.excp }
        when(io.mem2Wb.valid) { oldDynamicException(io.mem2Wb.robid) := 0.U }
      }
    val checkArmed = RegNext(true.B, false.B)
    when(checkArmed) {
      assert(dynamicException0 === oldDynamicException(head0Idx), "ROB dynamic even exception mismatch")
      assert(dynamicException1 === oldDynamicException(head1Idx), "ROB dynamic odd exception mismatch")
    }
  }
  val staticException0 = Mux(staticExcpSeen(0)(head), staticExcpBank(0)(head), 0.U(EXCP_NUM.W))
  val staticException1 = Mux(staticExcpSeen(1)(head), staticExcpBank(1)(head), 0.U(EXCP_NUM.W))
  if (!sys.props.get("e91c.synthesis").contains("true")) {
    val oldStaticException = RegInit(VecInit(Seq.fill(ROB_SIZE)(0.U(EXCP_NUM.W))))
    for (i <- 0 until 2) {
      when(io.allocEn && io.a(i).valid && !io.flush) { oldStaticException(allocationTags(i)) := io.a(i).excp }
    }
    val checkArmed = RegNext(true.B, false.B)
    when(checkArmed) {
      assert(staticException0 === oldStaticException(head0Idx), "ROB static exception even mismatch")
      assert(staticException1 === oldStaticException(head1Idx), "ROB static exception odd mismatch")
    }
  }

  val robFullMark = tail + ROB_GUARD.U
  val robFull = head === robFullMark
  val robEmpty = (head === tail) && !tailHalf

  io.robTail := tail; io.robTailHalf := tailHalf
  io.robFull := robFull
  io.robEmpty := robEmpty
  io.headRobid0 := head0Idx

  // Two allocation lanes write opposite parity banks, even across a pair
  // boundary. Splitting each parity bank again wastes small LUTRAM rows and
  // adds a wide read mux; each parity needs only one selected write port.
  private val STA_W = 75
  val staEven = Mem(ROB_SIZE / 2, UInt(STA_W.W))
  val staOdd = Mem(ROB_SIZE / 2, UInt(STA_W.W))
  val staWrtEven = RegInit(VecInit(Seq.fill(ROB_SIZE / 2)(false.B)))
  val staWrtOdd = RegInit(VecInit(Seq.fill(ROB_SIZE / 2)(false.B)))

  def staPack(k: Int): UInt = {
    val a = io.a(k)
    val isJal = a.inst(6, 0) === "b1101111".U
    val staticAny = a.excp.orR
    val dynEn = a.isLoad || a.isStore
    val hasPriv = a.privVec.orR
    Cat(a.pc(1, 0), hasPriv, dynEn, staticAny, a.excp(3, 0), a.csrNum(11, 0), a.privVec, a.ftqId,
      a.isLast, a.predTaken, a.brType, a.isBranch, a.isStore, a.isLoad, a.rd, a.rfWe,
      isJal, a.pc(31, 2))
  }
  val staPackV = VecInit((0 until 2).map(staPack))

  val resetB = reset.asBool
  val allocFire = !resetB && !io.flush && io.allocEn && !robFull

  val evenTailWe = allocFire && !tailHalf
  val evenNextWe = allocFire && (tailHalf && io.a(1).valid)
  val evenWriteAddress = Mux(tailHalf, alloc2Pair, tail)
  val evenWriteData = Mux(tailHalf, staPackV(1), staPackV(0))

  val oddTailWe = allocFire && ((!tailHalf && io.a(1).valid) || tailHalf)
  val oddTailWdata = Mux(tailHalf, staPackV(0), staPackV(1))
  when(evenTailWe || evenNextWe) {
    staEven.write(evenWriteAddress, evenWriteData)
    staWrtEven(evenWriteAddress) := true.B
  }
  when(oddTailWe) {
    staOdd.write(tail, oddTailWdata)
    staWrtOdd(tail) := true.B
  }

  val staH0Defined = staWrtEven(headStaticEvenQ)
  val staH1Defined = staWrtOdd(headStaticOddQ)
  val staH0 = staEven(headStaticEvenQ)
  val staH1 = staOdd(headStaticOddQ)

  // ---------------- 提交推进 / FTQ 前递 ----------------
  val headPopAdvance = io.cmtPop && !(allocFire && tailHalf && (head === tail))
  val headPopNext = head + 1.U
  val headWillAdvance = headPopAdvance
  val headAdvancePair = head + 1.U
  val staAdvance0 = staEven(headAdvancePair)
  val staAdvance1 = staOdd(headAdvancePair)

  if (!sys.props.get("e91c.synthesis").contains("true")) {
    val reference = Reg(Vec(ROB_SIZE, UInt(STA_W.W)))
    val seen = RegInit(VecInit(Seq.fill(ROB_SIZE)(false.B)))
    when(evenTailWe || evenNextWe) {
      reference(Cat(0.U(1.W), evenWriteAddress)) := evenWriteData
      seen(Cat(0.U(1.W), evenWriteAddress)) := true.B
    }
    when(oddTailWe) {
      reference(Cat(1.U(1.W), tail)) := oddTailWdata
      seen(Cat(1.U(1.W), tail)) := true.B
    }
    for ((address, data) <- Seq(
      (Cat(0.U(1.W), headStaticEvenQ), staH0),
      (Cat(1.U(1.W), headStaticOddQ), staH1),
      (Cat(0.U(1.W), headAdvancePair), staAdvance0),
      (Cat(1.U(1.W), headAdvancePair), staAdvance1))) {
      when(seen(address)) { assert(data === reference(address), "ROB static bank read mismatch") }
    }
    assert(!(evenTailWe && evenNextWe), "even static bank has two writers")
  }

  val ftqAlloc0Avail = tailHalf || !robFull
  val ftqAlloc1Avail = !robFull

  val stayFtq0FwdA0 = ftqAlloc0Avail && !tailHalf && (head === tail)
  val stayFtq0FwdA1 = ftqAlloc1Avail && tailHalf && io.a(1).valid && (head === alloc2Pair)
  val stayFtq1FwdA1 = ftqAlloc1Avail && !tailHalf && io.a(1).valid && (head === tail)
  val stayFtq1FwdA0 = ftqAlloc0Avail && tailHalf && (head === tail)
  val advFtq0FwdA0 = ftqAlloc0Avail && !tailHalf && (headAdvancePair === tail)
  val advFtq0FwdA1 = ftqAlloc1Avail && tailHalf && io.a(1).valid && (headAdvancePair === alloc2Pair)
  val advFtq1FwdA1 = ftqAlloc1Avail && !tailHalf && io.a(1).valid && (headAdvancePair === tail)
  val advFtq1FwdA0 = ftqAlloc0Avail && tailHalf && (headAdvancePair === tail)

  val headFtq0StayNext = Mux(stayFtq0FwdA0, io.a(0).ftqId,
    Mux(stayFtq0FwdA1, io.a(1).ftqId, staH0(47, 44)))
  val headFtq1StayNext = Mux(stayFtq1FwdA1, io.a(1).ftqId,
    Mux(stayFtq1FwdA0, io.a(0).ftqId, staH1(47, 44)))
  val headFtq0AdvNext = Mux(advFtq0FwdA0, io.a(0).ftqId,
    Mux(advFtq0FwdA1, io.a(1).ftqId, staAdvance0(47, 44)))
  val headFtq1AdvNext = Mux(advFtq1FwdA1, io.a(1).ftqId,
    Mux(advFtq1FwdA0, io.a(0).ftqId, staAdvance1(47, 44)))

  // ---------------- 静态完成判定 ----------------
  def staField(sta: UInt, hi: Int, lo: Int) = sta(hi, lo)
  val cmt0StaticExcp = staH0(70)
  val cmt1StaticExcp = staH1(70)
  val cmt0Barrier = staH0(48 + PrivType.FENCE)
  val cmt1Barrier = staH1(48 + PrivType.FENCE)
  val cmt0NoSide = !staH0(31) && !staH0(37) && !staH0(38) && !staH0(39) && !staH0(72)
  val cmt1NoSide = !staH1(31) && !staH1(37) && !staH1(38) && !staH1(39) && !staH1(72)
  val cmt0StaticDone = cmt0StaticExcp || cmt0Barrier || cmt0NoSide
  val cmt1StaticDone = cmt1StaticExcp || cmt1Barrier || cmt1NoSide


  // Stored-data ports deliberately exclude execution forwarding; the existing
  // ROB views below retain their separate full and NoAlu bypass networks.
  private var resultReadPort = 0
  def resultView(addr: UInt): UInt = {
    val port = resultReadPort
    resultReadPort += 1
    require(port < 7)
    registerFile.io.tagRead(port) := addr
    registerFile.io.tagData(port)
  }
  val resultViewC0 = resultView(head0Idx); val resultViewC1 = resultView(head1Idx)
  val resultViewR = VecInit((0 until 4).map(k => resultView(io.raddr(k))))
  def completeAt(idx: UInt) = Mux(idx(ROB_W - 1), completeOdd(idx(PW - 1, 0)), completeEven(idx(PW - 1, 0)))
  val baseProbeStoredReady = VecInit((0 until 2).map { p =>
    completeAt(io.baseProbeRobid(p)) ||
      (memShadowValid && memShadowRobid === io.baseProbeRobid(p))
  })
  val baseProbeRr = RegInit(false.B)
  val baseProbeChoose1 = baseProbeStoredReady(1) && (!baseProbeStoredReady(0) || baseProbeRr)
  val baseProbeReadAddr = Mux(baseProbeChoose1, io.baseProbeRobid(1), io.baseProbeRobid(0))
  val resultViewBp = resultView(baseProbeReadAddr)
  when(io.flush) {
    baseProbeRr := false.B
  }.elsewhen(baseProbeStoredReady.asUInt.andR &&
    io.baseProbeRobid(0) =/= io.baseProbeRobid(1)) {
    baseProbeRr := ~baseProbeRr
  }
  // A load may become commit-eligible on its forwarding cycle.  Preserve the
  // existing commit-result bypass when materializing architectural state.
  registerFile.io.retireData := VecInit(
    Mux(io.memFwd.valid && io.memFwd.robid === head0Idx, io.memFwd.data, resultViewC0),
    Mux(io.memFwd.valid && io.memFwd.robid === head1Idx, io.memFwd.data, resultViewC1))

  // mem 视图
  def memView(addr: UInt): UInt = {
    val m2 = memPayloadMem2(addr)
    Mux(memPayloadOwner(addr),
      Cat(0.U(1.W), m2(66, 64), 0.U(4.W), m2(63, 32), m2(31, 0)),   // mem2: size@66:64
      memPayloadFwd(addr))
  }
  val memViewC0 = memView(head0Idx); val memViewC1 = memView(head1Idx)

  // 分支视图
  def brView(addr: UInt): UInt = {
    val ow = brPayloadOwner(addr)
    Mux(ow === 0.U, brPayloadAlu0(addr),
      Mux(ow === 1.U, brPayloadAlu1(addr), 0.U))
  }
  val brViewC0 = brView(head0Idx); val brViewC1 = brView(head1Idx)

  // ---------------- dispatch 读口 ----------------
  for (p <- 0 until 4) {
    val ra = io.raddr(p)
    val wbhit = (io.alu(0).valid && io.alu(0).robid === ra) ||
      (io.alu(1).valid && io.alu(1).robid === ra) ||
      (io.memFwd.valid && io.memFwd.robid === ra) ||
      (io.mem2Wb.valid && io.mem2Wb.robid === ra) ||
      (io.mduWb.valid && io.mduWb.robid === ra)
    val wbdat = Mux(io.alu(0).valid && io.alu(0).robid === ra, io.alu(0).data,
      Mux(io.alu(1).valid && io.alu(1).robid === ra, io.alu(1).data,
      Mux(io.memFwd.valid && io.memFwd.robid === ra, io.memFwd.data,
      Mux(io.mem2Wb.valid && io.mem2Wb.robid === ra, io.mem2Wb.data,
      Mux(io.mduWb.valid && io.mduWb.robid === ra, io.mduWb.data, 0.U)))))
    val shadowHit = memShadowValid && (memShadowRobid === ra)
    io.rrdy(p) := completeAt(ra) | shadowHit | wbhit
    io.rdata(p) := Mux(wbhit, wbdat, resultViewR(p))
  }
  for (p <- 0 until 2) {
    val k = p * 2   // 口 0/2/4
    val ra = io.raddr(k)
    val wbhit = (io.memFwd.valid && io.memFwd.robid === ra) ||
      (io.mem2Wb.valid && io.mem2Wb.robid === ra) ||
      (io.mduWb.valid && io.mduWb.robid === ra)
    val wbdat = Mux(io.memFwd.valid && io.memFwd.robid === ra, io.memFwd.data,
      Mux(io.mem2Wb.valid && io.mem2Wb.robid === ra, io.mem2Wb.data,
      Mux(io.mduWb.valid && io.mduWb.robid === ra, io.mduWb.data, 0.U)))
    io.rdataNoAlu(p) := Mux(wbhit, wbdat, resultViewR(k))
  }

  // ---------------- LSU base 探测 ----------------
  for (p <- 0 until 2) {
    val ra = io.baseProbeRobid(p)
    val comp = completeAt(ra)
    val shadow = memShadowValid && (memShadowRobid === ra)
    val fwd = io.memFwd.valid && (io.memFwd.robid === ra)
    val fwd2 = io.mem2Wb.valid && (io.mem2Wb.robid === ra)
    val selected = if (p == 0) !baseProbeChoose1 else baseProbeChoose1
    val sharedTag = io.baseProbeRobid(0) === io.baseProbeRobid(1)
    io.baseProbeReady(p) := fwd || fwd2 || ((comp || shadow) && (selected || sharedTag))
    io.baseProbeData(p) := Mux(fwd, io.memFwd.data, Mux(fwd2, io.mem2Wb.data, resultViewBp))
  }

  if (!sys.props.get("e91c.synthesis").contains("true")) {
    when(baseProbeStoredReady.asUInt.andR &&
      io.baseProbeRobid(0) =/= io.baseProbeRobid(1) &&
      !io.memFwd.valid && !io.mem2Wb.valid) {
      assert(io.baseProbeReady.asUInt.xorR,
        "two distinct stored LSU base probes must grant exactly one shared read")
    }
    when(baseProbeStoredReady.asUInt.andR &&
      io.baseProbeRobid(0) === io.baseProbeRobid(1)) {
      assert(io.baseProbeReady.asUInt.andR,
        "identical LSU base-probe tags must share the stored result")
    }
  }

  // ---------------- 提交口 ----------------
  io.cmtValid(0) := validA(head0Idx)
  io.cmtIsJal(0) := false.B   // 原 RTL 槽 0 无 is_jal 输出
  // 静态完成：未写槽（golden X）视为 0；陈旧已写槽按真值求值
  io.cmtComplete(0) := completeEven(head) ||
    (memShadowValid && (memShadowRobid === head0Idx)) || (staH0Defined && cmt0StaticDone)
  io.cmtPc(0) := Cat(staH0(29, 0), staH0(74, 73))
  io.cmtRfWe(0) := staH0(31)
  io.cmtRd(0) := staH0(36, 32)
  val cmt0FwdHit = io.memFwd.valid && (io.memFwd.robid === head0Idx)
  val cmt1FwdHit = io.memFwd.valid && (io.memFwd.robid === head1Idx)
  io.cmtResult(0) := Mux(cmt0FwdHit, io.memFwd.data, resultViewC0)
  io.cmtStoreData(0) := Mux(cmt0FwdHit, io.memFwd.storeData, storeData(head0Idx))
  io.cmtResult2(0) := result2Mdu(head0Idx)
  io.cmtIsLoad(0) := staH0(37)
  io.cmtIsStore(0) := staH0(38)
  io.cmtPaddr(0) := memViewC0(31, 0)
  io.cmtVaddr(0) := memViewC0(63, 32)
  io.cmtWstrb(0) := memViewC0(67, 64)
  io.cmtSize(0) := memViewC0(70, 68)
  io.cmtUncached(0) := memViewC0(71)
  io.cmtIsBranch(0) := staH0(39)
  io.cmtBrType(0) := staH0(41, 40)
  io.cmtPredTaken(0) := staH0(42)
  io.cmtBrTaken(0) := brViewC0(0)
  io.cmtBrTarget(0) := Cat(brViewC0(31, 1), 0.U(1.W))
  io.cmtIsLast(0) := staH0(43)
  io.cmtFtqId(0) := headFtq0Q
  io.cmtPrivVec(0) := staH0(53, 48)
  io.cmtCsrNum(0) := staH0(65, 54)
  io.cmtExcp(0) := staticException0 | dynamicException0
  io.cmtHasExcpFast(0) := staH0(70) || (staH0(71) && dynamicException0.orR)
  io.cmtHasPrivFast(0) := staH0(72)

  io.cmtValid(1) := validA(head1Idx)
  io.cmtComplete(1) := completeOdd(head) ||
    (memShadowValid && (memShadowRobid === head1Idx)) || (staH1Defined && cmt1StaticDone)
  io.cmtPc(1) := Cat(staH1(29, 0), staH1(74, 73))
  io.cmtIsJal(1) := staH1(30)
  io.cmtRfWe(1) := staH1(31)
  io.cmtRd(1) := staH1(36, 32)
  io.cmtResult(1) := Mux(cmt1FwdHit, io.memFwd.data, resultViewC1)
  io.cmtStoreData(1) := Mux(cmt1FwdHit, io.memFwd.storeData, storeData(head1Idx))
  io.cmtResult2(1) := result2Mdu(head1Idx)
  io.cmtIsLoad(1) := staH1(37)
  io.cmtIsStore(1) := staH1(38)
  io.cmtPaddr(1) := memViewC1(31, 0)
  io.cmtVaddr(1) := memViewC1(63, 32)
  io.cmtWstrb(1) := memViewC1(67, 64)
  io.cmtSize(1) := memViewC1(70, 68)
  io.cmtUncached(1) := memViewC1(71)
  io.cmtIsBranch(1) := staH1(39)
  io.cmtBrType(1) := staH1(41, 40)
  io.cmtPredTaken(1) := staH1(42)
  io.cmtBrTaken(1) := brViewC1(0)
  io.cmtBrTarget(1) := Cat(brViewC1(31, 1), 0.U(1.W))
  io.cmtIsLast(1) := staH1(43)
  io.cmtFtqId(1) := headFtq1Q
  io.cmtPrivVec(1) := staH1(53, 48)
  io.cmtCsrNum(1) := staH1(65, 54)
  io.cmtExcp(1) := staticException1 | dynamicException1
  io.cmtHasExcpFast(1) := staH1(70) || (staH1(71) && dynamicException1.orR)
  io.cmtHasPrivFast(1) := staH1(72)

  // ---------------- 宽负载 bank 写（各自单源）----------------
  when(!resetB && !io.flush) {
    when(io.alu(0).valid) {

      brPayloadAlu0(io.alu(0).robid) := Cat(io.alu(0).brTarget(31, 1), io.alu(0).brTaken)
    }
    when(io.alu(1).valid) {

      brPayloadAlu1(io.alu(1).robid) := Cat(io.alu(1).brTarget(31, 1), io.alu(1).brTaken)
    }

    when(io.memFwd.valid) {
      storeData(io.memFwd.robid) := io.memFwd.storeData
      memPayloadFwd(io.memFwd.robid) := Cat(io.memFwd.uncached, io.memFwd.size,
        io.memFwd.wstrb, io.memFwd.vaddr, io.memFwd.paddr)
    }
    when(io.mem2Wb.valid) {

      memPayloadMem2(io.mem2Wb.robid) := Cat(io.mem2Wb.size, io.mem2Wb.vaddr, io.mem2Wb.paddr)
    }
    when(io.mduWb.valid) {

      result2Mdu(io.mduWb.robid) := io.mduWb.data2
    }
  }

  // ---------------- FTQ 头寄存器 ----------------
  when(io.flush) {
    headFtq0StayQ := 0.U; headFtq1StayQ := 0.U
    headFtq0AdvQ := 0.U; headFtq1AdvQ := 0.U
    headFtqAdvSelQ := false.B
  }.otherwise {
    headFtq0StayQ := headFtq0StayNext
    headFtq1StayQ := headFtq1StayNext
    headFtq0AdvQ := headFtq0AdvNext
    headFtq1AdvQ := headFtq1AdvNext
    headFtqAdvSelQ := headWillAdvance
  }

  // ---------------- 主状态机 ----------------
  when(io.flush) {
    head := 0.U; headStaticEvenQ := 0.U; headStaticOddQ := 0.U
    tail := 0.U; tailHalf := false.B
    memShadowValid := false.B; memShadowRobid := 0.U
    for (i <- 0 until 32) { validA(i) := false.B; dynamicExcpValid(i) := false.B }
    for (i <- 0 until 16) { completeEven(i) := false.B; completeOdd(i) := false.B }
  }.otherwise {
    memShadowValid := io.memWb.valid
    memShadowRobid := io.memWb.robid

    when(io.cmtClear0) { validA(head0Idx) := false.B }
    when(io.cmtClear1) { validA(head1Idx) := false.B }

    when(io.cmtPop) {
      when(headPopAdvance) {
        head := headPopNext
        headStaticEvenQ := headPopNext
        headStaticOddQ := headPopNext
      }
      when(!allocFire && tailHalf && (head === tail)) {
        tail := tail + 1.U
        tailHalf := false.B
      }
    }

    when(tailHalf || !robFull) { brPayloadOwner(alloc0Idx) := 3.U }
    when(!robFull) { brPayloadOwner(alloc1Idx) := 3.U }

    when(allocFire) {
      validA(alloc0Idx) := io.a(0).valid
      when(alloc0Idx(ROB_W - 1)) { completeOdd(alloc0Idx(PW - 1, 0)) := false.B }
        .otherwise { completeEven(alloc0Idx(PW - 1, 0)) := false.B }
      when(io.a(1).valid) {
        validA(alloc1Idx) := true.B
        when(alloc1Idx(ROB_W - 1)) { completeOdd(alloc1Idx(PW - 1, 0)) := false.B }
          .otherwise { completeEven(alloc1Idx(PW - 1, 0)) := false.B }
      }

      when(io.a(1).valid) {
        tail := tail + 1.U
      }.otherwise {
        tail := tail + Mux(tailHalf, 1.U, 0.U)
        tailHalf := ~tailHalf
      }
    }

    when(io.alu(0).valid) {

      brPayloadOwner(io.alu(0).robid) := 0.U
      when(io.alu(0).robid(ROB_W - 1)) { completeOdd(io.alu(0).robid(PW - 1, 0)) := true.B }
        .otherwise { completeEven(io.alu(0).robid(PW - 1, 0)) := true.B }
    }
    when(io.alu(1).valid) {

      brPayloadOwner(io.alu(1).robid) := 1.U
      when(io.alu(1).robid(ROB_W - 1)) { completeOdd(io.alu(1).robid(PW - 1, 0)) := true.B }
        .otherwise { completeEven(io.alu(1).robid(PW - 1, 0)) := true.B }
    }

    when(io.memFwd.valid) {
      when(io.memFwd.robid(ROB_W - 1)) { completeOdd(io.memFwd.robid(PW - 1, 0)) := true.B }
        .otherwise { completeEven(io.memFwd.robid(PW - 1, 0)) := true.B }

      memPayloadOwner(io.memFwd.robid) := false.B
      dynamicExcpValid(io.memFwd.robid) := true.B
      for (bank <- 0 until 2) when(io.memFwd.robid(ROB_W - 1) === bank.U) {
        dynamicExcpBank(bank)(io.memFwd.robid(PW - 1, 0)) := io.memFwd.excp
      }
    }
    when(io.mem2Wb.valid) {

      memPayloadOwner(io.mem2Wb.robid) := true.B
      dynamicExcpValid(io.mem2Wb.robid) := false.B
      when(io.mem2Wb.robid(ROB_W - 1)) { completeOdd(io.mem2Wb.robid(PW - 1, 0)) := true.B }
        .otherwise { completeEven(io.mem2Wb.robid(PW - 1, 0)) := true.B }
    }
    when(io.mduWb.valid) {

      when(io.mduWb.robid(ROB_W - 1)) { completeOdd(io.mduWb.robid(PW - 1, 0)) := true.B }
        .otherwise { completeEven(io.mduWb.robid(PW - 1, 0)) := true.B }
    }
  }
}




