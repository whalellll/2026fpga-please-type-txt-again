// Commit: 提交仲裁与精确异常边界（纯组合）。
// 移植自 cpu/commit.v：每拍 0/1/2/4 条退休；统一产生 ARF/RAT/SB/CSR/FTQ/RAS
// 更新；异常/中断/MRET/FENCE/FENCE.I/误预测在此形成精确冲刷。
package e91c.backend

import chisel3._
import chisel3.util.Cat
import e91c.config.Params._
import e91c.config.PrivType
import e91c.config.BrType
import e91c.config.FlushType

class Commit extends Module {
  val io = IO(new Bundle {
    val flushPending = Input(Bool())
    val headRobid0 = Input(UInt(ROB_W.W))
    val replayValid = Input(Bool())
    val replayTag = Input(UInt(ROB_W.W))
    // cmt0/cmt1（与 rob 提交口一致）
    val c = Vec(2, Input(new Bundle {
      val valid = Bool(); val complete = Bool(); val pc = UInt(32.W)
      val isJal = Bool(); val rfWe = Bool(); val rd = UInt(5.W)
      val result = UInt(32.W); val result2 = UInt(32.W)
      val isStore = Bool(); val paddr = UInt(32.W); val vaddr = UInt(32.W)
      val storeData = UInt(32.W)
      val wstrb = UInt(4.W); val size = UInt(3.W); val uncached = Bool()
      val isBranch = Bool(); val brType = UInt(2.W); val predTaken = Bool()
      val brTaken = Bool(); val brTarget = UInt(32.W); val isLast = Bool()
      val ftqId = UInt(FTQ_W.W); val privVec = UInt(6.W); val csrNum = UInt(12.W)
      val excp = UInt(EXCP_NUM.W); val hasExcpFast = Bool(); val hasPrivFast = Bool()
    }))
    val extendedFaults = Output(UInt(4.W))
    val translationFence = Output(Bool())
    val robPop = Output(Bool()); val robClear0 = Output(Bool()); val robClear1 = Output(Bool())
    val arfWe = Vec(2, Output(Bool())); val arfWaddr = Vec(2, Output(UInt(5.W)))
    val arfWdata = Vec(2, Output(UInt(32.W)))
    val ratCmtEn = Vec(2, Output(Bool())); val ratCmtAddr = Vec(2, Output(UInt(5.W)))
    val ratCmtNum = Vec(2, Output(UInt(ROB_W.W)))
    val sbPushValid = Output(Bool()); val sbPushPaddr = Output(UInt(32.W))
    val sbPushData = Output(UInt(32.W)); val sbPushWstrb = Output(UInt(4.W))
    val sbPushSize = Output(UInt(3.W)); val sbPushUncached = Output(Bool())
    val sbPushRobid = Output(UInt(ROB_W.W))
    val sbFull = Input(Bool()); val sbEmpty = Input(Bool())
    val csrCmtValid = Output(Bool()); val csrCmtPc = Output(UInt(32.W))
    val csrCmtEx = Output(Bool()); val csrCmtMret = Output(Bool())
    val csrCmtVaddr = Output(UInt(32.W)); val csrCmtIsStore = Output(Bool())
    val csrCmtRetireCount = Output(UInt(3.W))
    val excpInt = Output(Bool())
    val excpIAM = Output(Bool()); val excpLsAf = Output(Bool()); val excpLsMis = Output(Bool())
    val excpEcallM = Output(Bool()); val excpBreak = Output(Bool()); val excpIllegal = Output(Bool())
    val csrWe = Output(Bool()); val csrWnum = Output(UInt(12.W))
    val csrWmask = Output(UInt(32.W)); val csrWvalue = Output(UInt(32.W))
    val hasInt = Input(Bool()); val csrNextPc = Input(UInt(32.W))
    val fenceIV = Output(Bool())
    val ftqCmtValid = Output(Bool()); val ftqCmtId = Output(UInt(FTQ_W.W))
    val ftqCmtRelease = Output(UInt(2.W)); val ftqCmtIsBranch = Output(Bool())
    val ftqCmtTaken = Output(Bool()); val ftqCmtMispred = Output(Bool())
    val ftqCmtTarget = Output(UInt(32.W)); val ftqCmtBrType = Output(UInt(2.W))
    val ftqCmtPc = Output(UInt(32.W)); val ftqQueryId = Output(UInt(FTQ_W.W))
    val ftqBlkTarget = Input(UInt(32.W)); val ftqBlkTargetNext = Input(UInt(32.W))
    val rasCall = Output(Bool()); val rasRet = Output(Bool()); val rasRetaddr = Output(UInt(32.W))
    val flushReq = Output(Bool()); val flushType = Output(UInt(FLUSH_TYPE_W.W))
    val flushPc = Output(UInt(32.W))
    val earlyRecoveryValid = Input(Bool()); val earlyRecoveryRobid = Input(UInt(ROB_W.W))
    val preserveFrontend = Output(Bool())
    val uncachedLdInflight = Input(Bool())
    val retire0Valid = Output(Bool()); val retire0Pc = Output(UInt(32.W))
    val retire1Valid = Output(Bool()); val retire1Pc = Output(UInt(32.W))
  })

