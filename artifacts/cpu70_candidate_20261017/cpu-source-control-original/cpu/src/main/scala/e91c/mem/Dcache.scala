// DCache: L1 数据缓存（load/store 分离双口 + 非阻塞 miss）。
// 移植自 cpu/dcache.v（DC_MSHR_DEPTH=1 配置）。要点：
// - NWAY×256组×32B 写回 + 写分配；VIPT（vaddr index / paddr tag）；
//   135 实测：组数减半（128 组）仅省 51 LUT（阵列在 BSRAM/DRAM），周期
//   +~2%、tag 比较变宽使 10ns WNS 转负——容量瘦身不可行，维持 256 组；
// - 前端 FSM：IDLE 接受拍发 BRAM 读、LOOKUP 比对、命中两拍完成；
// - 后台 MSHR 非阻塞 miss（load miss 移交 LSU miss 槽；store miss posted）；
//   同行 store 合入在飞 MSHR、二次 load 合入（ld2）；hit-under-miss；
// - 写回缓冲 1 项与重填并行；Safe CWF-lite beat0 早回；
// - tag/valid/dirty 同存同步 RAM；复位后顺序清零 metadata；
// - FENCE.I 全量扫描写回失效；uncached 独占通道访问。
// 注意：ldOp/stSize 等端口沿用 Verilog 位段编号（[7:4] 字段内 bit0=原 bit4），
// MemOp 为 8 位独热编码的字段切片：op(0)=B op(1)=H op(2)=BU op(3)=HU，缺省 W。
package e91c.mem

import chisel3._
import chisel3.util.{switch, is, Cat, PriorityEncoder, Fill}
import e91c.config.Params._

class Dcache extends Module {
  val io = IO(new Bundle {
    val quiescent = Output(Bool())
    val ldReq = Input(Bool()); val ldVindex = Input(UInt(7.W)); val ldPaddr = Input(UInt(32.W))
    val ldSize = Input(UInt(3.W)); val ldOp = Input(UInt(4.W)); val ldUncached = Input(Bool())
    val ldRobid = Input(UInt(ROB_W.W))
    val ldError = Output(Bool()); val ldMshrError = Output(Bool())
    val ldAddrOk = Output(Bool()); val ldDataOk = Output(Bool()); val ldRdata = Output(UInt(32.W))
    val ldRespRobid = Output(UInt(ROB_W.W))
    val ldRespReady = Input(Bool()); val ldCancel = Input(Bool())
    val ldMiss = Output(Bool())
    val ldMshrDataOk = Output(Bool()); val ldMshrRdata = Output(UInt(32.W)); val ldMshrRobid = Output(UInt(ROB_W.W))
    val ldPairValid = Input(Bool()); val ldPairWord = Input(UInt(3.W)); val ldPairPaddr = Input(UInt(32.W))
    val ldPairDataOk = Output(Bool()); val ldPairMiss = Output(Bool()); val ldPairRdata = Output(UInt(32.W))
    val stReq = Input(Bool()); val stPaddr = Input(UInt(32.W))
    val stData = Input(UInt(32.W)); val stStrb = Input(UInt(4.W))
    val stSize = Input(UInt(3.W)); val stUncached = Input(Bool())
    val stAddrOk = Output(Bool()); val stDone = Output(Bool())
    val fenceI = Input(Bool())
    val axiRdReq = Output(Bool()); val axiRdType = Output(UInt(3.W)); val axiRdAddr = Output(UInt(32.W))
    val axiRdRdy = Input(Bool())
    val axiRetError = Input(Bool())
    val fatalStoreError = Output(Bool())
    val axiRetValid = Input(Bool()); val axiRetLast = Input(Bool()); val axiRetData = Input(UInt(128.W))
    val axiWrReq = Output(Bool()); val axiWrType = Output(UInt(3.W)); val axiWrAddr = Output(UInt(32.W))
    val axiWrStrb = Output(UInt(4.W)); val axiWrData = Output(UInt(128.W))
    val axiWrWriteThrough = Output(Bool()); val axiWrRdy = Input(Bool())
    val fullFlushDone = Output(Bool())
  })

  private val NWAY = 2; private val NSET = 128
  private val IDXW = 7; private val TAGW = 32 - IDXW - CACHE_LINE_W; private val LINEW = CACHE_LINE_BITS
  private val N_MSHR = DC_MSHR_DEPTH; private val MSHR_W = 1

  // ---------------- 前端 FSM ----------------
  private def st(i: Int) = i.U(4.W)
  val sIdle = st(0); val sLookup = st(1); val sMwait = st(2); val sRelook = st(3)
  val sUcRreq = st(4); val sUcRdata = st(5); val sUcResp = st(6); val sUcWreq = st(7)
  val sFlushWb0 = st(8); val sFlushWb1 = st(9); val sFlushCapture = st(11)
  val state = RegInit(sIdle)

  // ---------------- MSHR ----------------
  private def ms(i: Int) = i.U(2.W)
  val mIdle = ms(0); val mRreq = ms(1); val mRdata = ms(2); val mInstall = ms(3)

  val mshrState = Seq.fill(N_MSHR)(RegInit(mIdle))
  val mshrIsSt = Seq.fill(N_MSHR)(Reg(Bool()))
  val mshrLdRespPend = Seq.fill(N_MSHR)(Reg(Bool()))
  val mshrFromLd = Seq.fill(N_MSHR)(Reg(Bool()))
  val mshrPaddr = Seq.fill(N_MSHR)(Reg(UInt(32.W)))
  val mshrRobid = Seq.fill(N_MSHR)(Reg(UInt(ROB_W.W)))
  val mshrLdOp = Seq.fill(N_MSHR)(Reg(UInt(4.W)))
  val mshrLd2Pend = Seq.fill(N_MSHR)(Reg(Bool()))
  val mshrLd2Robid = Seq.fill(N_MSHR)(Reg(UInt(ROB_W.W)))
  val mshrLd2Word = Seq.fill(N_MSHR)(Reg(UInt(3.W)))
  val mshrLd2Off = Seq.fill(N_MSHR)(Reg(UInt(2.W)))
  val mshrLd2Op = Seq.fill(N_MSHR)(Reg(UInt(4.W)))
  val mshrWay = Seq.fill(N_MSHR)(Reg(UInt(2.W)))
  val mshrStbLine = Seq.fill(N_MSHR)(Reg(UInt(32.W)))
  val mshrB0 = Seq.fill(N_MSHR)(Reg(UInt(128.W)))
  val mshrLine = Seq.fill(N_MSHR)(Reg(UInt(LINEW.W)))

