// L2Cache: 1路×512组×32B 写回统一缓存（I$/D$ 共享）。
// 移植自 cpu/l2cache.v。要点：
// - 主 FSM 15 态：行写两拍捕获、LOOKUP 比对、victim 脏写回、D 侧内联重填
//   （重填数据流式直推 D$，不再 RET 重放）、uncached 旁路、FENCE.I 写穿；
// - I-miss 引擎（mem2 口）：I 侧 miss 移交后台重填，与 D 流量并行；
// - victim buffer 4 项全相联（行写 miss 直通内存同时旁挂；行读 miss 先查 VB）；
// - I next-line 预取 + 连续两 D miss 训练的 D-stream 预取（只在全空闲拍查表）；
// - 同组冲突阻塞：引擎在飞期间同 index 新请求不接受。
package e91c.mem

import chisel3._
import chisel3.util.{switch, is, Cat, Fill, OHToUInt, PopCount}
import e91c.config.Params._

class L2Cache extends Module {
  val io = IO(new Bundle {
    val icRdReq = Input(Bool()); val icRdType = Input(UInt(3.W)); val icRdAddr = Input(UInt(32.W))
    val icRdRdy = Output(Bool())
    val icRetError = Output(Bool())
    val icRetValid = Output(Bool()); val icRetLast = Output(Bool()); val icRetData = Output(UInt(128.W))

    val dcRdReq = Input(Bool()); val dcRdType = Input(UInt(3.W)); val dcRdAddr = Input(UInt(32.W))
    val dcRdRdy = Output(Bool())
    val dcRetError = Output(Bool())
    val dcRetValid = Output(Bool()); val dcRetLast = Output(Bool()); val dcRetData = Output(UInt(128.W))

    val dcWrReq = Input(Bool()); val dcWrType = Input(UInt(3.W)); val dcWrAddr = Input(UInt(32.W))
    val dcWrStrb = Input(UInt(4.W)); val dcWrData = Input(UInt(128.W))
    val dcWrWriteThrough = Input(Bool())
    val dcWrRdy = Output(Bool())

    // 下游读口 0（D 侧/旁路）
    val memRdReq = Output(Bool()); val memRdType = Output(UInt(3.W)); val memRdAddr = Output(UInt(32.W))
    val memRdRdy = Input(Bool())
    val memRetError = Input(Bool())
    val memRetValid = Input(Bool()); val memRetLast = Input(Bool()); val memRetData = Input(UInt(128.W))

    // 下游读口 1（I-miss 引擎专用）
    val mem2RdReq = Output(Bool()); val mem2RdType = Output(UInt(3.W)); val mem2RdAddr = Output(UInt(32.W))
    val mem2RdRdy = Input(Bool())
    val mem2RetError = Input(Bool())
    val mem2RetValid = Input(Bool()); val mem2RetLast = Input(Bool()); val mem2RetData = Input(UInt(128.W))

    // 下游写口
    val memWrReq = Output(Bool()); val memWrType = Output(UInt(3.W)); val memWrAddr = Output(UInt(32.W))
    val memWrStrb = Output(UInt(4.W)); val memWrData = Output(UInt(128.W))
    val memWrRdy = Input(Bool())
  })

  private val NWAY = L2_NWAY; private val NSET = L2_NSET
  require(NWAY == 1 || NWAY == 2)
  private val IDXW = L2_INDEX_W; private val TAGW = L2_TAG_W; private val LINEW = CACHE_LINE_BITS
  private val VBN = 4

  // ---------------- 主 FSM 状态 ----------------
  private def st(i: Int) = i.U(4.W)
  val sIdle = st(0); val sWcap = st(1); val sLookup = st(2); val sMwb0 = st(3)
  val sMwb1 = st(4); val sMrreq = st(5); val sMrdata = st(6); val sRet0 = st(7)
  val sRet1 = st(8); val sWfwd0 = st(9); val sWfwd1 = st(10); val sBypRreq = st(11)
  val sBypRdata = st(12); val sBypRet = st(13); val sBypWreq = st(14)
  val state = RegInit(sIdle)

