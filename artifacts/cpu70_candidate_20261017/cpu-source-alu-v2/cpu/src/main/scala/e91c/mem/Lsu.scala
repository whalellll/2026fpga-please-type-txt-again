// Lsu: 访存单元（AGU + DC 两级流水 + miss 槽非阻塞 load + STQ 顺序保护）。
// 移植自 cpu/lsu.v。要点：
// - issue→AGU→DC 单 payload 流水寄存器（仅在阶段接收时更新）；
// - DCache 前端 token 表（4 项）+ miss 槽影子（2 项，robid 配对返回）；
// - STQ(16) 未决 store 地址队列 + 最年轻 store 镜像前递；UC park 让位/重载；
// - fused-pair 槽（first load 携带 second，miss 则 replay 回 AGU）；
// - 写回仲裁：miss 槽 > hold > DC 级；fast_wb/fast_mdu 同拍命中旁路。
package e91c.mem

import chisel3._
import chisel3.util.{Cat, Fill, PriorityEncoder, UIntToOH}
import chisel3.util.Decoupled
import e91c.config.Params._
import e91c.config.MemOp

class Lsu extends Module {
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val atomicRequest = Decoupled(new AtomicRequest)
    val atomicBusy = Input(Bool())
    val retireMask = Input(UInt(ROB_SIZE.W))
    val replayValid = Output(Bool()); val replayTag = Output(UInt(ROB_W.W))
    // 发射入口
    val issueValid = Input(Bool()); val issueRobid = Input(UInt(ROB_W.W)); val issueMemOp = Input(UInt(MemOp.NUM.W))
    val issueBase = Input(UInt(32.W)); val issueBaseReady = Input(Bool()); val issueBaseRobid = Input(UInt(ROB_W.W))
    val issueWdata = Input(UInt(32.W)); val issueWdataReady = Input(Bool()); val issueWdataRobid = Input(UInt(ROB_W.W))
    val issueImm = Input(UInt(32.W))
    val issueOrderSpeculative = Input(Bool()); val issueOrderStoreTag = Input(UInt(ROB_W.W))
    val lsuReady = Output(Bool()); val lsuPlainOnly = Output(Bool())
    val issuePairValid = Input(Bool()); val issuePairRobid = Input(UInt(ROB_W.W))
    val issuePairMemOp = Input(UInt(MemOp.NUM.W)); val issuePairBase = Input(UInt(32.W)); val issuePairImm = Input(UInt(32.W))
    val lsuPairReady = Output(Bool())
    // PMA D 通道
    val pmaDReq = Output(Bool()); val pmaDVaddr = Output(UInt(32.W)); val pmaDIsStore = Output(Bool())
    val pmaDPaddr = Input(UInt(32.W)); val pmaDMat = Input(UInt(2.W)); val pmaDReady = Input(Bool())
    val pmaDExcpAfault = Input(Bool())
    val pmaDPageFault = Input(Bool())
    val pmaDAccept = Output(Bool())
    // DCache load 口
    val dcReq = Output(Bool()); val dcVindex = Output(UInt(7.W)); val dcPaddr = Output(UInt(32.W))
    val dcSize = Output(UInt(3.W)); val dcLoadOp = Output(UInt(4.W)); val dcUncached = Output(Bool())
    val dcRobid = Output(UInt(ROB_W.W))
    val dcError = Input(Bool()); val dcMshrError = Input(Bool())
    val dcAddrOk = Input(Bool()); val dcDataOk = Input(Bool()); val dcRdata = Input(UInt(32.W))
    val dcRespRobid = Input(UInt(ROB_W.W)); val dcRespReady = Output(Bool()); val dcCancel = Output(Bool())
    val dcMiss = Input(Bool()); val dcMshrDataOk = Input(Bool())
    val dcMshrRdata = Input(UInt(32.W)); val dcMshrRobid = Input(UInt(ROB_W.W))
    val dcPairValid = Output(Bool()); val dcPairWord = Output(UInt(3.W)); val dcPairPaddr = Output(UInt(32.W))
    val dcPairDataOk = Input(Bool()); val dcPairMiss = Input(Bool()); val dcPairRdata = Input(UInt(32.W))
    // SB 前递查询
    val sbQueryValid = Output(Bool()); val sbQueryPaddr = Output(UInt(30.W)); val sbQueryUncached = Output(Bool())
    val sbQueryRespValid = Input(Bool()); val sbQueryRespPaddr = Input(UInt(30.W)); val sbQueryRespUncached = Input(Bool())
    val sbQueryMaybe = Input(Bool()); val sbQueryHit = Input(Bool())
    val sbQueryData = Input(UInt(32.W)); val sbQueryPartial = Input(Bool()); val sbEmpty = Input(Bool())
    val sbPairQueryPaddr = Output(UInt(30.W)); val sbPairQueryMaybe = Input(Bool())
    // ROB head / store retire / base 探测
    val robHeadRobid = Input(UInt(ROB_W.W)); val robHeadValid = Input(Bool())
    val stRetireValid = Input(Bool()); val stRetireRobid = Input(UInt(ROB_W.W))
    val aBaseProbeRobid = Output(UInt(ROB_W.W))
    val robABaseReady = Input(Bool()); val robABaseData = Input(UInt(32.W))
    val qBaseProbeRobid = Output(UInt(ROB_W.W))
    val robQBaseReady = Input(Bool()); val robQBaseData = Input(UInt(32.W))
    val uncachedLdInflight = Output(Bool())
    // 写回 ROB
    val wbValid = Output(Bool()); val wbRobid = Output(UInt(ROB_W.W)); val wbData = Output(UInt(32.W))
    val wbPaddr = Output(UInt(32.W)); val wbVaddr = Output(UInt(32.W)); val wbWstrb = Output(UInt(4.W))
    val wbSize = Output(UInt(3.W)); val wbUncached = Output(Bool()); val wbExcp = Output(UInt(EXCP_NUM.W))
    val pairWbValid = Output(Bool()); val pairWbRobid = Output(UInt(ROB_W.W)); val pairWbData = Output(UInt(32.W))
    val pairWbPaddr = Output(UInt(32.W)); val pairWbVaddr = Output(UInt(32.W)); val pairWbSize = Output(UInt(3.W))
    val fastWbValid = Output(Bool()); val fastWbRobid = Output(UInt(ROB_W.W)); val fastWbData = Output(UInt(32.W))
    val fastMduValid = Output(Bool()); val fastMduRobid = Output(UInt(ROB_W.W)); val fastMduData = Output(UInt(32.W))
    val missWaitValid = Output(UInt(LSU_MISS_DEPTH.W))
    val missWaitRobids = Output(UInt((LSU_MISS_DEPTH * ROB_W).W))
    val pendingLoadValid = Output(UInt(LSU_TOKEN_DEPTH.W))
    val pendingLoadRobids = Output(UInt((LSU_TOKEN_DEPTH * ROB_W).W))
    val holdWbValid = Output(Bool()); val holdWbRobid = Output(UInt(ROB_W.W)); val holdWbData = Output(UInt(32.W))
    val earlyWakeupValid = Output(Bool()); val earlyWakeupRobid = Output(UInt(ROB_W.W))
  })

  private val TOK_N = LSU_TOKEN_DEPTH   // 4
  private val MISS_N = LSU_MISS_DEPTH   // 2
  private val STQ_N = 4
  private val DC_HIT_BYPASS = true      // `LSU_DC_HIT_BYPASS=1

  private def prioLow(mask: UInt): UInt = Mux(mask === 0.U, 0.U, PriorityEncoder(mask))

  // ================= AGU 级 =================
  val aValid = RegInit(false.B)
  val aRobid = Reg(UInt(ROB_W.W))
  val aMemOp = Reg(UInt(MemOp.NUM.W))
  val aBase = Reg(UInt(32.W))
  val aImm = Reg(UInt(32.W))
  val aWdataPrimary = Reg(UInt(32.W))
  val aWdataRefill = Reg(UInt(32.W))
  val aWdataRefillSel = Reg(Bool())
  val aWdata = Mux(aWdataRefillSel, aWdataRefill, aWdataPrimary)
  val aBaseReady = Reg(Bool())
  val aBaseRobid = Reg(UInt(ROB_W.W))
  val aWdataReady = Reg(Bool())
  val aWdataRobid = Reg(UInt(ROB_W.W))
  val aOrderSpeculative = RegInit(false.B)

  val aWdataEffW = Wire(UInt(32.W)); val aWdataEff = aWdataEffW
  val aBaseReadyEffW = Wire(Bool()); val aBaseReadyEff = aBaseReadyEffW
  aWdataEffW := aWdata
  aBaseReadyEffW := aBaseReady

  // issue skid
  val qValid = RegInit(false.B)
  val qRobid = Reg(UInt(ROB_W.W)); val qMemOp = Reg(UInt(MemOp.NUM.W))
  val qBase = Reg(UInt(32.W)); val qImm = Reg(UInt(32.W)); val qWdata = Reg(UInt(32.W))
  val qWdataRefill = Reg(UInt(32.W)); val qWdataRefillSel = Reg(Bool())
  val qBaseReady = Reg(Bool()); val qBaseRobid = Reg(UInt(ROB_W.W))
  val qWdataReady = Reg(Bool()); val qWdataRobid = Reg(UInt(ROB_W.W))
  val qOrderSpeculative = RegInit(false.B)

  // fused-pair 槽
  val pairSlotValid = RegInit(false.B)
  val pairWaitResp = RegInit(false.B)
  val pairReplay = RegInit(false.B)
  val pairAguReplay = RegInit(false.B)
  val pairFirstRobid = Reg(UInt(ROB_W.W))
  val pairSlotRobid = Reg(UInt(ROB_W.W)); val pairSlotMemOp = Reg(UInt(MemOp.NUM.W))
  val pairSlotVaddr = Reg(UInt(32.W)); val pairSlotPaddr = Reg(UInt(32.W))

  val phValid = RegInit(false.B)
  val phRobid = Reg(UInt(ROB_W.W)); val phData = Reg(UInt(32.W))
  val phVaddr = Reg(UInt(32.W)); val phPaddr = Reg(UInt(32.W)); val phSize = Reg(UInt(3.W))

  val aIsStoreOp = aMemOp(MemOp.ST_W) | aMemOp(MemOp.ST_B) | aMemOp(MemOp.ST_H)
  val aIsAtomic = aMemOp(MemOp.ATOMIC)
  val aIsLoadOp = aMemOp(MemOp.LD_W) | aMemOp(MemOp.LD_B) | aMemOp(MemOp.LD_H) | aMemOp(MemOp.LD_BU) | aMemOp(MemOp.LD_HU)

  val aVaddr = Wire(UInt(32.W)); aVaddr := aBase + aImm   // a_base_eff 即 a_base
  val aSizeH = aMemOp(MemOp.LD_H) | aMemOp(MemOp.LD_HU) | aMemOp(MemOp.ST_H)
  val aSizeW = aMemOp(MemOp.LD_W) | aMemOp(MemOp.ST_W)
  val aMisaligned = (aSizeH && aVaddr(0)) | (aSizeW && aVaddr(1, 0) =/= 0.U)
  val aNoTrans = aMisaligned

  io.pmaDReq := aValid && aBaseReadyEff && !aNoTrans && !io.atomicBusy
  io.pmaDVaddr := aVaddr
  io.pmaDIsStore := aIsStoreOp

  val aUncached = io.pmaDMat =/= "b01".U
  val aPaddr = io.pmaDPaddr

  val aExcp = Cat(!aNoTrans && io.pmaDPageFault && aIsStoreOp,
    !aNoTrans && io.pmaDPageFault && !aIsStoreOp,0.U(2.W),
    !aNoTrans && (io.pmaDExcpAfault || (aIsAtomic && aUncached && !io.pmaDPageFault)),aMisaligned,0.U(4.W))

  val aOff = aVaddr(1, 0)
  val aStData = Wire(UInt(32.W)); val aStStrb = Wire(UInt(4.W))
  aStData := Mux(aMemOp(MemOp.ST_B), Fill(4, aWdataEff(7, 0)),
    Mux(aMemOp(MemOp.ST_H), Cat(aWdataEff(15, 0), aWdataEff(15, 0)), aWdataEff))
  aStStrb := Mux(aMemOp(MemOp.ST_B), UIntToOH(aOff, 4),
    Mux(aMemOp(MemOp.ST_H), Mux(aOff(1), "hc".U, "h3".U), "hf".U))

  val aSize = Mux(aMemOp(MemOp.ST_B) | aMemOp(MemOp.LD_B) | aMemOp(MemOp.LD_BU), 0.U,
    Mux(aMemOp(MemOp.ST_H) | aMemOp(MemOp.LD_H) | aMemOp(MemOp.LD_HU), 1.U, 2.U))
  val pairSlotSize = Mux(pairSlotMemOp(MemOp.LD_B) | pairSlotMemOp(MemOp.LD_BU), 0.U,
    Mux(pairSlotMemOp(MemOp.LD_H) | pairSlotMemOp(MemOp.LD_HU), 1.U, 2.U))

  // ================= DC 级 =================
  val dValid = RegInit(false.B)
  val dVaddr = Reg(UInt(32.W))
  val dStData = Reg(UInt(32.W))
  val dRobid = Reg(UInt(ROB_W.W))
  val dMemOp = Reg(UInt(MemOp.NUM.W))
  val dIsStore = Reg(Bool())
  val dIsLoad = Reg(Bool())
  val dPaddr = Reg(UInt(32.W))
  val dStStrb = Reg(UInt(4.W))
  val dWdataReady = Reg(Bool())
  val dWdataRobid = Reg(UInt(ROB_W.W))
  val dSize = Reg(UInt(3.W))
  val dUncached = Reg(Bool())
  val dExcp = Reg(UInt(EXCP_NUM.W))
  val dPairValid = Reg(Bool())
  val dPairVaddr = Reg(UInt(32.W))
  val dPairPaddr = Reg(UInt(32.W))
  val dPairRobid = Reg(UInt(ROB_W.W))
  val dPairMemOp = Reg(UInt(MemOp.NUM.W))
  val dPairSize = Reg(UInt(3.W))
  val dOrderSpeculative = RegInit(false.B)

  // ================= token / miss / hold =================
  val tValidA = Seq.fill(TOK_N)(RegInit(false.B))
  val tRobidA = Seq.fill(TOK_N)(Reg(UInt(ROB_W.W)))
  val tWordLoadA = Seq.fill(TOK_N)(Reg(Bool()))
  val tVaddrA = Seq.fill(TOK_N)(Reg(UInt(32.W)))
  val tPaddrA = Seq.fill(TOK_N)(Reg(UInt(32.W)))
  val tSizeA = Seq.fill(TOK_N)(Reg(UInt(3.W)))
  val tUncachedA = Seq.fill(TOK_N)(Reg(Bool()))
  val tRobidV = VecInit(tRobidA); val tWordLoadV = VecInit(tWordLoadA)
  val tVaddrV = VecInit(tVaddrA); val tPaddrV = VecInit(tPaddrA); val tSizeV = VecInit(tSizeA)
  val tUncachedV = VecInit(tUncachedA)

  val tValidOh = VecInit(tValidA).asUInt
  val tFreeOh = ~tValidOh & Fill(TOK_N, 1.B)
  val tMatchOh = VecInit((0 until TOK_N).map(t => tValidA(t) && tRobidA(t) === io.dcRespRobid)).asUInt
  val pendingLoadValidOh = VecInit((0 until TOK_N).map(t =>
    tValidA(t) && !tUncachedA(t))).asUInt
  io.pendingLoadValid := pendingLoadValidOh
  io.pendingLoadRobids := VecInit((0 until TOK_N).map(t => tRobidA(t))).asUInt
  val tHasFree = tFreeOh.orR
  val tFreeIdx = prioLow(tFreeOh)
  val tMatchVld = tMatchOh.orR
  val tMatchIdx = prioLow(tMatchOh)

  val dReqSent = tValidOh.orR
  val dDrop = false.B

  // miss 槽
  val mValidA = Seq.fill(MISS_N)(RegInit(false.B))
  val mDropA = Seq.fill(MISS_N)(RegInit(false.B))
  val mRobidA = Seq.fill(MISS_N)(Reg(UInt(ROB_W.W)))
  val mVaddrA = Seq.fill(MISS_N)(Reg(UInt(32.W)))
  val mPaddrA = Seq.fill(MISS_N)(Reg(UInt(32.W)))
  val mSizeA = Seq.fill(MISS_N)(Reg(UInt(3.W)))
  val mRobidV = VecInit(mRobidA); val mVaddrV = VecInit(mVaddrA)
  val mPaddrV = VecInit(mPaddrA); val mSizeV = VecInit(mSizeA)

  val mValidOh = VecInit(mValidA).asUInt
  val mFreeOh = ~mValidOh & Fill(MISS_N, 1.B)
  val mDropOh = VecInit((0 until MISS_N).map(m => mValidA(m) && mDropA(m))).asUInt
  val mMatchOh = VecInit((0 until MISS_N).map(m =>
    mValidA(m) && io.dcMshrDataOk && mRobidA(m) === io.dcMshrRobid)).asUInt
  io.missWaitValid := VecInit((0 until MISS_N).map(m => mValidA(m) && !mDropA(m))).asUInt
  io.missWaitRobids := VecInit((0 until MISS_N).map(m => mRobidA(m))).asUInt
  val mHasFree = mFreeOh.orR
  val mFreeIdx = prioLow(mFreeOh)
  val mMatchDrop = mMatchOh & mDropOh
  val mMatchLive = mMatchOh & ~mDropOh
  val mMatchDropIdx = prioLow(mMatchDrop)
  val mMatchLiveIdx = prioLow(mMatchLive)
  val mMatchIdx = Mux(mMatchDrop.orR, mMatchDropIdx, mMatchLiveIdx)

  // hold 槽
  val hError = RegInit(false.B)
  val hValid = RegInit(false.B)
  val hRobid = Reg(UInt(ROB_W.W)); val hData = Reg(UInt(32.W))
  val hVaddr = Reg(UInt(32.W)); val hPaddr = Reg(UInt(32.W)); val hSize = Reg(UInt(3.W))

  val dcFastPipeValid = RegInit(false.B)
  val dcFastPipeRobid = Reg(UInt(ROB_W.W)); val dcFastPipeData = Reg(UInt(32.W))
  val baseMshrPipeValid = RegInit(false.B)
  val baseMshrPipeRobid = Reg(UInt(ROB_W.W)); val baseMshrPipeData = Reg(UInt(32.W))

  // UC park
  val uValid = RegInit(false.B)
  val uRobid = Reg(UInt(ROB_W.W))
  val uMemOp = Reg(UInt(MemOp.NUM.W))
  val uVaddr = Reg(UInt(32.W))
  val uPaddr = Reg(UInt(32.W))
  val uSize = Reg(UInt(3.W))

  // ================= STQ =================
  val stqV = Seq.fill(STQ_N)(RegInit(false.B))
  val stqId = Seq.fill(STQ_N)(Reg(UInt(ROB_W.W)))
  val stqPa = Seq.fill(STQ_N)(Reg(UInt(32.W)))
  val stqData = Seq.fill(STQ_N)(Reg(UInt(32.W)))
  val stqStrb = Seq.fill(STQ_N)(Reg(UInt(4.W)))
  val stqUc = Seq.fill(STQ_N)(Reg(Bool()))
  val stqYValid = RegInit(false.B)
  val stqYId = Reg(UInt(ROB_W.W)); val stqYPa = Reg(UInt(32.W))
  val stqYData = Reg(UInt(32.W)); val stqYStrb = Reg(UInt(4.W)); val stqYUc = Reg(Bool())

  val headPair = io.robHeadRobid(ROB_PAIR_W - 1, 0)
  val headS0Live = io.robHeadRobid(ROB_W - 1)

  val stRetVR = RegInit(false.B); val stRetIdR = RegInit(0.U(ROB_W.W))
  when(!io.flush) {
    stRetVR := io.stRetireValid
    stRetIdR := io.stRetireRobid
  }.otherwise {
    stRetVR := false.B
  }

  val stqDone = VecInit((0 until STQ_N).map(s => stqV(s) && stRetVR && stqId(s) === stRetIdR))

  // Decode the load byte mask at the AGU/DC pipeline boundary. The DC-stage
  // mask is used by store-order and cache-admission logic in the same cycle;
  // deriving it from dMemOp on that path delays the next AGU admission.
  val dLdBytes = Reg(UInt(4.W))
  val aLdBytes = Mux(aMemOp(MemOp.LD_B) || aMemOp(MemOp.LD_BU), UIntToOH(aVaddr(1, 0), 4),
    Mux(aMemOp(MemOp.LD_H) || aMemOp(MemOp.LD_HU), Mux(aVaddr(1), "hc".U, "h3".U), "hf".U))
  val uLdBytes = Mux(uMemOp(MemOp.LD_B) || uMemOp(MemOp.LD_BU), UIntToOH(uVaddr(1, 0), 4),
    Mux(uMemOp(MemOp.LD_H) || uMemOp(MemOp.LD_HU), Mux(uVaddr(1), "hc".U, "h3".U), "hf".U))

  val stqHitOne = VecInit((0 until STQ_N).map(s =>
    stqV(s) && stqPa(s)(31, 2) === dPaddr(31, 2) && (stqStrb(s) & dLdBytes).orR))
  val dPairLdBytes = Mux(dPairMemOp(MemOp.LD_B) || dPairMemOp(MemOp.LD_BU), UIntToOH(dPairVaddr(1, 0), 4),
    Mux(dPairMemOp(MemOp.LD_H) || dPairMemOp(MemOp.LD_HU), Mux(dPairVaddr(1), "hc".U, "h3".U), "hf".U))
  val dPairStqHitOne = VecInit((0 until STQ_N).map(s =>
    stqV(s) && stqPa(s)(31, 2) === dPairPaddr(31, 2) && (stqStrb(s) & dPairLdBytes).orR))

  val stqAny = VecInit(stqV).asUInt.orR
  val stqAnyUc = VecInit((0 until STQ_N).map(s => stqV(s) && stqUc(s))).asUInt.orR
  val stqOverlap = stqHitOne.asUInt.orR
  val dPairStqOverlap = dPairStqHitOne.asUInt.orR

  val stqFwdHit = stqYValid && !stqYUc && stqYPa(31, 2) === dPaddr(31, 2) &&
    (stqYStrb & dLdBytes) === dLdBytes

  val stqFull = VecInit(stqV).asUInt.andR
  val storeOrderBlock = Mux(dUncached, stqAny, (stqOverlap && !stqFwdHit) || stqAnyUc)

  // pair 判定
  val aPairMatch = pairSlotValid && !pairWaitResp && !pairReplay && !pairAguReplay &&
    aValid && (aRobid === pairFirstRobid)
  val aPairPaddr = Cat(aPaddr(31, 12), pairSlotVaddr(11, 0))
  val pairSlotSizeH = pairSlotMemOp(MemOp.LD_H) | pairSlotMemOp(MemOp.LD_HU)
  val pairSlotSizeW = pairSlotMemOp(MemOp.LD_W)
  val pairSlotMisaligned = (pairSlotSizeH && pairSlotVaddr(0)) | (pairSlotSizeW && pairSlotVaddr(1, 0).orR)
  io.sbPairQueryPaddr := Mux(dPairValid, dPairPaddr(31, 2), aPairPaddr(31, 2))
  val aPairEligible = aIsLoadOp && !aUncached && !aExcp.orR && !pairSlotMisaligned &&
    aVaddr(31, 12) === pairSlotVaddr(31, 12) &&
    ((aPaddr(5) =/= pairSlotVaddr(5)) || (aPaddr(11, 6) === pairSlotVaddr(11, 6))) &&
    !io.sbPairQueryMaybe
  val aPairSafe = aPairMatch && aPairEligible
  val dPairRuntimeSafe = dPairValid && !dUncached && !dExcp.orR && !stqAnyUc && !dPairStqOverlap &&
    !io.sbPairQueryMaybe &&
    ((dPaddr(31, 5) === dPairPaddr(31, 5)) || (dPaddr(5) =/= dPairPaddr(5)))

  // ================= DC 级行为 =================
  val dExcpAny = dExcp.orR
  io.sbQueryPaddr := dPaddr(31, 2)
  io.sbQueryUncached := dValid && dIsLoad && dUncached
  val sbQueryNeeded = dValid && dIsLoad && !dExcpAny && (dUncached || !stqFwdHit) && !io.sbEmpty && io.sbQueryMaybe
  io.sbQueryValid := sbQueryNeeded
  val sbQueryRespMatch = io.sbQueryRespValid && io.sbQueryRespPaddr === dPaddr(31, 2) &&
    io.sbQueryRespUncached === dUncached
  val sbQueryReady = !sbQueryNeeded || sbQueryRespMatch

  val dAtHead = (dRobid(ROB_PAIR_W - 1, 0) === headPair) &&
    ((dRobid(ROB_W - 1) === false.B) || !headS0Live) && io.robHeadValid

  val dIsUncLoad = dValid && dIsLoad && dUncached && !dExcpAny
  val dIsUartLsr = false.B
  io.uncachedLdInflight := dIsUncLoad || uValid

  val dLdGate = !storeOrderBlock && !hValid && tHasFree && sbQueryReady &&
    (!dUncached || ((dAtHead || dIsUartLsr) && !(sbQueryRespMatch && io.sbQueryPartial)))

  val dStqHit = dValid && dIsLoad && !dExcpAny && !dUncached && stqFwdHit
  val dSbHit = dValid && dIsLoad && !dExcpAny && !dUncached && !dStqHit && sbQueryNeeded &&
    sbQueryRespMatch && io.sbQueryHit
  val dSbPartial = dValid && dIsLoad && !dExcpAny && !dUncached && sbQueryNeeded &&
    sbQueryRespMatch && io.sbQueryPartial

  val dNeedDc = dValid && dIsLoad && !dExcpAny && !dStqHit && !dSbHit && !dSbPartial && !dIsUartLsr

  io.dcReq := dNeedDc && dLdGate && !io.flush
  io.dcVindex := dVaddr(11, 5)
  io.dcPaddr := dPaddr
  io.dcSize := dSize
  io.dcLoadOp := dMemOp(7, 4)
  io.dcUncached := dUncached
  io.dcRobid := dRobid
  io.dcCancel := io.flush
  io.dcPairValid := io.dcReq && dPairRuntimeSafe
  io.dcPairWord := dPairVaddr(4, 2)
  io.dcPairPaddr := dPairPaddr

  val dcFire = io.dcReq && io.dcAddrOk
  val dIsPlainLoad = dMemOp(MemOp.LD_W) || dMemOp(MemOp.LD_B) || dMemOp(MemOp.LD_H) || dMemOp(MemOp.LD_BU) || dMemOp(MemOp.LD_HU)
  val pendingLoadSet = dcFire && dIsPlainLoad && !dUncached
  val pendingLoadRespMatch = (tMatchOh & pendingLoadValidOh).orR
  val dcReturnValid = io.dcDataOk && tMatchVld
  val dcReturn = dcReturnValid && io.dcRespReady
  val dcMissed = io.dcMiss && tMatchVld
  val pendingLoadClearHit = dcReturn && pendingLoadRespMatch
  val pendingLoadClearMiss = dcMissed && pendingLoadRespMatch
  val pairRespMatch = pairWaitResp && io.dcRespRobid === pairFirstRobid
  val pairHitReturn = io.dcPairDataOk && pairRespMatch
  val pairMissReturn = io.dcPairMiss && pairWaitResp

  val mshrReturn = !mMatchDrop.orR && mMatchLive.orR
  val mshrReturnDrop = mMatchDrop.orR

  // load 整形
  def shapeData(word: UInt, op4: UInt, off: UInt): UInt = {
    val byteValue = (word >> (off << 3))(7, 0)
    val halfValue = Mux(off(1), word(31, 16), word(15, 0))
    Mux(op4(0), Cat(Fill(24, byteValue(7)), byteValue),
      Mux(op4(2), Cat(0.U(24.W), byteValue),
        Mux(op4(1), Cat(Fill(16, halfValue(15)), halfValue),
          Mux(op4(3), Cat(0.U(16.W), halfValue), word))))
  }
  val shapedDcToken = io.dcRdata
  val shapedSbD = shapeData(io.sbQueryData, dMemOp(7, 4), dVaddr(1, 0))
  val shapedStqD = shapeData(stqYData, dMemOp(7, 4), dVaddr(1, 0))
  val shapedPair = shapeData(io.dcPairRdata, pairSlotMemOp(7, 4), pairSlotVaddr(1, 0))

  val localRefillData = io.dcMshrRdata
  val localDcHitValid = DC_HIT_BYPASS.B && !io.dcError && io.dcDataOk && io.dcRespReady && tMatchVld
  val localDcHitData = shapedDcToken
  val localFastValid = (hValid && !hError) || dcFastPipeValid
  val localFastRobid = Mux(hValid, hRobid, dcFastPipeRobid)
  val localFastData = Mux(hValid, hData, dcFastPipeData)

  val qBaseMshrHit = baseMshrPipeValid && qValid && !qBaseReady && qBaseRobid === baseMshrPipeRobid
  val qBaseFastHit = localFastValid && qValid && !qBaseReady && qBaseRobid === localFastRobid
  val qBaseRobHit = qValid && !qBaseReady && io.robQBaseReady && !qBaseMshrHit && !qBaseFastHit
  val qBaseRefillHit = qBaseMshrHit || qBaseFastHit || qBaseRobHit
  val aBaseMshrHit = baseMshrPipeValid && aValid && !aBaseReady && aBaseRobid === baseMshrPipeRobid
  val aBaseFastHit = localFastValid && aValid && !aBaseReady && aBaseRobid === localFastRobid
  val aBaseRobHit = aValid && !aBaseReady && io.robABaseReady && !aBaseMshrHit && !aBaseFastHit
  val aBaseRefillHit = aBaseMshrHit || aBaseFastHit || aBaseRobHit
  val issueBaseMshrHit = baseMshrPipeValid && io.issueValid && io.lsuReady && !io.issueBaseReady && io.issueBaseRobid === baseMshrPipeRobid
  val issueBaseFastHit = localFastValid && io.issueValid && io.lsuReady && !io.issueBaseReady && io.issueBaseRobid === localFastRobid
  val issueBaseDcHit = localDcHitValid && io.issueValid && io.lsuReady && !io.issueBaseReady && io.issueBaseRobid === io.dcRespRobid
  val qBaseReturnData = Mux(qBaseMshrHit, baseMshrPipeData, Mux(qBaseFastHit, localFastData, io.robQBaseData))
  val aBaseReturnData = Mux(aBaseMshrHit, baseMshrPipeData, Mux(aBaseFastHit, localFastData, io.robABaseData))
  io.aBaseProbeRobid := aBaseRobid
  io.qBaseProbeRobid := qBaseRobid
  val qBaseEff = Mux(qBaseRefillHit, qBaseReturnData, qBase)
  val qBaseReadyEff = qBaseReady || qBaseRefillHit

  val qWdataMshrHit = baseMshrPipeValid && qValid && !qWdataReady && qWdataRobid === baseMshrPipeRobid
  val qWdataFastHit = localFastValid && qValid && !qWdataReady && qWdataRobid === localFastRobid
  val qWdataDcHit = localDcHitValid && qValid && !qWdataReady && qWdataRobid === io.dcRespRobid
  val qWdataRefillHit = qWdataMshrHit || qWdataFastHit || qWdataDcHit
  val aWdataMshrHit = baseMshrPipeValid && aValid && !aWdataReady && aWdataRobid === baseMshrPipeRobid
  val aWdataFastHit = localFastValid && aValid && !aWdataReady && aWdataRobid === localFastRobid
  val aWdataDcHit = localDcHitValid && aValid && !aWdataReady && aWdataRobid === io.dcRespRobid
  val aWdataRefillHit = aWdataMshrHit || aWdataFastHit || aWdataDcHit
  val dWdataMshrHit = baseMshrPipeValid && dValid && dIsStore && !dWdataReady && dWdataRobid === baseMshrPipeRobid
  val dWdataFastHit = localFastValid && dValid && dIsStore && !dWdataReady && dWdataRobid === localFastRobid
  val dWdataDcHit = localDcHitValid && dValid && dIsStore && !dWdataReady && dWdataRobid === io.dcRespRobid
  val dWdataRefillHit = dWdataMshrHit || dWdataFastHit || dWdataDcHit
  val issueWdataMshrHit = baseMshrPipeValid && io.issueValid && io.lsuReady && !io.issueWdataReady && io.issueWdataRobid === baseMshrPipeRobid
  val issueWdataFastHit = localFastValid && io.issueValid && io.lsuReady && !io.issueWdataReady && io.issueWdataRobid === localFastRobid
  val issueWdataDcHit = localDcHitValid && io.issueValid && io.lsuReady && !io.issueWdataReady && io.issueWdataRobid === io.dcRespRobid
  val issueWdataRefillHit = issueWdataMshrHit || issueWdataFastHit || issueWdataDcHit
  val qReturnData = Mux(qWdataMshrHit, baseMshrPipeData, Mux(qWdataDcHit, localDcHitData, localFastData))
  val aReturnData = Mux(aWdataMshrHit, baseMshrPipeData, Mux(aWdataDcHit, localDcHitData, localFastData))
  val dReturnData = Mux(dWdataMshrHit, baseMshrPipeData, Mux(dWdataDcHit, localDcHitData, localFastData))
  val issueReturnData = Mux(issueWdataMshrHit, baseMshrPipeData, Mux(issueWdataDcHit, localDcHitData, localFastData))
  val qWdataCurrent = Mux(qWdataRefillSel, qWdataRefill, qWdata)
  val qWdataEff = Mux(qWdataRefillHit, qReturnData, qWdataCurrent)
  val qWdataReadyEff = qWdataReady || qWdataRefillHit
  val aWdataReadyEff = aWdataReady || aWdataRefillHit
  aWdataEffW := Mux(aWdataRefillHit, aReturnData, aWdata)   // 最终覆盖（Verilog 908 行定义）
  aBaseReadyEffW := aBaseReady
  val issueBaseEff = io.issueBase
  val issueBaseReadyEff = io.issueBaseReady
  val issueWdataReadyEff = io.issueWdataReady || issueWdataRefillHit

  val dRefillStData = Mux(dMemOp(MemOp.ST_B), Fill(4, dReturnData(7, 0)),
    Mux(dMemOp(MemOp.ST_H), Cat(dReturnData(15, 0), dReturnData(15, 0)), dReturnData))
  val dStDataEff = Mux(dWdataRefillHit, dRefillStData, dStData)

  io.pairWbValid := phValid && !io.flush
  io.pairWbRobid := phRobid; io.pairWbData := phData
  io.pairWbPaddr := phPaddr; io.pairWbVaddr := phVaddr; io.pairWbSize := phSize

  // ================= 写回仲裁 =================
  val wbMshrCase = mshrReturn
  val wbHoldCase = !wbMshrCase && hValid
  val wbLdDcCase = !wbMshrCase && !hValid && dcReturn
  val dcstOk = !wbMshrCase && !hValid && !dcReturn
  val wbExcpCase = dcstOk && dValid && dExcpAny
  val wbUartLsrCase = dcstOk && dIsUartLsr && dLdGate
  val wbStCase = dcstOk && dValid && !dExcpAny && dIsStore && dWdataReady && !stqFull
  val stqReady = dStqHit && dLdGate && !storeOrderBlock
  val sbReady = dSbHit && dLdGate && !storeOrderBlock
  val wbLdSbCase = false.B
  io.dcRespReady := !hValid
  val holdCapDc = dcReturn && !wbLdDcCase
  val holdCapStq = stqReady && !holdCapDc
  val holdCapSb = sbReady && !holdCapDc && !holdCapStq

  io.wbValid := (wbMshrCase || wbHoldCase || wbExcpCase || wbUartLsrCase || wbStCase ||
    wbLdSbCase || wbLdDcCase) && !io.flush
  io.wbRobid := Mux(wbMshrCase, io.dcMshrRobid,
    Mux(wbHoldCase, hRobid, Mux(wbLdDcCase, tRobidV(tMatchIdx), dRobid)))
  io.wbData := Mux(wbMshrCase, io.dcMshrRdata,
    Mux(wbHoldCase, hData,
    Mux(wbUartLsrCase, "h60".U,
    Mux(wbLdSbCase, shapedSbD,
    Mux(wbLdDcCase, shapedDcToken, dStDataEff)))))
  io.wbPaddr := Mux(wbMshrCase, mPaddrV(mMatchIdx),
    Mux(wbHoldCase, hPaddr, Mux(wbLdDcCase, tPaddrV(tMatchIdx), dPaddr)))
  io.wbVaddr := Mux(wbMshrCase, mVaddrV(mMatchIdx),
    Mux(wbHoldCase, hVaddr, Mux(wbLdDcCase, tVaddrV(tMatchIdx), dVaddr)))
  io.wbWstrb := Mux(!wbMshrCase && !wbHoldCase && !wbLdDcCase && dIsStore && !dExcpAny, dStStrb, 0.U)
  io.wbSize := Mux(wbMshrCase, mSizeV(mMatchIdx),
    Mux(wbHoldCase, hSize, Mux(wbLdDcCase, tSizeV(tMatchIdx), dSize)))
  io.wbUncached := Mux(wbLdDcCase, tUncachedV(tMatchIdx),
    (!wbMshrCase && !wbHoldCase) && dUncached)
  io.wbExcp := Mux(wbMshrCase,Mux(io.dcMshrError,32.U,0.U),
    Mux(wbHoldCase,Mux(hError,32.U,0.U),Mux(wbLdDcCase,Mux(io.dcError,32.U,0.U),dExcp)))

  val fastHoldReady = false.B
  val fastDcReady = DC_HIT_BYPASS.B && !io.dcError && io.dcDataOk && io.dcRespReady && tMatchVld
  io.fastWbValid := (fastHoldReady || fastDcReady) && !io.flush
  io.fastWbRobid := Mux(fastHoldReady, hRobid, io.dcRespRobid)
  io.fastWbData := Mux(fastHoldReady, hData, shapedDcToken)
  io.fastMduValid := fastDcReady && tWordLoadV(tMatchIdx) && !io.flush
  io.fastMduRobid := io.dcRespRobid
  io.fastMduData := io.dcRdata
  io.holdWbValid := hValid && !hError && !io.flush
  io.holdWbRobid := hRobid
  io.holdWbData := hData

  // ================= 流水推进 =================
  val dDone = wbExcpCase || wbUartLsrCase || wbStCase || wbLdSbCase || dcFire || holdCapStq || holdCapSb
  val loadOrder = Module(new CompactLoadOrderQueue)
  loadOrder.io.flush := io.flush
  loadOrder.io.headTag := Cat(!headS0Live,headPair)
  loadOrder.io.reserveValid := io.issueValid && io.lsuReady && io.issueOrderSpeculative && !io.flush
  loadOrder.io.reserveLoadTag := io.issueRobid
  loadOrder.io.reserveStoreTag := io.issueOrderStoreTag
  loadOrder.io.resolveValid := dDone && dValid && dIsLoad && dOrderSpeculative && !io.flush
  loadOrder.io.resolveTag := dRobid
  loadOrder.io.resolveCacheable := !dExcpAny && !dUncached
  loadOrder.io.resolveAddress := dPaddr
  loadOrder.io.resolveMask := dLdBytes
  loadOrder.io.storeValid := wbStCase && !io.flush
  loadOrder.io.storeTag := dRobid
  loadOrder.io.storeAddress := dPaddr
  loadOrder.io.storeMask := dStStrb
  io.replayValid := loadOrder.io.replayValid
  io.replayTag := loadOrder.io.replayTag
  val dUcYield = dIsUncLoad && !dIsUartLsr && !dAtHead && !dDrop
  val uAtHead = uValid && uRobid(ROB_PAIR_W - 1, 0) === headPair &&
    ((uRobid(ROB_W - 1) === false.B) || !headS0Live) && io.robHeadValid
  val aFromH = aRobid(ROB_PAIR_W - 1, 0) - headPair
  val dFromH = dRobid(ROB_PAIR_W - 1, 0) - headPair
  val uFromH = uRobid(ROB_PAIR_W - 1, 0) - headPair
  val aOlderThanD = (aFromH < dFromH) ||
    ((aFromH === dFromH) && !aRobid(ROB_W - 1) && dRobid(ROB_W - 1))
  val aOlderThanU = !uValid || (aFromH < uFromH) ||
    ((aFromH === uFromH) && !aRobid(ROB_W - 1) && uRobid(ROB_W - 1))
  val uReload = uAtHead && (!dValid || dDone || dUcYield)
  val dFree = !dValid || dDone ||
    (dUcYield && !uValid && aValid && aOlderThanD && !uReload)
  val aTranslateReady = aNoTrans || io.pmaDReady
  val aGo = aValid && aBaseReadyEff && aTranslateReady && dFree && !uReload && aOlderThanU &&
    !io.atomicBusy && (!aIsAtomic || aExcp.orR)
  val atomicAtHead = io.robHeadValid && aRobid(ROB_PAIR_W-1,0) === headPair &&
    (!aRobid(ROB_W-1) || !headS0Live)
  val atomicDrained = !dValid && !uValid && !tValidOh.orR && !mValidOh.orR &&
    !hValid && !phValid && !pairSlotValid && !dcFastPipeValid && io.sbEmpty
  io.atomicRequest.valid := aValid && aIsAtomic && aBaseReadyEff && aWdataReadyEff &&
    aTranslateReady && !aExcp.orR && atomicAtHead && atomicDrained && !io.flush
  io.atomicRequest.bits.robid := aRobid
  io.atomicRequest.bits.operation := aMemOp(13,9)
  io.atomicRequest.bits.physicalAddress := aPaddr
  io.atomicRequest.bits.virtualAddress := aVaddr
  io.atomicRequest.bits.operand := aWdataEff
  val aConsumed = aGo || io.atomicRequest.fire
  io.pmaDAccept := aConsumed && !aNoTrans && !io.flush
  val dPark = (dUcYield && aGo && !uValid) || (dUcYield && uReload)

  io.lsuReady := !qValid && !io.flush && !io.atomicBusy &&
    !(pairSlotValid && (pairReplay || pairAguReplay)) &&
    (!io.issueOrderSpeculative || loadOrder.io.reserveReady)
  io.lsuPlainOnly := pairSlotValid
  io.lsuPairReady := !pairSlotValid && !io.flush
  val issueAccept = io.issueValid && io.lsuReady
  val issuePairAccept = io.issuePairValid && io.lsuPairReady
  val pairReplayPending = pairSlotValid && (pairReplay || pairAguReplay)
  val pairReplayTake = pairReplayPending && (aGo || !aValid)
  val pairAguSet = aGo && aPairMatch && !aPairEligible
  val aPayloadTakeQ = !pairReplayPending && qValid

  // pair_agu_replay 独立小状态机
  when(io.flush) { pairAguReplay := false.B }
    .elsewhen(!pairSlotValid) { pairAguReplay := false.B }
    .elsewhen(pairAguSet) { pairAguReplay := true.B }

  val aPayloadRobid = Mux(pairReplayPending, pairSlotRobid, Mux(aPayloadTakeQ, qRobid, io.issueRobid))
  val aPayloadMemOp = Mux(pairReplayPending, pairSlotMemOp, Mux(aPayloadTakeQ, qMemOp, io.issueMemOp))
  val aPayloadBase = Mux(pairReplayPending, pairSlotVaddr, Mux(aPayloadTakeQ, qBaseEff, issueBaseEff))
  val aPayloadBaseReady = Mux(pairReplayPending, true.B, Mux(aPayloadTakeQ, qBaseReadyEff, issueBaseReadyEff))
  val aPayloadBaseRobid = Mux(pairReplayPending, 0.U, Mux(aPayloadTakeQ, qBaseRobid, io.issueBaseRobid))
  val aPayloadImm = Mux(pairReplayPending, 0.U, Mux(aPayloadTakeQ, qImm, io.issueImm))
  val aPayloadWdataPrimary = Mux(pairReplayPending, 0.U, Mux(aPayloadTakeQ, qWdataEff, io.issueWdata))
  val aPayloadWdataRefill = Mux(pairReplayPending, 0.U, Mux(aPayloadTakeQ, qWdataEff, issueReturnData))
  val aPayloadWdataRefillSel = !pairReplayPending && !aPayloadTakeQ && issueWdataRefillHit
  val aPayloadWdataReady = Mux(pairReplayPending, true.B, Mux(aPayloadTakeQ, qWdataReadyEff, issueWdataReadyEff))
  val aPayloadWdataRobid = Mux(pairReplayPending, 0.U, Mux(aPayloadTakeQ, qWdataRobid, io.issueWdataRobid))
  val aPayloadOrderSpeculative = Mux(pairReplayPending, false.B,
    Mux(aPayloadTakeQ, qOrderSpeculative, io.issueOrderSpeculative))

  // ================= 主时序 =================
  // Verilog 的 if(reset||flush_i) 全门控：plain Reg（bank/pair 槽）也不得在复位拍写入
  val resetB = reset.asBool
  when(resetB || io.flush) {
    aValid := false.B; qValid := false.B
    aOrderSpeculative := false.B; qOrderSpeculative := false.B
    dValid := false.B; dOrderSpeculative := false.B
    hValid := false.B; dcFastPipeValid := false.B; baseMshrPipeValid := false.B
    phValid := false.B; uValid := false.B
    pairSlotValid := false.B; pairWaitResp := false.B; pairReplay := false.B
    tValidA.foreach(_ := false.B)
    mValidA.foreach(_ := false.B); mDropA.foreach(_ := false.B)
    stqV.foreach(_ := false.B)
    stqYValid := false.B
  }.otherwise {
    phValid := false.B

    dcFastPipeValid := localDcHitValid
    dcFastPipeRobid := io.dcRespRobid
    dcFastPipeData := localDcHitData
    baseMshrPipeValid := mshrReturn && !io.dcMshrError
    baseMshrPipeRobid := mRobidV(mMatchIdx)
    baseMshrPipeData := localRefillData

    // 各级 refill 数据捕获
    when(dWdataRefillHit) {
      dWdataReady := true.B
      dStData := dRefillStData
    }
    when(aWdataRefillHit) {
      aWdataReady := true.B
      aWdataPrimary := aReturnData
      aWdataRefillSel := false.B
    }
    when(qWdataRefillHit) {
      qWdataReady := true.B; qWdata := qReturnData; qWdataRefillSel := false.B
    }
    when(aBaseRefillHit) {
      aBaseReady := true.B
      aBase := aBaseReturnData
    }
    when(qBaseRefillHit) {
      qBaseReady := true.B; qBase := qBaseReturnData
    }

    // pair 槽
    when(!pairSlotValid) {
      pairFirstRobid := io.issueRobid
      pairSlotRobid := io.issuePairRobid
      pairSlotMemOp := io.issuePairMemOp
      pairSlotVaddr := io.issuePairBase + io.issuePairImm
    }
    when(issuePairAccept) {
      pairSlotValid := true.B
      pairWaitResp := false.B
      pairReplay := false.B
    }

    when(dcFire && dPairValid) {
      pairSlotPaddr := dPairPaddr
      when(io.dcPairValid) { pairWaitResp := true.B }
        .otherwise { pairReplay := true.B }
    }.elsewhen(dDone && dPairValid) {
      pairReplay := true.B
    }

    when(pairHitReturn) {
      phValid := true.B
      phRobid := pairSlotRobid
      phData := shapedPair
      phVaddr := pairSlotVaddr
      phPaddr := pairSlotPaddr
      phSize := pairSlotSize
      pairSlotValid := false.B
      pairWaitResp := false.B
      pairReplay := false.B
    }.elsewhen(pairMissReturn) {
      pairWaitResp := false.B
      pairReplay := true.B
    }.elsewhen(pairReplayTake) {
      pairSlotValid := false.B
      pairWaitResp := false.B
      pairReplay := false.B
    }

    // token 表
    when(dcReturn || dcMissed) {
      for (t <- 0 until TOK_N) when(tMatchIdx === t.U) { tValidA(t) := false.B }
    }
    when(dcFire) {
      for (t <- 0 until TOK_N) when(tFreeIdx === t.U) {
        tValidA(t) := true.B
        tRobidA(t) := dRobid
        tWordLoadA(t) := dMemOp(MemOp.LD_W)
        tVaddrA(t) := dVaddr
        tPaddrA(t) := dPaddr
        tSizeA(t) := dSize
        tUncachedA(t) := dUncached
      }
    }

    // miss 槽
    when(mshrReturn || mshrReturnDrop) {
      for (m <- 0 until MISS_N) when(mMatchIdx === m.U) {
        mValidA(m) := false.B
        mDropA(m) := false.B
      }
    }
    when(dcMissed && mHasFree) {
      for (m <- 0 until MISS_N) when(mFreeIdx === m.U) {
        mValidA(m) := true.B
        mDropA(m) := false.B
        mRobidA(m) := tRobidV(tMatchIdx)
        mVaddrA(m) := tVaddrV(tMatchIdx)
        mPaddrA(m) := tPaddrV(tMatchIdx)
        mSizeA(m) := tSizeV(tMatchIdx)
      }
    }

    // hold 槽
    when(wbHoldCase) { hValid := false.B }
    when(holdCapDc || holdCapStq || holdCapSb) {
      hValid := true.B
      hError := holdCapDc && io.dcError
      hRobid := Mux(holdCapDc, tRobidV(tMatchIdx), dRobid)
      hData := Mux(holdCapDc, shapedDcToken, Mux(holdCapStq, shapedStqD, shapedSbD))
      hVaddr := Mux(holdCapDc, tVaddrV(tMatchIdx), dVaddr)
      hPaddr := Mux(holdCapDc, tPaddrV(tMatchIdx), dPaddr)
      hSize := Mux(holdCapDc, tSizeV(tMatchIdx), dSize)
    }

    // STQ
    for (s <- 0 until STQ_N) {
      when(stqDone(s)) { stqV(s) := false.B }
      when(!stqV(s)) {
        stqId(s) := dRobid
        stqPa(s) := dPaddr
        stqData(s) := dStDataEff
        stqStrb(s) := dStStrb
        stqUc(s) := dUncached
      }
    }
    when(stqYValid && stRetVR && stqYId === stRetIdR) { stqYValid := false.B }
    when(wbStCase && dIsStore) {
      stqYValid := true.B
      stqYId := dRobid
      stqYPa := dPaddr
      stqYData := dStDataEff
      stqYStrb := dStStrb
      stqYUc := dUncached
      val stqFreeOh = ~VecInit(stqV).asUInt
      val pushIdx = prioLow(stqFreeOh)
      for (s <- 0 until STQ_N) when(pushIdx === s.U) { stqV(s) := true.B }
    }

    // DC 级 / UC park / reload
    when(dDone && !uReload && !aGo) { dValid := false.B }
    when(dPark) {
      uValid := true.B
      uRobid := dRobid
      uMemOp := dMemOp
      uVaddr := dVaddr
      uPaddr := dPaddr
      uSize := dSize
    }.elsewhen(uReload) {
      uValid := false.B
    }
    when(uReload) {
      dValid := true.B
      dRobid := uRobid
      dMemOp := uMemOp
      dLdBytes := uLdBytes
      dIsStore := false.B
      dIsLoad := true.B
      dVaddr := uVaddr
      dPaddr := uPaddr
      dStData := 0.U
      dStStrb := 0.U
      dWdataReady := true.B
      dWdataRobid := 0.U
      dSize := uSize
      dUncached := true.B
      dExcp := 0.U
      dPairValid := false.B
      dOrderSpeculative := false.B
    }.elsewhen(aGo) {
      dValid := true.B
      dVaddr := aVaddr
      dStData := aStData
      dRobid := aRobid
      dMemOp := aMemOp
      dLdBytes := aLdBytes
      dIsStore := aIsStoreOp
      dIsLoad := aIsLoadOp
      dPaddr := aPaddr
      dStStrb := aStStrb
      dWdataReady := aWdataReadyEff
      dWdataRobid := aWdataRobid
      dSize := aSize
      dUncached := aUncached
      dExcp := aExcp
      dPairValid := aPairSafe
      dPairVaddr := pairSlotVaddr
      dPairPaddr := aPairPaddr
      dPairRobid := pairSlotRobid
      dPairMemOp := pairSlotMemOp
      dPairSize := pairSlotSize
      dOrderSpeculative := aOrderSpeculative
    }

    // issue skid -> AGU
    when(aConsumed || !aValid) {
      aRobid := aPayloadRobid
      aMemOp := aPayloadMemOp
      aBase := aPayloadBase
      aBaseReady := aPayloadBaseReady
      aBaseRobid := aPayloadBaseRobid
      aImm := aPayloadImm
      aWdataPrimary := aPayloadWdataPrimary
      aWdataRefill := aPayloadWdataRefill
      aWdataRefillSel := aPayloadWdataRefillSel
      aWdataReady := aPayloadWdataReady
      aWdataRobid := aPayloadWdataRobid
      aOrderSpeculative := aPayloadOrderSpeculative
      when(pairReplayTake) { aValid := true.B }
        .elsewhen(qValid) { aValid := true.B; qValid := false.B }
        .otherwise { aValid := issueAccept }
    }.elsewhen(!qValid) {
      qValid := issueAccept
    }
    when(!qValid) {
      qRobid := io.issueRobid
      qMemOp := io.issueMemOp
      qBase := issueBaseEff
      qBaseReady := issueBaseReadyEff
      qBaseRobid := io.issueBaseRobid
      qImm := io.issueImm
      qWdata := io.issueWdata
      qWdataRefill := issueReturnData
      qWdataRefillSel := issueWdataRefillHit
      qWdataReady := issueWdataReadyEff
      qWdataRobid := io.issueWdataRobid
      qOrderSpeculative := io.issueOrderSpeculative
    }
  }

  // Retain the timing-compatible output ports while this optional early path is disabled.
  io.earlyWakeupValid := dcFire && !dUncached && !dExcpAny && !io.flush
  io.earlyWakeupRobid := dRobid
}