  private def c0 = io.c(0)
  private def c1 = io.c(1)
  val cmt1Robid = Cat(1.U(1.W), io.headRobid0(ROB_PAIR_W - 1, 0))

  val replay0 = io.replayValid && io.replayTag === io.headRobid0
  val replay1 = io.replayValid && io.replayTag === cmt1Robid
  val replayAtHead = !io.flushPending && Mux(c0.valid,
    c0.complete && replay0, c1.valid && c1.complete && replay1)
  val cmt0Ready = !io.flushPending && c0.valid && c0.complete && !replay0
  val cmt1Ready = !io.flushPending && c1.valid && c1.complete && !replay1

  val cmt0CfMis = cmt0Ready && c0.isBranch && c0.brTaken && c0.brTarget(1, 0).orR
  val cmt1CfMis = cmt1Ready && c1.isBranch && c1.brTaken && c1.brTarget(1, 0).orR
  val cmt0HasExcp = c0.hasExcpFast | cmt0CfMis
  val cmt1HasExcp = c1.hasExcpFast | cmt1CfMis
  val cmt0HasPriv = c0.hasPrivFast
  val cmt1HasPriv = c1.hasPrivFast

  val cmt0TrueWfi = c0.privVec(PrivType.WFI)
  val intTake = !io.flushPending && io.hasInt && c0.valid && !io.uncachedLdInflight && !cmt0TrueWfi
  val cmt0FenceBlock = cmt0Ready && c0.privVec(PrivType.FENCE) && !io.sbEmpty
  val cmt1FenceBlock = cmt1Ready && c1.privVec(PrivType.FENCE) && !io.sbEmpty
  val cmt0FenceIBlock = cmt0Ready && c0.privVec(PrivType.FENCE_I) && !io.sbEmpty
  val cmt1FenceIBlock = cmt1Ready && c1.privVec(PrivType.FENCE_I) && !io.sbEmpty
  val cmt0StorePush = cmt0Ready && c0.isStore && c0.wstrb.orR && !cmt0HasExcp
  val cmt1StorePush = cmt1Ready && c1.isStore && c1.wstrb.orR && !cmt1HasExcp
  val cmt0StoreBlock = cmt0StorePush && io.sbFull
  val cmt0EffectW = Wire(Bool())
  val cmt0Effect = cmt0EffectW
  val cmt1StoreBlock = cmt1StorePush && (io.sbFull || (cmt0EffectW && c0.isStore))

  val cmt0Mispred = cmt0Ready && !cmt0HasExcp && !cmt0HasPriv &&
    ((c0.brTaken =/= c0.predTaken) ||
      (c0.brTaken && c0.predTaken && (c0.brTarget =/= io.ftqBlkTarget)) ||
      (!c0.isBranch && c0.predTaken))

  val cmt1SameFtq = c0.valid && (c0.ftqId === c1.ftqId)
  val cmt1FtqTarget = Mux(!c0.valid || cmt1SameFtq, io.ftqBlkTarget, io.ftqBlkTargetNext)
  val cmt1BranchMispred = cmt1Ready && !cmt1HasExcp && !cmt1HasPriv && c1.isBranch &&
    ((c1.brTaken =/= c1.predTaken) ||
      (c1.brTaken && c1.predTaken && (c1.brTarget =/= cmt1FtqTarget)))
  val cmt1NonbranchMispred = cmt1Ready && !cmt1HasExcp && !cmt1HasPriv &&
    !c1.isBranch && (c1.brTaken || c1.predTaken)
  val cmt1Mispred = cmt1BranchMispred || cmt1NonbranchMispred

  val cmt1BrSoft = c1.isBranch &&
    ((c1.brType === BrType.COND.U) || ((c1.brType === BrType.UNCOND.U) && c1.isJal))
  val cmt1BrHard = c1.isBranch && !cmt1BrSoft

  val cmt0Retire = intTake ||
    (cmt0Ready && (cmt0HasExcp ||
      (!cmt0StoreBlock && !cmt0FenceBlock && !cmt0FenceIBlock)))
  cmt0EffectW := cmt0Ready && !intTake && !cmt0HasExcp &&
    !cmt0StoreBlock && !cmt0FenceBlock && !cmt0FenceIBlock
  val cmt0PrivNeedsFlush = cmt0HasPriv
  val cmt0Flush = intTake || (cmt0Ready && cmt0HasExcp) ||
    (cmt0Effect && cmt0PrivNeedsFlush) || cmt0Mispred