  val mshrBusyOh = VecInit(mshrState.map(_ =/= mIdle)).asUInt
  val mshrRreqOh = VecInit(mshrState.map(_ === mRreq)).asUInt
  val mshrInstallOh = VecInit(mshrState.map(_ === mInstall)).asUInt
  val mshrAnyBusy = mshrBusyOh.orR
  val mshrHasFree = !mshrBusyOh.andR
  val mshrAnyInstall = mshrInstallOh.orR
  val mshrRreqVld = mshrRreqOh.orR

  private def prioLow(mask: UInt): UInt = Mux(mask === 0.U, 0.U, PriorityEncoder(mask))
  val mshrFreeIdx = prioLow(~mshrBusyOh)
  val mshrRreqIdx = prioLow(mshrRreqOh)
  val mshrInstallIdx = prioLow(mshrInstallOh)

  val mshrPaddrV = VecInit(mshrPaddr)
  val mshrStateV = VecInit(mshrState)
  val mshrLd2PendV = VecInit(mshrLd2Pend)

  // AXI 读通道 owner
  val axiMshrHold = RegInit(false.B)
  val axiMshrId = RegInit(0.U(MSHR_W.W))
  val axiMshrGrantVld = axiMshrHold || mshrRreqVld
  val axiMshrGrant = Mux(axiMshrHold, axiMshrId, mshrRreqIdx)
  val mshrAxiLine = mshrPaddrV(axiMshrGrant)(31, CACHE_LINE_W)

  // ---------------- 写回缓冲 ----------------
  private def ws(i: Int) = i.U(2.W)
  val wIdle = ws(0); val wB0 = ws(1); val wB1 = ws(2)
  val wbState = RegInit(wIdle)
  val wbValid = RegInit(false.B)
  val wbAddr = Reg(UInt(32.W))
  val wbLine = Reg(UInt(LINEW.W))
  val wbAllIdle = (wbState === wIdle) && !wbValid

  // ---------------- 存储阵列 ----------------
  // tag/data RAM（双口同步：A 读写，B 只读）。Tag RAM 的高两位
  // 依次保存 dirty/valid，使 lookup metadata 与 tag 共享同一个读边界。
  val tagMem = Seq.fill(NWAY)(Mem(NSET, UInt((TAGW + 2).W)))
  // Keep one physical line array, but expose its byte write enables so a
  // store hit does not require a 256-bit read/modify/write data path.
  val dataMem = Seq.fill(NWAY)(Mem(NSET, Vec(32, UInt(8.W))))
  val tagRd = Seq.fill(NWAY)(Reg(UInt((TAGW + 2).W)))
  val pairTagRd = Seq.fill(NWAY)(Reg(UInt((TAGW + 2).W)))
  val dataOut = Seq.fill(NWAY)(Reg(UInt(LINEW.W)))
  val pairDataOut = Seq.fill(NWAY)(Reg(UInt(LINEW.W)))
  val dataOutV = VecInit(dataOut)
  val tagRdV = VecInit(tagRd.map(_(TAGW - 1, 0)))
  val pairDataOutV = VecInit(pairDataOut)

  val ramAddr = Wire(UInt(IDXW.W)); val ramRe = Wire(Bool())
  val ramWe = Wire(Vec(NWAY, Bool())); val ramWline = Wire(UInt(LINEW.W))
  val ramPairAddr = Wire(UInt(IDXW.W)); val ramPairRe = Wire(Bool())
  val tagWe = Wire(Vec(NWAY, Bool())); val tagWaddr = Wire(UInt(IDXW.W))
  val tagWdata = Wire(UInt((TAGW + 2).W))

  // Mem contents are not resettable.  A bounded 128-cycle sweep establishes
  // the same all-invalid post-reset state before the D-cache accepts traffic.
  val metaIniting = RegInit(true.B)
  val metaInitSet = RegInit(0.U(IDXW.W))

  val mshrError = RegInit(VecInit(Seq.fill(N_MSHR)(false.B)))
  val ucError = RegInit(false.B)
  val mshrInstallFire = Wire(Bool())
  val mshrInstWay = Wire(UInt(2.W)); val mshrInstTag = Wire(UInt(TAGW.W))

  // ---------------- 请求锁存 ----------------
  val reqIsSt = Reg(Bool()); val reqIsLd = Reg(Bool()); val reqIsFlush = Reg(Bool())
  val reqPaddr = Reg(UInt(32.W)); val reqLdOp = Reg(UInt(4.W))
  val reqMshrLineMatchR = Reg(UInt(N_MSHR.W))
  val reqChainSafe = Reg(Bool())
  val reqRobid = Reg(UInt(ROB_W.W))
  val reqWdata = Reg(UInt(32.W)); val reqWstrb = Reg(UInt(4.W))
  val reqSize = Reg(UInt(3.W)); val reqUncached = Reg(Bool())
  val reqLdKilled = Reg(Bool())
  val reqPairValid = Reg(Bool()); val reqPairWord = Reg(UInt(3.W)); val reqPairPaddr = Reg(UInt(32.W))

  val reqValidVec = VecInit(tagRd.map(_(TAGW))).asUInt
  val reqDirtyVec = VecInit(tagRd.map(_(TAGW + 1))).asUInt
  val reqPairValidVec = VecInit(pairTagRd.map(_(TAGW))).asUInt

