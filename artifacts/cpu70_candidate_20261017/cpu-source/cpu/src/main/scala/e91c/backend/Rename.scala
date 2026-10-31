// Rename: RAT lookup + ARF read + paired ROB allocation + dispatch pipeline regs.
// Ported from cpu/rename.v. Key semantics preserved:
// - no_exec elimination (static excp / FENCE / no-side-effect stay in ROB only)
// - L0 CSR serialization drain (l0_csr_drain_r gates rename until ROB empty)
// - paired allocation with tail_half parity; slot2 needs !rob_full2, MEM<=2, MDU<=1
// - same-cycle RAW bypass to the producing slot's new robid (ready=0)
// - null bubble (inst==0, no excp) clears excp and sets is_nop
// - residency wakeup from ROB by producer tag when can_go=0; fire clears valid
package e91c.backend

import chisel3._
import chisel3.util.Cat
import e91c.config.Params._
import e91c.config.{AluOpG, BrOp, FuType, MemOp, PrivType}

class Rename extends Module {
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val recoveryStall = Input(Bool())
    val recoveryRedirect = Input(Bool())
    val robEmpty = Input(Bool())
    val ibValid = Input(Vec(2, Bool()))
    val ibPc = Input(Vec(2, UInt(32.W)))
    val ibInst = Input(Vec(2, UInt(32.W)))
    val ibPredTaken = Input(Vec(2, Bool()))
    val ibIsLast = Input(Vec(2, Bool()))
    val ibFtqId = Input(Vec(2, UInt(FTQ_W.W)))
    val ibExcp = Input(Vec(2, UInt(EXCP_NUM.W)))
    val ibFutype = Input(Vec(2, UInt(FU_NUM.W)))
    val ibAluOp = Input(Vec(2, UInt(AluOpG.NUM.W)))
    val ibBrOp = Input(Vec(2, UInt(BrOp.NUM.W)))
    val ibMemOp = Input(Vec(2, UInt(MemOp.NUM.W)))
    val ibCsrOp = Input(Vec(2, UInt(3.W)))
    val ibCsrNum = Input(Vec(2, UInt(12.W)))
    val ibSrc0Addr = Input(Vec(2, UInt(5.W)))
    val ibSrc1Addr = Input(Vec(2, UInt(5.W)))
    val ibUseSrc0 = Input(Vec(2, Bool()))
    val ibUseSrc1 = Input(Vec(2, Bool()))
    val ibRdAddr = Input(Vec(2, UInt(5.W)))
    val ibRfWe = Input(Vec(2, Bool()))
    val ibImm = Input(Vec(2, UInt(32.W)))
    val ibUseImm = Input(Vec(2, Bool()))
    val ibBrOffs = Input(Vec(2, UInt(32.W)))
    val ibIsBranch = Input(Vec(2, Bool()))
    val ibBrType = Input(Vec(2, UInt(BR_TYPE_W.W)))
    val ibPrivVec = Input(Vec(2, UInt(PRIV_NUM.W)))
    val ibIsNop = Input(Vec(2, Bool()))
    val ibIsLoad = Input(Vec(2, Bool()))
    val ibIsStore = Input(Vec(2, Bool()))
    val ibReady = Output(Vec(2, Bool()))
    val ratRaddr = Output(Vec(4, UInt(5.W)))
    val ratRbusy = Input(Vec(4, Bool()))
    val ratRnum = Input(Vec(4, UInt(ROB_W.W)))
    val ratWen = Output(Vec(2, Bool()))
    val ratWaddr = Output(Vec(2, UInt(5.W)))
    val ratWnum = Output(Vec(2, UInt(ROB_W.W)))
    val arfRaddr = Output(Vec(4, UInt(5.W)))
    val arfRdata = Input(Vec(4, UInt(32.W)))
    val robAllocEn = Output(Bool())
    val robTail = Input(UInt(ROB_PAIR_W.W))
    val robFull = Input(Bool())
    val robTailHalf = Input(Bool())
    val robAValid = Output(Vec(2, Bool()))
    val robAPc = Output(Vec(2, UInt(32.W)))
    val robAInst = Output(Vec(2, UInt(32.W)))
    val robARfWe = Output(Vec(2, Bool()))
    val robARd = Output(Vec(2, UInt(5.W)))
    val robAIsLoad = Output(Vec(2, Bool()))
    val robAIsStore = Output(Vec(2, Bool()))
    val robAIsBranch = Output(Vec(2, Bool()))
    val robABrType = Output(Vec(2, UInt(BR_TYPE_W.W)))
    val robAPredTaken = Output(Vec(2, Bool()))
    val robAIsLast = Output(Vec(2, Bool()))
    val robAFtqId = Output(Vec(2, UInt(FTQ_W.W)))
    val robAPrivVec = Output(Vec(2, UInt(PRIV_NUM.W)))
    val robACsrNum = Output(Vec(2, UInt(12.W)))
    val robAExcp = Output(Vec(2, UInt(EXCP_NUM.W)))
    val robAIsNop = Output(Vec(2, Bool()))
    val dispatchReady = Input(Bool())
    val disFire = Input(Vec(2, Bool()))
    val robRrdy = Input(Vec(4, Bool()))
    val robRdata = Input(Vec(4, UInt(32.W)))
    val disValid = Output(Vec(2, Bool()))
    val disRobid = Output(Vec(2, UInt(ROB_W.W)))
    val disPc = Output(Vec(2, UInt(32.W)))
    val disFutype = Output(Vec(2, UInt(FU_NUM.W)))
    val disAluOp = Output(Vec(2, UInt(AluOpG.NUM.W)))
    val disBrOp = Output(Vec(2, UInt(BrOp.NUM.W)))
    val disMemOp = Output(Vec(2, UInt(MemOp.NUM.W)))
    val disCsrOp = Output(Vec(2, UInt(3.W)))
    val disCsrNum = Output(Vec(2, UInt(12.W)))
    val disSrc0Ready = Output(Vec(2, Bool()))
    val disSrc0Val = Output(Vec(2, UInt(32.W)))
    val disSrc0Robid = Output(Vec(2, UInt(ROB_W.W)))
    val disSrc1Ready = Output(Vec(2, Bool()))
    val disSrc1Val = Output(Vec(2, UInt(32.W)))
    val disSrc1Robid = Output(Vec(2, UInt(ROB_W.W)))
    val disImm = Output(Vec(2, UInt(32.W)))
    val disUseImm = Output(Vec(2, Bool()))
    val disBrOffs = Output(Vec(2, UInt(32.W)))
    val disPredTaken = Output(Vec(2, Bool()))
    val disFtqId = Output(Vec(2, UInt(FTQ_W.W)))
  })

  import io._

  val staticExcp = Wire(Vec(2, Bool()))
  val barrier = Wire(Vec(2, Bool()))
  val noSideEffect = Wire(Vec(2, Bool()))
  val noExec = Wire(Vec(2, Bool()))
  val effV = Wire(Vec(2, Bool()))
  val l0CsrWr = Wire(Vec(2, Bool()))
  val l0CsrClass = Wire(Vec(2, Bool()))
  for (i <- 0 until 2) {
    staticExcp(i) := ibExcp(i).orR
    barrier(i) := ibPrivVec(i)(PrivType.FENCE)
    noSideEffect(i) := !ibRfWe(i) && !ibIsLoad(i) && !ibIsStore(i) &&
                       !ibIsBranch(i) && !ibPrivVec(i).orR
    noExec(i) := staticExcp(i) || barrier(i) || noSideEffect(i)
    effV(i) := ibValid(i) && !noExec(i)
    val csrCls = ibPrivVec(i)(PrivType.CSR_WR) || ibPrivVec(i)(PrivType.CSR_SERIAL)
    // CSR class already implies a side effect; keep exception and FENCE guards.
    l0CsrWr(i) := ibValid(i) && !staticExcp(i) && !barrier(i) && csrCls
    l0CsrClass(i) := ibValid(i) && csrCls
  }
  val csrSerializeEmptyOk = !(l0CsrClass(0) || l0CsrClass(1)) || robEmpty
  val l0CsrDrainR = RegInit(false.B)

  val bothSlotsValid = ibValid(0) && ibValid(1)
  val dualIssueOk = !((bothSlotsValid && ibFutype(0)(FuType.MDU) && ibFutype(1)(FuType.MDU)) ||
                      (l0CsrClass(0) && ibValid(1)) ||
                      (l0CsrClass(1) && ibValid(0)))
  val canGo = Wire(Bool())
  val takeSlot1 = canGo && ibValid(1) && dualIssueOk && !robFull

  canGo := (ibValid(0) || ibValid(1)) && !robFull && dispatchReady &&
           !flush && !recoveryStall && !l0CsrDrainR && csrSerializeEmptyOk
  ibReady(0) := canGo && ibValid(0)
  ibReady(1) := takeSlot1
  robAllocEn := canGo

  val l0CsrAlloc = canGo && (l0CsrWr(0) ||
    (l0CsrWr(1) && takeSlot1))
  when(reset.asBool || flush) { l0CsrDrainR := false.B }
    .elsewhen(l0CsrAlloc) { l0CsrDrainR := true.B }

  val nullBubble = Wire(Vec(2, Bool()))
  for (i <- 0 until 2) nullBubble(i) := ibValid(i) && (ibInst(i) === 0.U) && !ibExcp(i).orR

  val robTailNext = robTail + 1.U
  val robid0 = Mux(robTailHalf, Cat(1.U(1.W), robTail), Cat(0.U(1.W), robTail))
  val robid1 = Mux(robTailHalf, Cat(0.U(1.W), robTailNext), Cat(1.U(1.W), robTail))
  val robids = Seq(robid0, robid1)

  val ibWritesRf = Wire(Vec(2, Bool()))
  for (i <- 0 until 2) ibWritesRf(i) := ibValid(i) && ibRfWe(i) && (ibRdAddr(i) =/= 0.U)

  for (i <- 0 until 2) {
    ratRaddr(i * 2) := ibSrc0Addr(i)
    ratRaddr(i * 2 + 1) := ibSrc1Addr(i)
    arfRaddr(i * 2) := ibSrc0Addr(i)
    arfRaddr(i * 2 + 1) := ibSrc1Addr(i)
  }

  def rawFrom(i: Int, j: Int, useSrc: Int): Bool =
    (if (useSrc == 0) ibUseSrc0(i) else ibUseSrc1(i)) && ibWritesRf(j) &&
    ((if (useSrc == 0) ibSrc0Addr(i) else ibSrc1Addr(i)) === ibRdAddr(j))

  val s0ReadyArr = Wire(Vec(2, Bool()))
  val s1ReadyArr = Wire(Vec(2, Bool()))
  val s0ValArr = Wire(Vec(2, UInt(32.W)))
  val s1ValArr = Wire(Vec(2, UInt(32.W)))
  val srcTagArr = Wire(Vec(4, UInt(ROB_W.W)))

  for (p <- 0 until 4) srcTagArr(p) := ratRnum(p)

  s0ReadyArr(0) := !ibUseSrc0(0) || !ratRbusy(0)
  s0ValArr(0) := Mux(ibUseSrc0(0), arfRdata(0), 0.U)
  s1ReadyArr(0) := !ibUseSrc1(0) || !ratRbusy(1)
  s1ValArr(0) := Mux(ibUseSrc1(0), arfRdata(1), 0.U)

  val r10 = rawFrom(1, 0, 0)
  val r11 = rawFrom(1, 0, 1)
  s0ReadyArr(1) := Mux(!ibUseSrc0(1), true.B, Mux(r10, false.B, !ratRbusy(2)))
  s0ValArr(1) := Mux(ibUseSrc0(1), arfRdata(2), 0.U)
  srcTagArr(2) := Mux(r10, robid0, ratRnum(2))
  s1ReadyArr(1) := Mux(!ibUseSrc1(1), true.B, Mux(r11, false.B, !ratRbusy(3)))
  s1ValArr(1) := Mux(ibUseSrc1(1), arfRdata(3), 0.U)
  srcTagArr(3) := Mux(r11, robid0, ratRnum(3))

  val takeSlots = Seq(true.B, takeSlot1)
  for (i <- 0 until 2) {
    ratWen(i) := (if (i == 0) canGo else takeSlots(i)) && ibWritesRf(i)
    ratWaddr(i) := ibRdAddr(i)
    ratWnum(i) := robids(i)
  }

  for (i <- 0 until 2) {
    robAValid(i) := (if (i == 0) canGo && ibValid(i) else takeSlots(i) && ibValid(i))
    robAPc(i) := ibPc(i)
    robAInst(i) := ibInst(i)
    robARfWe(i) := ibRfWe(i)
    robARd(i) := ibRdAddr(i)
    robAIsLoad(i) := ibIsLoad(i)
    robAIsStore(i) := ibIsStore(i)
    robAIsBranch(i) := ibIsBranch(i)
    robABrType(i) := ibBrType(i)
    robAPredTaken(i) := ibPredTaken(i)
    robAIsLast(i) := ibIsLast(i)
    robAFtqId(i) := ibFtqId(i)
    robAPrivVec(i) := ibPrivVec(i)
    robACsrNum(i) := ibCsrNum(i)
    robAExcp(i) := Mux(nullBubble(i), 0.U, ibExcp(i))
    robAIsNop(i) := ibIsNop(i) || nullBubble(i)
  }

  val disValidR = Seq.fill(2)(RegInit(false.B))
  val disRobidR = Seq.fill(2)(Reg(UInt(ROB_W.W)))
  val disPcR = Seq.fill(2)(Reg(UInt(32.W)))
  val disFutypeR = Seq.fill(2)(Reg(UInt(FU_NUM.W)))
  val disAluOpR = Seq.fill(2)(Reg(UInt(AluOpG.NUM.W)))
  val disBrOpR = Seq.fill(2)(Reg(UInt(BrOp.NUM.W)))
  val disMemOpR = Seq.fill(2)(Reg(UInt(MemOp.NUM.W)))
  val disCsrOpR = Seq.fill(2)(Reg(UInt(3.W)))
  val disCsrNumR = Seq.fill(2)(Reg(UInt(12.W)))
  val disS0ReadyR = Seq.fill(2)(Reg(Bool()))
  val disS0ValR = Seq.fill(2)(Reg(UInt(32.W)))
  val disS0RobidR = Seq.fill(2)(Reg(UInt(ROB_W.W)))
  val disS1ReadyR = Seq.fill(2)(Reg(Bool()))
  val disS1ValR = Seq.fill(2)(Reg(UInt(32.W)))
  val disS1RobidR = Seq.fill(2)(Reg(UInt(ROB_W.W)))
  val disImmR = Seq.fill(2)(Reg(UInt(32.W)))
  val disUseImmR = Seq.fill(2)(Reg(Bool()))
  val disBrOffsR = Seq.fill(2)(Reg(UInt(32.W)))
  val disPredTakenR = Seq.fill(2)(Reg(Bool()))
  val disFtqIdR = Seq.fill(2)(Reg(UInt(FTQ_W.W)))
  val s0UseR = Seq.fill(2)(Reg(Bool()))
  val s1UseR = Seq.fill(2)(Reg(Bool()))

  when(reset.asBool || flush || recoveryRedirect) {
    for (i <- 0 until 2) disValidR(i) := false.B
  }.elsewhen(canGo) {
    for (i <- 0 until 2) {
      disValidR(i) := (if (i == 0) ibValid(i) && !noExec(i) else takeSlots(i) && !noExec(i))
      disRobidR(i) := robids(i)
      disPcR(i) := ibPc(i)
      disFutypeR(i) := ibFutype(i)
      disAluOpR(i) := ibAluOp(i)
      disBrOpR(i) := ibBrOp(i)
      disMemOpR(i) := ibMemOp(i)
      disCsrOpR(i) := ibCsrOp(i)
      disCsrNumR(i) := ibCsrNum(i)
      disS0ReadyR(i) := s0ReadyArr(i)
      disS0ValR(i) := s0ValArr(i)
      disS0RobidR(i) := srcTagArr(i * 2)
      disS1ReadyR(i) := s1ReadyArr(i)
      disS1ValR(i) := s1ValArr(i)
      disS1RobidR(i) := srcTagArr(i * 2 + 1)
      disImmR(i) := ibImm(i)
      disUseImmR(i) := ibUseImm(i)
      disBrOffsR(i) := ibBrOffs(i)
      disPredTakenR(i) := ibPredTaken(i)
      disFtqIdR(i) := ibFtqId(i)
      s0UseR(i) := ibUseSrc0(i)
      s1UseR(i) := ibUseSrc1(i)
    }
  }.otherwise {
    for (i <- 0 until 2) {
      when(disValidR(i) && s0UseR(i) && !disS0ReadyR(i) && robRrdy(i * 2)) {
        disS0ReadyR(i) := true.B
        disS0ValR(i) := robRdata(i * 2)
      }
      when(disValidR(i) && s1UseR(i) && !disS1ReadyR(i) && robRrdy(i * 2 + 1)) {
        disS1ReadyR(i) := true.B
        disS1ValR(i) := robRdata(i * 2 + 1)
      }
      when(disFire(i)) { disValidR(i) := false.B }
    }
  }

  for (i <- 0 until 2) {
    disValid(i) := disValidR(i)
    disRobid(i) := disRobidR(i)
    disPc(i) := disPcR(i)
    disFutype(i) := disFutypeR(i)
    disAluOp(i) := disAluOpR(i)
    disBrOp(i) := disBrOpR(i)
    disMemOp(i) := disMemOpR(i)
    disCsrOp(i) := disCsrOpR(i)
    disCsrNum(i) := disCsrNumR(i)
    disSrc0Ready(i) := disS0ReadyR(i)
    disSrc0Val(i) := disS0ValR(i)
    disSrc0Robid(i) := disS0RobidR(i)
    disSrc1Ready(i) := disS1ReadyR(i)
    disSrc1Val(i) := disS1ValR(i)
    disSrc1Robid(i) := disS1RobidR(i)
    disImm(i) := disImmR(i)
    disUseImm(i) := disUseImmR(i)
    disBrOffs(i) := disBrOffsR(i)
    disPredTaken(i) := disPredTakenR(i)
    disFtqId(i) := disFtqIdR(i)
  }
}