  val cmt1HeadRetire = (!c0.valid) &&
    (cmt1Ready && (cmt1HasExcp ||
      (!cmt1StoreBlock && !cmt1FenceBlock && !cmt1FenceIBlock)))
  val cmt1HeadEffect = (!c0.valid) && cmt1Ready && !cmt1HasExcp &&
    !cmt1StoreBlock && !cmt1FenceBlock && !cmt1FenceIBlock
  val cmt0TakenBr = cmt0Effect && c0.isBranch && c0.brTaken && !c0.isLast

  val cmt1SingleLimit = cmt1HasExcp || cmt1HasPriv || cmt1BrHard ||
    cmt1NonbranchMispred ||
    cmt0HasPriv || (c0.isBranch && c1.isBranch) ||
    cmt0TakenBr
  val cmt1DualEffect = cmt0Effect && !cmt0Flush && cmt1Ready &&
    !cmt1SingleLimit && !cmt1StoreBlock &&
    !cmt1FenceBlock && !cmt1FenceIBlock
  val cmt1Retire = Mux(c0.valid, cmt1DualEffect, cmt1HeadRetire)
  val cmt1Effect = Mux(c0.valid, cmt1DualEffect, cmt1HeadEffect)

  val takeSlot1ForCsr = !cmt0Retire && cmt1HeadRetire
  val brSelCmt1 = (cmt1DualEffect && c1.isBranch) || takeSlot1ForCsr
  val csrSelPc = Mux(takeSlot1ForCsr, c1.pc, c0.pc)
  val selPc = Mux(brSelCmt1, c1.pc, c0.pc)
  val instructionBytes = 4.U
  val selResult2 = Mux(takeSlot1ForCsr, c1.result2, c0.result2)
  val selVaddr = Mux(takeSlot1ForCsr, c1.vaddr, c0.vaddr)
  val selIsStore = Mux(takeSlot1ForCsr, c1.isStore, c0.isStore)
  val selCsrNum = Mux(takeSlot1ForCsr, c1.csrNum, c0.csrNum)
  val selPriv = Mux(takeSlot1ForCsr, c1.privVec, c0.privVec)
  val selExcpBase = Mux(takeSlot1ForCsr, c1.excp, c0.excp)
  val selCfMis = Mux(takeSlot1ForCsr, cmt1CfMis, cmt0CfMis)
  val selExcp = selExcpBase | selCfMis   // EXCP_INST_ADDR_MISALIGNED = bit0
  val selIsBranch = Mux(brSelCmt1, c1.isBranch, c0.isBranch)
  val selBrTaken = Mux(brSelCmt1, c1.brTaken, c0.brTaken)
  val selBrTarget = Mux(brSelCmt1, c1.brTarget, c0.brTarget)
  val selBrType = Mux(brSelCmt1, c1.brType, c0.brType)
  val selFtqId = Mux(brSelCmt1, c1.ftqId, c0.ftqId)
  val selRobid = Mux(brSelCmt1, cmt1Robid, io.headRobid0)

  val selectedEffect = Mux(takeSlot1ForCsr, cmt1HeadEffect, cmt0Effect)
  val selectedExcpTake = intTake ||
    Mux(takeSlot1ForCsr, cmt1Ready && cmt1HasExcp, cmt0Ready && cmt0HasExcp)
  val selectedPrivFlush = selectedEffect && selPriv.orR
  val selectedMispred = Mux(brSelCmt1, cmt1Mispred, cmt0Mispred)

  val memExcp = selExcp(5) | selExcp(4) | selExcp(8) | selExcp(9)   // AF=5, MIS=4

  io.robClear0 := cmt0Retire
  io.robClear1 := cmt1Retire
  io.robPop := (c0.valid || c1.valid) &&
    Mux(c0.valid, cmt0Retire, true.B) && Mux(c1.valid, cmt1Retire, true.B)

  io.arfWe(0) := cmt0Effect && c0.rfWe && (c0.rd =/= 0.U)
  io.arfWaddr(0) := c0.rd
  io.arfWdata(0) := c0.result
  io.arfWe(1) := cmt1Effect && c1.rfWe && (c1.rd =/= 0.U)
  io.arfWaddr(1) := c1.rd
  io.arfWdata(1) := c1.result

  for (k <- 0 until 2) {
    io.ratCmtEn(k) := io.arfWe(k)
  }
  io.ratCmtAddr(0) := c0.rd; io.ratCmtNum(0) := io.headRobid0
  io.ratCmtAddr(1) := c1.rd; io.ratCmtNum(1) := cmt1Robid