  // ---------------- I-miss 引擎 ----------------
  private def ims(i: Int) = i.U(3.W)
  val imIdle = ims(0); val imRreq = ims(1); val imRdata = ims(2)
  val imInstall = ims(3); val imRet0 = ims(4); val imRet1 = ims(5)
  val imState = RegInit(imIdle)
  val imAttach = RegInit(false.B)
  val imLineAddr = Reg(UInt(27.W))
  val imWayR = RegInit(false.B)
  val imB0 = Reg(UInt(128.W))
  val imLine = Reg(UInt(LINEW.W))

  val imBusy = imState =/= imIdle
  val imSet = imLineAddr(IDXW + CACHE_LINE_W - 1 - 5, CACHE_LINE_W - 5)
  val imTag = imLineAddr(26, IDXW + CACHE_LINE_W - 5)

  // ---------------- 存储：每路 tag + data（单口同步 RAM 语义）----------------
  val tagMem = Seq.fill(NWAY)(Mem(NSET, UInt((TAGW + 2).W)))
  val dataMem = Seq.fill(NWAY)(Mem(NSET, UInt(LINEW.W)))
  val tagOut = Seq.fill(NWAY)(Reg(UInt((TAGW + 2).W)))
  val dataOut = Seq.fill(NWAY)(Reg(UInt(LINEW.W)))

  val ramAddr = Wire(UInt(IDXW.W))
  val ramRe = Wire(Bool())
  val tagWe = Seq.fill(NWAY)(Wire(Bool()))
  val dataWe = Seq.fill(NWAY)(Wire(Bool()))
  val tagWdata = Wire(UInt((TAGW + 2).W))
  val dataWdata = Wire(UInt(LINEW.W))

  val initing = RegInit(true.B)
  val initSet = RegInit(0.U(IDXW.W))

  // ---------------- 请求锁存 ----------------
  val reqIsIc = Reg(Bool()); val reqIsRd = Reg(Bool()); val reqIsLine = Reg(Bool()); val reqIsPf = Reg(Bool())
  val reqWriteThrough = Reg(Bool())
  val reqAddr = Reg(UInt(32.W)); val reqType = Reg(UInt(3.W))
  val reqWline = Reg(UInt(LINEW.W))
  val ucWdata = Reg(UInt(128.W)); val ucStrb = Reg(UInt(4.W))