  // FENCE.I 扫描项 / pending 缓冲 / 中间量
  val flushPend = RegInit(false.B); val flushPendAddr = Reg(UInt(32.W))
  val pendValid = RegInit(false.B); val pendIsSt = Reg(Bool()); val pendIsLd = Reg(Bool())
  val pendLdKilled = RegInit(false.B); val pendPaddr = Reg(UInt(32.W)); val pendRobid = Reg(UInt(ROB_W.W))
  val pendWdata = Reg(UInt(32.W)); val pendWstrb = Reg(UInt(4.W)); val pendSize = Reg(UInt(3.W))
  val pendLdOp = Reg(UInt(4.W)); val pendUncached = Reg(Bool())
  val pendPairValid = RegInit(false.B); val pendPairWord = Reg(UInt(3.W)); val pendPairPaddr = Reg(UInt(32.W))

  val cwbTag = Reg(UInt(TAGW.W)); val cwbLine = Reg(UInt(LINEW.W)); val cwbWay = Reg(UInt(2.W))
  val ucRdata = Reg(UInt(32.W))

  val fullFlushSet = RegInit(0.U(IDXW.W)); val fullFlushWay = RegInit(0.U(2.W))
  val fullFlushDoneR = RegInit(false.B)
  val fullFlushLast = (fullFlushSet === (NSET - 1).U) && (fullFlushWay === (NWAY - 1).U)
  val fullFlushNextWay = Mux(fullFlushWay === (NWAY - 1).U, 0.U, fullFlushWay + 1.U)
  val fullFlushNextSet = Mux(fullFlushWay === (NWAY - 1).U, fullFlushSet + 1.U, fullFlushSet)
  val fullFlushNextAddr = Cat(0.U((32 - IDXW - 5).W), fullFlushNextSet, 0.U(3.W), fullFlushNextWay)
  io.fullFlushDone := fullFlushDoneR