  val cmt0SbPush = cmt0Effect && c0.isStore && c0.wstrb.orR
  val cmt1SbPush = cmt1Effect && c1.isStore && c1.wstrb.orR && !cmt0SbPush
  io.sbPushValid := cmt0SbPush || cmt1SbPush
  io.sbPushPaddr := Mux(cmt0SbPush, c0.paddr, c1.paddr)
  io.sbPushData := Mux(cmt0SbPush, c0.storeData, c1.storeData)
  io.sbPushWstrb := Mux(cmt0SbPush, c0.wstrb, c1.wstrb)
  io.sbPushSize := Mux(cmt0SbPush, c0.size, c1.size)
  io.sbPushUncached := Mux(cmt0SbPush, c0.uncached, c1.uncached)
  io.sbPushRobid := Mux(cmt0SbPush, io.headRobid0, cmt1Robid)

  io.csrCmtValid := cmt0Retire || cmt1Retire
  io.csrCmtPc := csrSelPc
  io.csrCmtEx := selectedExcpTake
  io.csrCmtMret := selectedEffect && selPriv(PrivType.MRET)
  io.csrCmtVaddr := Mux(selCfMis, selBrTarget, Mux(memExcp, selVaddr, csrSelPc))
  io.csrCmtIsStore := selIsStore
  io.csrCmtRetireCount := Cat(0.U(2.W), cmt1Effect) + Cat(0.U(2.W), cmt0Effect)
  io.extendedFaults := selExcp(9,6)
  io.translationFence := selectedEffect && (selPriv(PrivType.CSR_SERIAL) && selCsrNum(11,5) === 9.U ||
    selPriv(PrivType.CSR_WR) && selCsrNum === "h180".U)
  io.excpInt := intTake
  io.excpIAM := selExcp(0)
  io.excpLsAf := selExcp(5)
  io.excpLsMis := selExcp(4)
  io.excpEcallM := selExcp(2)
  io.excpBreak := selExcp(3)
  io.excpIllegal := selExcp(1)
  io.csrWe := selectedEffect && selPriv(PrivType.CSR_WR)
  io.csrWnum := selCsrNum
  io.csrWmask := "hffffffff".U
  io.csrWvalue := selResult2
  io.fenceIV := selectedEffect && selPriv(PrivType.FENCE_I)

  val ftqS0Last = cmt0Effect && (c0.isLast || (c0.isBranch && c0.brTaken))
  val ftqS1Last = cmt1Effect && (c1.isLast || (c1.isBranch && c1.brTaken))

  io.ftqCmtValid := selectedEffect || cmt1DualEffect
  io.ftqCmtId := selFtqId
  io.ftqCmtRelease := Cat(0.U(1.W), ftqS0Last) + Cat(0.U(1.W), ftqS1Last)
  io.ftqCmtIsBranch := selIsBranch
  io.ftqCmtTaken := selBrTaken
  io.ftqCmtMispred := selectedMispred
  io.ftqCmtTarget := selBrTarget
  io.ftqCmtBrType := selBrType
  io.ftqCmtPc := selPc
  io.ftqQueryId := Mux(c0.valid, c0.ftqId, c1.ftqId)

  val brRetired = Mux(brSelCmt1, cmt1Effect && c1.isBranch, cmt0Effect && c0.isBranch)
  io.rasCall := brRetired && (selBrType === BrType.CALL.U)
  io.rasRet := brRetired && (selBrType === BrType.RET.U)
  io.rasRetaddr := selPc + instructionBytes

  io.flushReq := selectedExcpTake || selectedPrivFlush || selectedMispred
  io.flushType := Mux(selectedExcpTake, FlushType.EXCP.U,
    Mux(selectedEffect && selPriv(PrivType.MRET), FlushType.MRET.U,
    Mux(selectedPrivFlush, FlushType.REFETCH.U,
    Mux(selectedMispred, FlushType.MISPRED.U, FlushType.NONE.U))))
  io.flushPc := Mux(selectedExcpTake, io.csrNextPc,
    Mux(selectedEffect && selPriv(PrivType.MRET), io.csrNextPc,
    Mux(selectedPrivFlush, selPc + instructionBytes,
    Mux(selectedMispred, Mux(selBrTaken, selBrTarget, selPc + instructionBytes), 0.U))))
  io.preserveFrontend := selectedMispred && !selectedExcpTake && !selectedPrivFlush &&
    io.earlyRecoveryValid && io.earlyRecoveryRobid === selRobid
  when(replayAtHead && !intTake) {
    io.flushReq := true.B
    io.flushType := FlushType.REFETCH.U
    io.flushPc := Mux(c0.valid,c0.pc,c1.pc)
    io.preserveFrontend := false.B
  }

  io.retire0Valid := cmt0Effect
  io.retire0Pc := c0.pc
  io.retire1Valid := cmt1Effect
  io.retire1Pc := c1.pc
}