  val reqSet = reqAddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W)
  val reqTag = reqAddr(31, IDXW + CACHE_LINE_W)

  // ---------------- 命中判定（LOOKUP 拍）----------------
  val wayHit = VecInit((0 until NWAY).map(w => tagOut(w)(TAGW + 1) && tagOut(w)(TAGW - 1, 0) === reqTag))
  val hitAny = wayHit.asUInt.orR
  val hitWay = if (NWAY == 1) false.B else wayHit(1)

  val rrBit = RegInit(false.B)
  val pickWay = if (NWAY == 1) false.B else Mux(!tagOut(0)(TAGW + 1), false.B, Mux(!tagOut(NWAY - 1)(TAGW + 1), true.B, rrBit))
  val pickValid = Mux(pickWay, tagOut(NWAY - 1)(TAGW + 1), tagOut(0)(TAGW + 1))
  val pickDirty = Mux(pickWay, tagOut(NWAY - 1)(TAGW), tagOut(0)(TAGW))

  val dataOutV = VecInit(dataOut)   // 硬件索引读

  val victimWayR = Reg(Bool())
  val victimTagR = Reg(UInt(TAGW.W))
  val mainLine = Reg(UInt(LINEW.W))
  val victimLineR = mainLine

  val bypError = RegInit(false.B)
  val imError = RegInit(false.B)
  val refillB0 = Reg(UInt(128.W))
  val retLine = mainLine
  val bypData = Reg(UInt(128.W))

  // ---------------- victim buffer ----------------
  val vbValid = Seq.fill(VBN)(RegInit(false.B))
  val vbAddr = Seq.fill(VBN)(Reg(UInt(27.W)))
  val vbData = Mem(VBN, UInt(LINEW.W))
  val vbPtr = RegInit(0.U(2.W))

  val reqLineKey = reqAddr(31, 5)
  val vbHitVec = VecInit((0 until VBN).map(v => vbValid(v) && vbAddr(v) === reqLineKey)).asUInt
  val vbHit = vbHitVec.orR
  val vbHitLine = Wire(UInt(LINEW.W))
  vbHitLine := Mux(vbHit, vbData(OHToUInt(vbHitVec)), 0.U(LINEW.W))

  // ---------------- 预取武装 ----------------
  val pfArmed = RegInit(false.B)
  val pfIsD = RegInit(false.B)
  val pfAddr = RegInit(0.U(32.W))
  val lastDMissValid = RegInit(false.B)
  val lastDMissLine = Reg(UInt(27.W))

  val reqNextLine = Cat(reqAddr(31, 5), 0.U(5.W)) + "h20".U(32.W)
  val reqPfOk = reqAddr(11, 5) =/= "h7f".U(7.W)
  val imNextLineAddr = imLineAddr + 1.U(27.W)
  val imNextLine = Cat(imNextLineAddr, 0.U(5.W))
  // imLineAddr stores byte-address [31:5]; original [11:5] becomes [6:0].
  val imPfOk = imLineAddr(6, 0) =/= "h7f".U(7.W)
  val dPfMissEvent = (state === sLookup) && reqIsRd && reqIsLine && !reqIsPf && !reqIsIc && !hitAny && !vbHit
  val dPfStreamMatch = dPfMissEvent && lastDMissValid &&
    reqAddr(31, 5) === (lastDMissLine + 1.U(27.W)) && reqPfOk
  val dPfArmEvent = dPfStreamMatch && (!pfArmed || pfIsD) && !((imState === imRet1) && imPfOk)

  // ---------------- 仲裁（IDLE 拍）----------------
  private def idxOf(a: UInt) = a(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W)
  val wrSetConf = imBusy && idxOf(io.dcWrAddr) === imSet
  val dcrdSetConf = imBusy && idxOf(io.dcRdAddr) === imSet
  val icrdSetConf = imBusy && idxOf(io.icRdAddr) === imSet
  val ramPortBusy = imState === imInstall

  val rrRdDc = RegInit(false.B)
  val grantBase = (state === sIdle) && !initing && !ramPortBusy
  val wrWant = io.dcWrReq && !wrSetConf
  val dcrdWant = io.dcRdReq && !dcrdSetConf
  val icrdWant = io.icRdReq && !icrdSetConf
  val grantWr = grantBase && wrWant
  val grantDcRd = grantBase && !wrWant && dcrdWant && (!icrdWant || rrRdDc)
  val grantIcRd = grantBase && !wrWant && icrdWant && (!dcrdWant || !rrRdDc)
  val grantPf = grantBase && !io.dcWrReq && !io.dcRdReq && !io.icRdReq && pfArmed && !imBusy

  // ---------------- 上行握手 ----------------
  io.dcWrRdy := (grantWr && (io.dcWrType === "b100".U)) |
    ((state === sBypWreq) && io.memWrRdy)
  io.dcRdRdy := grantDcRd

  val lkIcLineRd = (state === sLookup) && reqIsIc && reqIsRd && reqIsLine && !reqIsPf
  val lkImAlloc = lkIcLineRd && !hitAny && !vbHit && !imBusy
  io.icRdRdy := (lkIcLineRd && (hitAny || vbHit)) |
    (lkImAlloc && !(pickValid && pickDirty)) |
    ((state === sMwb1) && reqIsIc && reqIsRd) |
    ((state === sLookup) && reqIsIc && reqIsRd && !reqIsLine)

  // ---------------- 上行返回 ----------------
  val retBeat = (state === sRet0) || (state === sRet1)
  val bypBeat = state === sBypRet
  val dcRefillStream = (state === sMrdata) && !reqIsIc && io.memRetValid
  val mainLineBeat = Mux((state === sRet0) || (state === sMwb0), mainLine(127, 0), mainLine(255, 128))
  val retDataMux = Mux(bypBeat, bypData, mainLineBeat)

  val imRetBeat = (imState === imRet0) || (imState === imRet1)
  val imRetDataMux = Mux(imState === imRet0, imLine(127, 0), imLine(255, 128))

  io.icRetValid := (reqIsIc && (retBeat || bypBeat)) | imRetBeat
  io.icRetLast := (reqIsIc && ((state === sRet1) || bypBeat)) | (imState === imRet1)
  io.icRetData := Mux(imRetBeat, imRetDataMux, retDataMux)
  io.icRetError := Mux(imRetBeat,imError,bypBeat && bypError)

  io.dcRetValid := (!reqIsIc && (retBeat || bypBeat)) || dcRefillStream
  io.dcRetLast := (!reqIsIc && ((state === sRet1) || bypBeat)) || (dcRefillStream && io.memRetLast)
  io.dcRetData := Mux(dcRefillStream, io.memRetData, retDataMux)
  io.dcRetError := Mux(dcRefillStream,io.memRetError,bypBeat && bypError)

  // ---------------- 下游接口 ----------------
  io.memRdReq := (state === sMrreq) || (state === sBypRreq)
  io.memRdType := Mux(state === sMrreq, "b100".U, reqType)
  io.memRdAddr := Mux(state === sMrreq, Cat(reqAddr(31, CACHE_LINE_W), 0.U(CACHE_LINE_W.W)), reqAddr)

  io.mem2RdReq := imState === imRreq
  io.mem2RdType := "b100".U
  io.mem2RdAddr := Cat(imLineAddr, 0.U(CACHE_LINE_W.W))

  io.memWrReq := (state === sMwb0) || (state === sMwb1) || (state === sWfwd0) ||
    (state === sWfwd1) || (state === sBypWreq)
  io.memWrType := Mux(state === sBypWreq, reqType, "b100".U)
  io.memWrAddr := Mux((state === sWfwd0) || (state === sWfwd1),
    Cat(reqAddr(31, CACHE_LINE_W), 0.U(CACHE_LINE_W.W)),
    Mux(state === sBypWreq, reqAddr, Cat(victimTagR, reqSet, 0.U(CACHE_LINE_W.W))))
  io.memWrData := Mux((state === sMwb0) || (state === sMwb1), mainLineBeat,
    Mux(state === sWfwd0, reqWline(127, 0),
    Mux(state === sWfwd1, reqWline(255, 128), ucWdata)))
  io.memWrStrb := Mux(state === sBypWreq, ucStrb, "hf".U)

  // ---------------- BRAM 控制 ----------------
  val idleSet = Mux(grantWr, idxOf(io.dcWrAddr),
    Mux(grantDcRd, idxOf(io.dcRdAddr), Mux(grantIcRd, idxOf(io.icRdAddr), idxOf(pfAddr))))

  val refillWrEn = (state === sMrdata) && io.memRetValid && io.memRetLast && !io.memRetError
  val whitWrEn = (state === sLookup) && !reqIsRd && reqIsLine && hitAny
  val ucwInvalEn = (state === sLookup) && !reqIsRd && !reqIsLine && hitAny
  val imInstallFire = (imState === imInstall) && !imError && !initing &&
    !refillWrEn && !whitWrEn && !ucwInvalEn &&
    (state =/= sWcap) &&
    !(grantWr || grantDcRd || grantIcRd || grantPf)

  ramAddr := idleSet
  ramRe := false.B
  for (w <- 0 until NWAY) { tagWe(w) := false.B; dataWe(w) := false.B }
  tagWdata := Cat(1.U(1.W), 0.U(1.W), reqTag)
  dataWdata := Cat(io.memRetData, refillB0)

  when(initing) {
    ramAddr := initSet
    for (w <- 0 until NWAY) tagWe(w) := true.B
    tagWdata := 0.U
  }.elsewhen(imInstallFire) {
    ramAddr := imSet
    dataWdata := imLine
    tagWdata := Cat(1.U(1.W), 0.U(1.W), imTag)
    when(!imWayR) { dataWe(0) := true.B; tagWe(0) := true.B }
      .otherwise { dataWe(NWAY - 1) := true.B; tagWe(NWAY - 1) := true.B }
  }.elsewhen(whitWrEn) {
    ramAddr := reqSet
    dataWdata := reqWline
    tagWdata := Cat(1.U(1.W), ~reqWriteThrough, reqTag)
    when(!hitWay) { dataWe(0) := true.B; tagWe(0) := true.B }
      .otherwise { dataWe(NWAY - 1) := true.B; tagWe(NWAY - 1) := true.B }
  }.elsewhen(ucwInvalEn) {
    ramAddr := reqSet
    tagWdata := 0.U
    when(!hitWay) { tagWe(0) := true.B } .otherwise { tagWe(NWAY - 1) := true.B }
  }.elsewhen(refillWrEn) {
    ramAddr := reqSet
    dataWdata := Cat(io.memRetData, refillB0)
    tagWdata := Cat(1.U(1.W), 0.U(1.W), reqTag)
    when(!victimWayR) { dataWe(0) := true.B; tagWe(0) := true.B }
      .otherwise { dataWe(NWAY - 1) := true.B; tagWe(NWAY - 1) := true.B }
  }.elsewhen((grantWr && (io.dcWrType === "b100".U)) || grantDcRd || grantIcRd || grantPf) {
    ramRe := true.B
    ramAddr := idleSet
  }.elsewhen(grantWr) {
    ramRe := true.B
    ramAddr := idleSet
  }.elsewhen(state === sWcap) {
    ramRe := true.B
    ramAddr := reqSet
  }

  for (w <- 0 until NWAY) {
    when(tagWe(w)) { tagMem(w)(ramAddr) := tagWdata }
      .elsewhen(ramRe) { tagOut(w) := tagMem(w)(ramAddr) }
    when(dataWe(w)) { dataMem(w)(ramAddr) := dataWdata }
      .elsewhen(ramRe) { dataOut(w) := dataMem(w)(ramAddr) }
  }

  // ---------------- victim buffer 更新 ----------------
  val vbInstallEn = (state === sLookup) && !reqIsRd && reqIsLine && !hitAny
  val imLineKey = imLineAddr
  val refillLineKey = reqAddr(31, 5)
  val vbClrIm = VecInit((0 until VBN).map(v => imInstallFire && vbValid(v) && vbAddr(v) === imLineKey))
  val vbClrRefill = VecInit((0 until VBN).map(v => refillWrEn && vbValid(v) && vbAddr(v) === refillLineKey))
  val vbClrUcw = VecInit((0 until VBN).map(v =>
    (state === sLookup) && !reqIsRd && !reqIsLine && vbValid(v) && vbAddr(v) === reqLineKey))

  for (v <- 0 until VBN) {
    vbValid(v) := vbValid(v) && !(vbClrIm(v) || vbClrRefill(v) || vbClrUcw(v))
  }
  when(vbInstallEn) {
    when(vbHit) {
      // Shared data write port below updates the uniquely matching slot.
    }.otherwise {
      for (v <- 0 until VBN) when(vbPtr === v.U) {
        vbValid(v) := true.B
        vbAddr(v) := reqLineKey
      }
      vbPtr := vbPtr + 1.U
    }
  }

  val vbWriteIndex = Mux(vbHit, OHToUInt(vbHitVec), vbPtr)
  when(vbInstallEn) { vbData(vbWriteIndex) := reqWline }
  if (!sys.props.get("e91c.synthesis").contains("true")) {
    val referenceData = Seq.fill(VBN)(Reg(UInt(LINEW.W)))
    when(vbInstallEn) {
      when(vbHit) {
        for (v <- 0 until VBN) when(vbHitVec(v)) { referenceData(v) := reqWline }
      }.otherwise {
        for (v <- 0 until VBN) when(vbPtr === v.U) { referenceData(v) := reqWline }
      }
    }
    val referenceLine = (0 until VBN).map(v => Mux(vbHitVec(v), referenceData(v), 0.U))
      .foldLeft(0.U(LINEW.W))(_ | _)
    val checkArmed = RegNext(true.B, false.B)
    when(checkArmed) {
      assert(PopCount(vbHitVec) <= 1.U, "duplicate L2 victim buffer address")
      when(vbHit) { assert(vbHitLine === referenceLine, "L2 victim data storage mismatch") }
    }
  }

  // ---------------- 主 FSM ----------------
  switch(state) {
    is(sIdle) {
      when(grantWr) {
        reqIsRd := false.B
        reqIsPf := false.B
        reqIsLine := io.dcWrType === "b100".U
        reqWriteThrough := io.dcWrWriteThrough
        reqAddr := io.dcWrAddr
        reqType := io.dcWrType
        when(io.dcWrType === "b100".U) {
          reqWline := Cat(0.U(128.W), io.dcWrData)
          state := sWcap
        }.otherwise {
          ucWdata := io.dcWrData
          ucStrb := io.dcWrStrb
          state := sLookup
        }
      }.elsewhen(grantDcRd || grantIcRd) {
        reqIsRd := true.B
        reqIsPf := false.B
        reqWriteThrough := false.B
        reqIsIc := grantIcRd
        rrRdDc := grantIcRd
        reqIsLine := Mux(grantIcRd, io.icRdType === "b100".U, io.dcRdType === "b100".U)
        reqAddr := Mux(grantIcRd, io.icRdAddr, io.dcRdAddr)
        reqType := Mux(grantIcRd, io.icRdType, io.dcRdType)
        state := sLookup
      }.elsewhen(grantPf) {
        reqIsRd := true.B
        reqIsPf := true.B
        reqWriteThrough := false.B
        reqIsIc := true.B
        reqIsLine := true.B
        reqAddr := pfAddr
        reqType := "b100".U
        pfArmed := false.B
        state := sLookup
      }
    }

    is(sWcap) {
      reqWline := Cat(io.dcWrData, reqWline(127, 0))
      state := sLookup
    }

    is(sLookup) {
      when(!reqIsRd) {
        when(!reqIsLine) {
          state := sBypWreq
        }.elsewhen(reqWriteThrough) {
          state := sWfwd0
        }.otherwise {
          state := Mux(hitAny, sIdle, sWfwd0)
        }
      }.elsewhen(!reqIsLine) {
        state := sBypRreq
      }.elsewhen(reqIsPf) {
        when(!hitAny && !vbHit && !imBusy && !(pickValid && pickDirty)) {
          rrBit := ~rrBit
        }
        state := sIdle
      }.elsewhen(hitAny) {
        retLine := dataOutV(hitWay)
        when(reqIsIc && reqPfOk) {
          pfArmed := true.B
          pfIsD := false.B
          pfAddr := reqNextLine
        }
        state := sRet0
      }.elsewhen(vbHit) {
        retLine := vbHitLine
        when(reqIsIc && reqPfOk) {
          pfArmed := true.B
          pfIsD := false.B
          pfAddr := reqNextLine
        }
        state := sRet0
      }.elsewhen(reqIsIc) {
        victimWayR := pickWay
        victimTagR := Mux(pickWay, tagOut(NWAY - 1)(TAGW - 1, 0), tagOut(0)(TAGW - 1, 0))
        victimLineR := dataOutV(pickWay)
        when(imBusy) {
          state := sIdle
        }.elsewhen(pickValid && pickDirty) {
          rrBit := ~rrBit
          state := sMwb0
        }.otherwise {
          rrBit := ~rrBit
          state := sIdle
        }
      }.otherwise {
        victimWayR := pickWay
        victimTagR := Mux(pickWay, tagOut(NWAY - 1)(TAGW - 1, 0), tagOut(0)(TAGW - 1, 0))
        victimLineR := dataOutV(pickWay)
        rrBit := ~rrBit
        when(pickValid && pickDirty) { state := sMwb0 } .otherwise { state := sMrreq }
      }
    }

    is(sMwb0) { when(io.memWrRdy) { state := sMwb1 } }
    is(sMwb1) { state := Mux(reqIsIc && reqIsRd, sIdle, sMrreq) }

    is(sMrreq) { when(io.memRdRdy) { state := sMrdata } }
    is(sMrdata) {
      when(io.memRetValid) {
        when(io.memRetLast) {
          retLine := Cat(io.memRetData, refillB0)
          state := sIdle
        }.otherwise {
          refillB0 := io.memRetData
        }
      }
    }

    is(sRet0) { state := sRet1 }
    is(sRet1) { state := sIdle }

    is(sWfwd0) { when(io.memWrRdy) { state := sWfwd1 } }
    is(sWfwd1) { state := sIdle }

    is(sBypRreq) { when(io.memRdRdy) { state := sBypRdata } }
    is(sBypRdata) {
      when(io.memRetValid) {
        bypData := io.memRetData
        bypError := io.memRetError
        state := sBypRet
      }
    }
    is(sBypRet) { state := sIdle }

    is(sBypWreq) { when(io.memWrRdy) { state := sIdle } }
  }

  // （case 之后同拍覆盖优先）
  when((imState === imRet1) && imPfOk) {
    pfArmed := true.B
    pfIsD := false.B
    pfAddr := imNextLine
  }
  when(dPfMissEvent) {
    when(dPfArmEvent) {
      pfArmed := true.B
      pfIsD := true.B
      pfAddr := reqNextLine
    }
    lastDMissValid := true.B
    lastDMissLine := reqAddr(31, 5)
  }

  // init：逐组清 tag valid
  when(initing) {
    initSet := initSet + 1.U
    when(initSet === Fill(IDXW, 1.B)) { initing := false.B }
  }

  // ---------------- I-miss 引擎 ----------------
  val imAllocDemandClean = lkImAlloc && !(pickValid && pickDirty)
  val imAllocDemandWb = (state === sMwb1) && reqIsIc && reqIsRd
  val imAllocPf = (state === sLookup) && reqIsPf && !hitAny && !vbHit && !imBusy && !(pickValid && pickDirty)
  val imAlloc = imAllocDemandClean | imAllocDemandWb | imAllocPf

  switch(imState) {
    is(imIdle) {
      when(imAlloc) {
        imLineAddr := reqAddr(31, 5)
        imError := false.B
        imWayR := Mux(imAllocDemandWb, victimWayR, pickWay)
        imAttach := !imAllocPf
        imState := imRreq
      }
    }
    is(imRreq) { when(io.mem2RdRdy) { imState := imRdata } }
    is(imRdata) {
      when(io.mem2RetValid) {
        imError := imError || io.mem2RetError
        when(io.mem2RetLast) {
          imLine := Cat(io.mem2RetData, imB0)
          imState := imInstall
        }.otherwise {
          imB0 := io.mem2RetData
        }
      }
    }
    is(imInstall) {
      when(imInstallFire || imError) {
        imState := Mux(imAttach, imRet0, imIdle)
      }
    }
    is(imRet0) { imState := imRet1 }
    is(imRet1) {
      imAttach := false.B
      imState := imIdle
    }
  }
  if (!sys.props.get("e91c.synthesis").contains("true")) {
    val oldReturnLine = Reg(UInt(LINEW.W))
    val oldVictimLine = Reg(UInt(LINEW.W))
    when((state === sLookup) && reqIsRd && reqIsLine && !reqIsPf) {
      when(hitAny) { oldReturnLine := dataOutV(hitWay) }
        .elsewhen(vbHit) { oldReturnLine := vbHitLine }
        .otherwise { oldVictimLine := dataOutV(pickWay) }
    }
    when((state === sMrdata) && io.memRetValid && io.memRetLast) {
      oldReturnLine := Cat(io.memRetData, refillB0)
    }
    when((state === sRet0) || (state === sRet1)) {
      assert(mainLine === oldReturnLine, "L2 shared return line mismatch")
    }
    when((state === sMwb0) || (state === sMwb1)) {
      assert(mainLine === oldVictimLine, "L2 shared victim line mismatch")
    }
  }
}