  val reqSet = reqPaddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W)
  val reqTag = reqPaddr(31, IDXW + CACHE_LINE_W)
  val reqWord = reqPaddr(4, 2)
  val reqPairSet = reqPairPaddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W)
  val reqPairTag = reqPairPaddr(31, IDXW + CACHE_LINE_W)
  val reqPairSameLine = reqPaddr(31, CACHE_LINE_W) === reqPairPaddr(31, CACHE_LINE_W)

  // Tag reads never need the refill/store write-address mux.  When no front
  // request is accepted the sampled value is unowned, so raw request priority
  // can select the idle address without importing accept/MSHR control.
  val tagIdleReadAddr = Mux(flushPend,
    flushPendAddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W),
    Mux(!io.ldReq && io.stReq,
      io.stPaddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W),
      io.ldPaddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W)))
  val tagReadAddr = Mux(state === sRelook, reqSet, tagIdleReadAddr)

  // ---------------- tag 阵列 ----------------
  for (gt <- 0 until NWAY) {
    when(tagWe(gt)) {
      tagMem(gt)(tagWaddr) := tagWdata
    }.elsewhen(ramRe) {
      tagRd(gt) := tagMem(gt)(tagReadAddr)
    }
    when(ramPairRe) { pairTagRd(gt) := tagMem(gt)(ramPairAddr) }
  }

  // ---------------- 命中判定 ----------------
  val wayHit = VecInit((0 until NWAY).map(w =>
    reqValidVec(w) && tagRd(w)(TAGW - 1, 0) === reqTag)).asUInt
  val hitAny = wayHit.orR
  val hitWay = if (NWAY == 1) 0.U(2.W) else Mux(wayHit(1), 1.U(2.W), 0.U(2.W))
  val pairWayHit = VecInit((0 until NWAY).map(w =>
    reqPairValidVec(w) && pairTagRd(w)(TAGW - 1, 0) === reqPairTag)).asUInt
  val pairHitAnyRaw = pairWayHit.orR
  val pairHitWay = if (NWAY == 1) 0.U(2.W) else Mux(pairWayHit(1), 1.U(2.W), 0.U(2.W))

  val wayInvalid = VecInit((0 until NWAY).map(w => !reqValidVec(w))).asUInt
  val replaceWay = RegInit(false.B)
  val pickWay = if (NWAY == 1) 0.U(2.W)
                else Mux(wayInvalid(0), 0.U(2.W),
                  Mux(wayInvalid(1), 1.U(2.W), replaceWay.asUInt))
  val pickValid = VecInit(reqValidVec.asBools)(pickWay)
  val reqDirtyVecEff = reqDirtyVec
  val pickDirty = VecInit(reqDirtyVecEff.asBools)(pickWay)

  val flushReqSet = reqPaddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W)
  val flushReqWay = Cat(0.U(1.W), reqPaddr(0))

  // ---------------- 接受仲裁（IDLE 拍）----------------
  val pendSet = pendPaddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W)
  val pendSetMatch = VecInit((0 until N_MSHR).map(m =>
    mshrBusyOh(m) && pendSet === mshrPaddr(m)(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W))).asUInt
  val pendCanProgress = !pendSetMatch.orR && mshrHasFree
  val pendDrain = (state === sIdle) && pendValid && mshrHasFree && wbAllIdle &&
    !mshrAnyInstall && pendCanProgress
  val lookupLdChain = Wire(Bool())
  val acceptOk = ((state === sIdle) || lookupLdChain) && !metaIniting &&
    !mshrAnyInstall && !pendDrain
  val flushTake = acceptOk && flushPend
  val stTake = acceptOk && !flushPend && !io.ldReq && io.stReq
  val ldTake = acceptOk && !flushPend && io.ldReq

  val stTakeLineMatch = VecInit((0 until N_MSHR).map(m =>
    mshrBusyOh(m) && io.stPaddr(31, CACHE_LINE_W) === mshrPaddr(m)(31, CACHE_LINE_W))).asUInt
  val ldTakeLineMatch = VecInit((0 until N_MSHR).map(m =>
    mshrBusyOh(m) && io.ldPaddr(31, CACHE_LINE_W) === mshrPaddr(m)(31, CACHE_LINE_W))).asUInt
  val ldTakeSetMatch = VecInit((0 until N_MSHR).map(m =>
    mshrBusyOh(m) && io.ldPaddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W) ===
      mshrPaddr(m)(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W))).asUInt

  io.stAddrOk := stTake
  io.ldAddrOk := ldTake

  // ---------------- LOOKUP 拍分类 ----------------
  val mshrSetMatch = VecInit((0 until N_MSHR).map(m =>
    mshrBusyOh(m) && reqSet === mshrPaddr(m)(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W))).asUInt
  val mshrLineMatch = VecInit((0 until N_MSHR).map(m => mshrBusyOh(m) && reqMshrLineMatchR(m))).asUInt
  val pairMshrSetMatch = VecInit((0 until N_MSHR).map(m =>
    mshrBusyOh(m) && reqPairSet === mshrPaddr(m)(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W))).asUInt
  val mshrMergeable = VecInit((0 until N_MSHR).map(m =>
    mshrLineMatch(m) && (mshrState(m) === mRreq || mshrState(m) === mRdata || mshrState(m) === mInstall))).asUInt
  val mshrLdMergeable = VecInit((0 until N_MSHR).map(m =>
    mshrLineMatch(m) && !mshrLd2Pend(m) && (mshrState(m) === mRreq || mshrState(m) === mRdata))).asUInt

  val pairSetConf = !reqPairSameLine && pairMshrSetMatch.orR
  val pairHitAny = Mux(reqPairSameLine, hitAny, pairHitAnyRaw && !pairSetConf)
  val lkStMerge = (state === sLookup) && reqIsSt && !reqIsFlush && !reqUncached && mshrMergeable.orR
  val mshrMergeIdx = prioLow(mshrMergeable)
  val lkLdMerge = (state === sLookup) && reqIsLd && !reqIsFlush && !reqUncached && mshrLdMergeable.orR
  val mshrLdMergeIdx = prioLow(mshrLdMergeable)
  val reqStbLine = VecInit((0 until 8).map(w => Mux(reqWord === w.U, reqWstrb, 0.U(4.W)))).asUInt
  // Byte strobes own every consumed byte; no word-wide data masking is needed.
  val reqDataLine = Fill(8, reqWdata)
  def mergeStoreBytes(old: UInt): UInt = VecInit((0 until 32).map(b =>
    Mux(reqStbLine(b), reqWdata((b % 4) * 8 + 7, (b % 4) * 8), old(b * 8 + 7, b * 8)))).asUInt

  val lkSetConf = (state === sLookup) && !reqIsFlush && !reqUncached &&
    mshrSetMatch.orR && !lkStMerge && !lkLdMerge
  val lkFlushWait = (state === sLookup) && reqIsFlush && (mshrAnyBusy || !wbAllIdle)

  val lkCachedLd = (state === sLookup) && reqIsLd && !reqIsFlush && !reqUncached
  val lkCachedSt = (state === sLookup) && reqIsSt && !reqIsFlush && !reqUncached
  val lkUcLd = (state === sLookup) && reqIsLd && !reqIsFlush && reqUncached
  val lkUcSt = (state === sLookup) && reqIsSt && !reqIsFlush && reqUncached
  val lkFlush = (state === sLookup) && reqIsFlush && !lkFlushWait

  // Any active MSHR on this set either consumes the load as a merge or blocks
  // the lookup.  Test that condition directly so a load-hit response does not
  // pass through the unrelated store-merge classifier.
  val lkLdHit = lkCachedLd && !mshrSetMatch.orR && hitAny
  val lkStHit = lkCachedSt && !lkSetConf && !lkStMerge && hitAny
  val lkLdMiss = lkCachedLd && !mshrSetMatch.orR && !hitAny
  val lkStMiss = lkCachedSt && !lkSetConf && !lkStMerge && !hitAny
  lookupLdChain := lkLdHit && reqChainSafe && !(reqLdKilled || io.ldCancel) && io.ldRespReady

  val missNeedWb = pickValid && pickDirty
  val mshrAllocBase = mshrHasFree && (!missNeedWb || wbAllIdle)
  val lkLdAlloc = lkLdMiss && mshrAllocBase
  val lkStAlloc = lkStMiss && mshrAllocBase

  val lkUcOk = !mshrAnyBusy && wbAllIdle
  val lkCacheBlock = lkSetConf || ((lkLdMiss || lkStMiss) && !mshrAllocBase)
  val lkToPend = lkCacheBlock && !pendValid
  val lkToMwaitCache = lkCacheBlock && pendValid

  // ---------------- 命中数据通路 ----------------
  // Select the 32-bit word before combining ways.  A line-wide way mux or
  // hit mask is redundant for a word-sized load and costs substantial LUTs.
  val hitWords = (0 until NWAY).map(w => (dataOut(w) >> (reqWord << 5))(31, 0))
  val hitWordS32 = (0 until NWAY).map(w =>
    Mux(wayHit(w), hitWords(w), 0.U(32.W))).reduce(_ | _)
  val pairSameWords = VecInit((0 until NWAY).map(w =>
    (dataOut(w) >> (reqPairWord << 5))(31, 0)))
  val pairOtherWords = VecInit((0 until NWAY).map(w =>
    (pairDataOut(w) >> (reqPairWord << 5))(31, 0)))
  val hitPairWord = Mux(reqPairSameLine,
    pairSameWords(hitWay), pairOtherWords(pairHitWay))

  val stLineBe = VecInit((0 until 32).map(b => Fill(8, reqStbLine(b)))).asUInt

  // ---------------- MSHR 重填数据通路 ----------------
  val mshrRfB0 = VecInit(mshrB0)(axiMshrGrant)
  val mshrRfWord = mshrPaddrV(axiMshrGrant)(4, 2)
  val mshrRfOff = mshrPaddrV(axiMshrGrant)(1, 0)
  val mshrRfOp = VecInit(mshrLdOp)(axiMshrGrant)
  val mshrRfLdResp = VecInit(mshrLdRespPend)(axiMshrGrant)
  val mshrOwnerRdata = axiMshrGrantVld && (mshrStateV(axiMshrGrant) === mRdata)

  val refillLineRaw = Cat(io.axiRetData, mshrRfB0)
  val refillMergeNow = lkStMerge && (mshrMergeIdx === axiMshrGrant)
  val refillStoredMask = VecInit(mshrStbLine)(axiMshrGrant)
  val refillDatEff0 = VecInit(mshrLine)(axiMshrGrant)
  val refillLineMerged = VecInit((0 until 32).map { b =>
    Mux(refillMergeNow && reqStbLine(b),reqWdata((b % 4)*8+7,(b % 4)*8),
      Mux(refillStoredMask(b),refillDatEff0(b*8+7,b*8),refillLineRaw(b*8+7,b*8)))
  }).asUInt

  val mshrBeat = mshrOwnerRdata && io.axiRetValid
  val mshrBeat0 = mshrBeat && !io.axiRetLast
  val mshrBeat1 = mshrBeat && io.axiRetLast

  // load 成形：op(0)=B op(2)=BU op(1)=H op(3)=HU，缺省 W（8 位独热 [7:4] 切片）
  def shapeData(word: UInt, op: UInt, off: UInt): UInt = {
    val byteValue = (word >> (off << 3))(7, 0)
    val halfValue = Mux(off(1), word(31, 16), word(15, 0))
    Mux(op(0), Cat(Fill(24, byteValue(7)), byteValue),
      Mux(op(2), Cat(0.U(24.W), byteValue),
        Mux(op(1), Cat(Fill(16, halfValue(15)), halfValue),
          Mux(op(3), Cat(0.U(16.W), halfValue), word))))
  }

  val beatWord = (io.axiRetData >> (mshrRfWord(1, 0) << 5))(31, 0)
  val refillWord = (refillLineMerged >> (mshrRfWord << 5))(31, 0)
  val mshrRfNoStMerge = (VecInit(mshrStbLine)(axiMshrGrant) === 0.U) && !refillMergeNow
  val mshrCwfEarly = false.B // wait for final AXI status before architectural completion
  val mshrRespFire = mshrRfLdResp && (mshrBeat1 || mshrCwfEarly)
  val mshrRespWord = Mux(mshrBeat1, refillWord, beatWord)

  // MSHR 安装拍
  val frontRamBusy = (state === sRelook) || lkStHit || lkFlush ||
    (lkLdHit && !io.ldRespReady)
  val mshrInstallFireOh = VecInit((0 until N_MSHR).map(m =>
    mshrInstallOh(m) && !metaIniting && !frontRamBusy &&
      !(mshrRespFire && mshrLd2Pend(m)) &&
      (mshrInstallIdx === m.U))).asUInt
  mshrInstallFire := mshrInstallFireOh.orR && !mshrError(mshrInstallIdx)
  when(mshrInstallFire) { replaceWay := !VecInit(mshrWay)(mshrInstallIdx)(0) }
  mshrInstWay := VecInit(mshrWay)(mshrInstallIdx)
  val mshrInstSet = mshrPaddrV(mshrInstallIdx)(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W)
  mshrInstTag := mshrPaddrV(mshrInstallIdx)(31, IDXW + CACHE_LINE_W)
  val mshrInstOhV = VecInit(mshrInstallOh.asBools)
  val installMergeNow = lkStMerge && (mshrMergeIdx === mshrInstallIdx) && mshrInstOhV(mshrInstallIdx)
  val mshrInstIsSt = VecInit(mshrIsSt)(mshrInstallIdx) | installMergeNow |
    (VecInit(mshrStbLine)(mshrInstallIdx) =/= 0.U)
  // Store fills belong to already-retired stores. They cannot be retrapped as
  // precise faults: report an unrecoverable fabric error and stop retirement.
  val fatalStore = RegInit(false.B)
  when(mshrInstallFireOh.orR && mshrError(mshrInstallIdx) && mshrInstIsSt) {
    fatalStore := true.B
  }
  io.fatalStoreError := fatalStore
  val mshrInstLine0 = VecInit(mshrLine)(mshrInstallIdx)
  val mshrInstLine = VecInit((0 until 32).map(b =>
    Mux(installMergeNow && reqStbLine(b),reqWdata((b % 4)*8+7,(b % 4)*8),
      mshrInstLine0(b*8+7,b*8)))).asUInt

  val mshrLd2RespFire = !mshrRespFire && mshrAnyInstall && mshrLd2PendV(mshrInstallIdx)
  val mshrLd2WordSel = VecInit(mshrLd2Word)(mshrInstallIdx)
  val mshrLd2RespWord = (mshrInstLine >> (mshrLd2WordSel << 5))(31, 0)
  // The first and paired miss responses are mutually exclusive. Select the
  // raw word before size/sign extension to share one shaper.
  val mshrSelectedWord = Mux(mshrLd2RespFire, mshrLd2RespWord, mshrRespWord)
  val mshrSelectedOp = Mux(mshrLd2RespFire, VecInit(mshrLd2Op)(mshrInstallIdx), mshrRfOp)
  val mshrSelectedOff = Mux(mshrLd2RespFire, VecInit(mshrLd2Off)(mshrInstallIdx), mshrRfOff)
  io.ldMshrError := Mux(mshrLd2RespFire,mshrError(mshrInstallIdx),io.axiRetError)
  io.ldError := state === sUcResp && ucError
  io.ldMshrDataOk := mshrRespFire | mshrLd2RespFire
  io.ldMshrRdata := shapeData(mshrSelectedWord, mshrSelectedOp, mshrSelectedOff)
  io.ldMshrRobid := Mux(mshrLd2RespFire, VecInit(mshrLd2Robid)(mshrInstallIdx), VecInit(mshrRobid)(axiMshrGrant))

  // ---------------- 响应输出 ----------------
  io.ldDataOk := (lkLdHit | (state === sUcResp)) && !(reqLdKilled || io.ldCancel)
  val frontLdWord = Mux(state === sUcResp, ucRdata, hitWordS32)
  io.ldRdata := shapeData(frontLdWord, reqLdOp, reqPaddr(1, 0))
  io.ldPairDataOk := lkLdHit && reqPairValid && pairHitAny && !(reqLdKilled || io.ldCancel)
  val pairMissNow = reqPairValid && !(reqLdKilled || io.ldCancel) &&
    (lkLdAlloc || lkLdMerge || (lkLdHit && !pairHitAny))
  io.ldPairMiss := pairMissNow
  io.ldPairRdata := hitPairWord
  io.ldRespRobid := reqRobid
  io.ldMiss := (lkLdAlloc || lkLdMerge) && !(reqLdKilled || io.ldCancel)

  io.stDone := lkStHit | lkStAlloc | lkStMerge | ((state === sUcWreq) && io.axiWrRdy)

  // ---------------- 下层读通道 ----------------
  val mshrOwnerRreq = axiMshrGrantVld && (mshrStateV(axiMshrGrant) === mRreq)
  val mshrRdSameLineBlk = mshrOwnerRreq && (wbValid || (wbState =/= wIdle)) &&
    (wbAddr(31, CACHE_LINE_W) === mshrAxiLine)
  io.axiRdReq := (mshrOwnerRreq && !mshrRdSameLineBlk) || (state === sUcRreq)
  io.axiRdType := Mux(mshrOwnerRreq, "b100".U, reqSize)
  io.axiRdAddr := Mux(mshrOwnerRreq, Cat(mshrAxiLine, 0.U(CACHE_LINE_W.W)), reqPaddr)

  // ---------------- 下层写通道 ----------------
  io.axiWrReq := (wbState === wB0) || (wbState === wB1) || (state === sFlushWb0) ||
    (state === sFlushWb1) || (state === sUcWreq)
  io.axiWrType := Mux(state === sUcWreq, reqSize, "b100".U)
  io.axiWrAddr := Mux(state === sUcWreq, reqPaddr,
    Mux((state === sFlushWb0) || (state === sFlushWb1), Cat(cwbTag, reqSet, 0.U(CACHE_LINE_W.W)), wbAddr))
  io.axiWrData := Mux(state === sUcWreq, Cat(0.U(96.W), reqWdata),
    Mux(state === sFlushWb0, cwbLine(127, 0),
      Mux(state === sFlushWb1, cwbLine(255, 128),
        Mux(wbState === wB0, wbLine(127, 0), wbLine(255, 128)))))
  io.axiWrStrb := Mux(state === sUcWreq, reqWstrb, "hf".U)
  io.axiWrWriteThrough := (state === sFlushWb0) || (state === sFlushWb1)

  // ---------------- BRAM 读写控制 ----------------
  val rdSetIdle = Mux(flushTake, flushPendAddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W),
    Mux(stTake, io.stPaddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W),
      io.ldPaddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W)))

  ramRe := !metaIniting && ((state === sIdle) || (state === sRelook) || lookupLdChain)
  ramPairRe := false.B
  for (w <- 0 until NWAY) ramWe(w) := false.B
  for (w <- 0 until NWAY) tagWe(w) := false.B
  ramAddr := Mux(state === sLookup, reqSet, rdSetIdle)
  ramPairAddr := io.ldPairPaddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W)
  ramWline := mshrInstLine
  tagWaddr := ramAddr
  tagWdata := 0.U
  when(metaIniting) {
    for (w <- 0 until NWAY) tagWe(w) := true.B
    tagWaddr := metaInitSet
  }.elsewhen(lkStHit) {
    tagWe(hitWay) := true.B
    tagWaddr := reqSet
    tagWdata := Cat(1.U(1.W), 1.U(1.W), tagRdV(hitWay))
  }.elsewhen(mshrInstallFire) {
    tagWe(mshrInstWay) := true.B
    tagWaddr := mshrInstSet
    tagWdata := Cat(mshrInstIsSt, 1.U(1.W), mshrInstTag)
  }.elsewhen(lkFlush) {
    tagWe(flushReqWay) := true.B
    tagWaddr := flushReqSet
  }
  when(lkStHit) {
    ramWe(hitWay) := true.B
    ramAddr := reqSet
  }.elsewhen(mshrInstallFire) {
    ramWe(mshrInstWay) := true.B
    ramAddr := mshrInstSet
    ramWline := mshrInstLine
  }.elsewhen(state === sRelook) {
    ramAddr := reqSet
    ramPairRe := reqPairValid
    ramPairAddr := reqPairSet
  }.elsewhen(stTake || ldTake || flushTake) {
    ramAddr := rdSetIdle
    ramPairRe := ldTake && io.ldPairValid
    ramPairAddr := io.ldPairPaddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W)
  }

  val ramWriteBytes = VecInit((0 until 32).map(b => ramWline(b * 8 + 7, b * 8)))
  val storeWriteBytes = VecInit((0 until 32).map(b => reqDataLine(b * 8 + 7, b * 8)))
  val fullWriteMask = VecInit(Seq.fill(32)(true.B))
  val storeWriteMask = VecInit(reqStbLine.asBools)
  for (w <- 0 until NWAY) {
    when(ramWe(w)) {
      dataMem(w).write(ramAddr,
        Mux(lkStHit, storeWriteBytes, ramWriteBytes),
        Mux(lkStHit, storeWriteMask, fullWriteMask))
    }.elsewhen(ramRe) { dataOut(w) := dataMem(w)(ramAddr).asUInt }
    when(ramPairRe) { pairDataOut(w) := dataMem(w)(ramPairAddr).asUInt }
  }

  // ================= 时序逻辑 =================
  // 默认清零（先于覆盖）
  fullFlushDoneR := false.B

  when(reset.asBool) {
    metaIniting := true.B
    metaInitSet := 0.U
  }.elsewhen(metaIniting) {
    when(metaInitSet === (NSET - 1).U) { metaIniting := false.B }
      .otherwise { metaInitSet := metaInitSet + 1.U }
  }

  // fence / cancel / install-fire 覆盖
  when(io.fenceI) {
    flushPend := true.B
    flushPendAddr := 0.U
    fullFlushSet := 0.U
    fullFlushWay := 0.U
  }
  when(io.ldCancel) {
    when(reqIsLd && (state =/= sIdle)) { reqLdKilled := true.B }
    when(pendValid && pendIsLd) { pendLdKilled := true.B }
  }
  private def latchStore(): Unit = {
    reqIsFlush := false.B; reqIsSt := true.B; reqIsLd := false.B
    reqLdKilled := false.B
    reqPaddr := io.stPaddr
    reqMshrLineMatchR := stTakeLineMatch
    reqChainSafe := false.B
    reqWdata := io.stData; reqWstrb := io.stStrb; reqSize := io.stSize
    reqUncached := io.stUncached
    reqPairValid := false.B
  }
  private def latchLoad(): Unit = {
    reqIsFlush := false.B; reqIsSt := false.B; reqIsLd := true.B
    reqLdKilled := io.ldCancel
    reqPaddr := io.ldPaddr
    reqMshrLineMatchR := ldTakeLineMatch
    reqChainSafe := !io.ldUncached && !(ldTakeSetMatch.orR)
    reqRobid := io.ldRobid
    reqSize := io.ldSize; reqLdOp := io.ldOp
    reqUncached := io.ldUncached
    reqPairValid := io.ldPairValid
    reqPairWord := io.ldPairWord
    reqPairPaddr := io.ldPairPaddr
  }
  private def latchFlush(): Unit = {
    reqIsFlush := true.B; reqIsSt := false.B; reqIsLd := false.B
    reqLdKilled := false.B
    reqUncached := false.B
    reqPairValid := false.B
    reqPaddr := flushPendAddr
    reqMshrLineMatchR := 0.U
    reqChainSafe := false.B
    flushPend := false.B
  }
  switch(state) {
    is(sIdle) {
      when(pendDrain) {
        reqIsFlush := false.B
        reqIsSt := pendIsSt; reqIsLd := pendIsLd
        reqLdKilled := pendLdKilled | (pendIsLd && io.ldCancel)
        reqPaddr := pendPaddr
        reqMshrLineMatchR := 0.U
        reqChainSafe := pendIsLd && !pendUncached
        reqRobid := pendRobid
        reqWdata := pendWdata; reqWstrb := pendWstrb; reqSize := pendSize
        reqLdOp := pendLdOp; reqUncached := pendUncached
        reqPairValid := pendPairValid; reqPairWord := pendPairWord; reqPairPaddr := pendPairPaddr
        pendValid := false.B
        pendLdKilled := false.B
        pendPairValid := false.B
        state := sRelook
      }.elsewhen(flushTake) {
        latchFlush(); state := sLookup
      }.elsewhen(stTake) {
        latchStore(); state := sLookup
      }.elsewhen(ldTake) {
        latchLoad(); state := sLookup
      }
    }

    is(sLookup) {
      when(lkFlushWait) {
        state := sMwait
      }.elsewhen(lkToPend) {
        pendValid := true.B
        pendIsSt := reqIsSt; pendIsLd := reqIsLd
        pendLdKilled := reqIsLd && (reqLdKilled || io.ldCancel)
        pendPaddr := reqPaddr; pendRobid := reqRobid
        pendWdata := reqWdata; pendWstrb := reqWstrb; pendSize := reqSize
        pendLdOp := reqLdOp; pendUncached := reqUncached
        pendPairValid := reqPairValid; pendPairWord := reqPairWord; pendPairPaddr := reqPairPaddr
        reqLdKilled := false.B
        state := sIdle
      }.elsewhen(lkToMwaitCache) {
        state := sMwait
      }.elsewhen(lkFlush) {
        when(VecInit(reqValidVec.asBools)(flushReqWay) && VecInit(reqDirtyVecEff.asBools)(flushReqWay)) {
          cwbWay := flushReqWay
          state := sFlushCapture
        }.otherwise {
          when(fullFlushLast) {
            fullFlushDoneR := true.B
          }.otherwise {
            fullFlushSet := fullFlushNextSet
            fullFlushWay := fullFlushNextWay
            flushPend := true.B
            flushPendAddr := fullFlushNextAddr
          }
          state := sIdle
        }
      }.elsewhen(lkUcLd) {
        state := Mux(lkUcOk, sUcRreq, sMwait)
      }.elsewhen(lkUcSt) {
        state := Mux(lkUcOk, sUcWreq, sMwait)
      }.elsewhen(lkStMerge) {
        reqLdKilled := false.B
        state := sIdle
      }.elsewhen(lkLdMerge) {
        reqLdKilled := false.B
        reqPairValid := false.B
        state := sIdle
      }.elsewhen(lkLdHit && !(reqLdKilled || io.ldCancel) && !io.ldRespReady) {
        state := sLookup
      }.elsewhen(lkLdHit || lkStHit) {
        when(flushTake) { latchFlush(); state := sLookup }
          .elsewhen(stTake) { latchStore(); state := sLookup }
          .elsewhen(ldTake) { latchLoad(); state := sLookup }
          .otherwise {
            reqLdKilled := false.B
            reqPairValid := false.B
            state := sIdle
          }
      }.elsewhen(mshrAllocBase) {
        reqLdKilled := false.B
        state := sIdle
      }.otherwise {
        state := sMwait
      }
    }

    is(sMwait) {
      when(!mshrAnyBusy && wbAllIdle) {
        reqMshrLineMatchR := 0.U
        reqChainSafe := reqIsLd && !reqUncached
        state := sRelook
      }
    }

    is(sRelook) { state := sLookup }

    is(sUcRreq) { when(io.axiRdRdy) { state := sUcRdata } }
    is(sUcRdata) {
      when(io.axiRetValid) {
        ucRdata := io.axiRetData(31, 0)
        ucError := io.axiRetError
        state := sUcResp
      }
    }
    is(sUcResp) {
      when((reqLdKilled || io.ldCancel) || io.ldRespReady) {
        reqLdKilled := false.B
        state := sIdle
      }
    }

    is(sUcWreq) { when(io.axiWrRdy) { state := sIdle } }

    is(sFlushCapture) {
      cwbTag := tagRdV(cwbWay)
      cwbLine := dataOutV(cwbWay)
      state := sFlushWb0
    }
    is(sFlushWb0) { when(io.axiWrRdy) { state := sFlushWb1 } }
    is(sFlushWb1) {
      state := sIdle
      when(fullFlushLast) {
        fullFlushDoneR := true.B
      }.otherwise {
        fullFlushSet := fullFlushNextSet
        fullFlushWay := fullFlushNextWay
        flushPend := true.B
        flushPendAddr := fullFlushNextAddr
      }
    }
  }

  // ---------------- MSHR 引擎 + AXI owner ----------------
  val mshrAlloc = lkLdAlloc | lkStAlloc
  when(axiMshrHold) {
    when((mshrStateV(axiMshrId) === mRdata) && mshrBeat1) { axiMshrHold := false.B }
      .elsewhen(mshrStateV(axiMshrId) === mIdle) { axiMshrHold := false.B }
  }.elsewhen(mshrOwnerRreq && io.axiRdRdy && !mshrRdSameLineBlk) {
    axiMshrHold := true.B
    axiMshrId := axiMshrGrant
  }

  for (mi <- 0 until N_MSHR) {
    when(io.ldCancel) {
      mshrLdRespPend(mi) := false.B
      mshrLd2Pend(mi) := false.B
    }
    when(lkLdMerge && !(reqLdKilled || io.ldCancel) && (mshrLdMergeIdx === mi.U)) {
      mshrLd2Pend(mi) := true.B
      mshrLd2Robid(mi) := reqRobid
      mshrLd2Word(mi) := reqPaddr(4, 2)
      mshrLd2Off(mi) := reqPaddr(1, 0)
      mshrLd2Op(mi) := reqLdOp
    }
    when(mshrLd2RespFire && (mshrInstallIdx === mi.U)) { mshrLd2Pend(mi) := false.B }

    switch(mshrState(mi)) {
      is(mIdle) {
        mshrLine(mi) := Mux(reqIsSt, reqDataLine, 0.U)
        when(mshrAlloc && (mshrFreeIdx === mi.U)) {
          mshrIsSt(mi) := reqIsSt
          mshrFromLd(mi) := reqIsLd
          mshrLdRespPend(mi) := reqIsLd && !(reqLdKilled || io.ldCancel)
          mshrError(mi) := false.B
          mshrPaddr(mi) := reqPaddr
          mshrRobid(mi) := reqRobid
          mshrLdOp(mi) := reqLdOp
          mshrLd2Pend(mi) := false.B
          mshrWay(mi) := pickWay
          when(reqIsSt) { mshrStbLine(mi) := reqStbLine }
            .otherwise { mshrStbLine(mi) := 0.U }
          mshrState(mi) := mRreq
        }
      }
      is(mRreq) {
        when(io.axiRdRdy && !mshrRdSameLineBlk && axiMshrGrantVld && (axiMshrGrant === mi.U)) {
          mshrState(mi) := mRdata
        }
        when(lkStMerge && (mshrMergeIdx === mi.U)) {
          mshrStbLine(mi) := mshrStbLine(mi) | reqStbLine
          mshrLine(mi) := mergeStoreBytes(mshrLine(mi))
        }
      }
      is(mRdata) {
        when(mshrRespFire && (axiMshrGrant === mi.U)) { mshrLdRespPend(mi) := false.B }
        when(mshrBeat0 && (axiMshrGrant === mi.U)) { mshrB0(mi) := io.axiRetData }
        when(lkStMerge && (mshrMergeIdx === mi.U)) {
          mshrStbLine(mi) := mshrStbLine(mi) | reqStbLine
          when(!(mshrBeat1 && (axiMshrGrant === mi.U))) {
            mshrLine(mi) := mergeStoreBytes(mshrLine(mi))
          }
        }
        when(mshrBeat1 && (axiMshrGrant === mi.U)) {
          mshrError(mi) := io.axiRetError
          mshrLine(mi) := refillLineMerged
          mshrState(mi) := mInstall
        }
      }
      is(mInstall) {
        when(lkStMerge && (mshrMergeIdx === mi.U)) {
          mshrStbLine(mi) := mshrStbLine(mi) | reqStbLine
          mshrLine(mi) := mergeStoreBytes(mshrLine(mi))
        }
        when(mshrInstallFireOh(mi)) {
          mshrState(mi) := mIdle
          mshrFromLd(mi) := false.B
          mshrLd2Pend(mi) := false.B
        }
      }
    }
  }

  // ---------------- 写回缓冲排空引擎 ----------------
  val frontWrBusy = (state === sUcWreq) || (state === sFlushWb0) || (state === sFlushWb1)
  switch(wbState) {
    is(wIdle) { when(wbValid && !frontWrBusy) { wbState := wB0 } }
    is(wB0) { when(io.axiWrRdy) { wbState := wB1 } }
    is(wB1) {
      wbState := wIdle
      wbValid := false.B
    }
  }
  when(mshrAlloc && missNeedWb) {
    wbValid := true.B
    wbAddr := Cat(tagRdV(pickWay), reqSet, 0.U(CACHE_LINE_W.W))
    wbLine := dataOutV(pickWay)
  }
  io.quiescent := !metaIniting && state === sIdle && !pendValid && !mshrAnyBusy && wbAllIdle
}
