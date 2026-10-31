// ============================================================
// e91c.frontend.Icache — cpu/icache.v 的 Chisel 移植（L1 指令缓存）
// ------------------------------------------------------------
// 2 路 x 128 组 x 32B 行 = 8KB；
// PIPT（接受拍 paddr 索引 / LOOKUP 拍
// paddr 比 tag）；整行取指；miss 整行读下层（2 拍 128b）；
// uncached 从块起始字逐字拼部分有效行；FENCE.I 一次清全部 valid。
// 移植要点：
// - way 体 = 单口同步 RAM（en 使能读或写，不使能保持）；
// - tag = Mem 异步读（复位不清，valid=0 即无效）；rr_ptr 上电清零；
// - LOOKUP hit / RESP 均为"返回旧请求 + 接受新请求"替换窗口（稳态 1 请求/拍）。
// ============================================================
package e91c.frontend

import chisel3._
import chisel3.util.{Cat, is, switch}
import e91c.config.Params.{CACHE_LINE_BITS, CACHE_LINE_W, ICACHE_NWAY, L1_INDEX_W, L1_NSET, L1_TAG_W}

class Icache(val cacheableOnly: Boolean = false) extends Module {
  val io = IO(new Bundle {
    val ifuReq = Input(Bool())          // 保持至 addr_ok
    val ifuVindex = Input(UInt(L1_INDEX_W.W))
    val ifuPaddr = Input(UInt(32.W))
    val ifuUncached = Input(Bool())
    val ifuAddrOk = Output(Bool())
    val ifuDataOk = Output(Bool())
    val ifuError = Output(Bool())
    val ifuRline = Output(UInt(CACHE_LINE_BITS.W))
    val ifuDecodeLines = Output(Vec(3, UInt(CACHE_LINE_BITS.W)))
    val ifuDecodeSelect = Output(UInt(3.W))
    val invalidate = Input(Bool())
    val axiRdReq = Output(Bool())
    val axiRdType = Output(UInt(3.W))   // 100=行重填 010=单字
    val axiRdAddr = Output(UInt(32.W))
    val axiRdRdy = Input(Bool())
    val axiRetError = Input(Bool())
    val axiRetValid = Input(Bool())
    val axiRetLast = Input(Bool())
    val axiRetData = Input(UInt(128.W))
  })

  val NWAY = 2
  val I_NSET = 128
  val IDXW = 7
  val TAGW = 32 - IDXW - CACHE_LINE_W
  val LINEW = CACHE_LINE_BITS

  val sIdle = 0.U; val sLookup = 1.U; val sRreq = 2.U; val sRdata = 3.U
  val sResp = 4.U; val sUcRreq = 5.U; val sUcRdata = 6.U
  val state = RegInit(sIdle)

  // valid 触发器阵列（一拍判定/失效）
  // Tag and valid share a synchronous read boundary with data.
  val tagMem = Seq.fill(NWAY)(Mem(I_NSET, UInt((TAGW + 1).W)))
  val tagOut = Seq.fill(NWAY)(Reg(UInt((TAGW + 1).W)))
  val clearing = RegInit(true.B)
  val clearSet = RegInit(0.U(IDXW.W))
  // way 体（单口同步 RAM，en 不使能保持）
  val wayMem = Seq.fill(NWAY)(Mem(I_NSET, UInt(LINEW.W)))
  val dataOut = Seq.fill(NWAY)(Reg(UInt(LINEW.W)))

  val reqPaddr = Reg(UInt(32.W))
  val reqUncached = Reg(Bool())
  val invalidatePending = RegInit(false.B)
  val fullInvNow = io.invalidate || invalidatePending || clearing
  val refillKilled = RegInit(false.B)
  val victimWay = Reg(UInt(2.W))
  val refillB0 = Reg(UInt(128.W))
  val responseError = RegInit(false.B)
  val respLine = Reg(UInt(LINEW.W))
  val ucWord = Reg(UInt(3.W))
  val ucLine = Reg(UInt(LINEW.W))

  val reqSet = reqPaddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W)
  val reqTag = reqPaddr(31, IDXW + CACHE_LINE_W)

  val tagRd = tagOut.map(_(TAGW - 1, 0))

  val wayHit = WireDefault(VecInit(Seq.fill(NWAY)(false.B)))
  val wayInvalid = WireDefault(VecInit(Seq.fill(NWAY)(false.B)))
  for (w <- 0 until NWAY) {
    wayHit(w) := tagOut(w)(TAGW) && (tagRd(w) === reqTag)
    wayInvalid(w) := !tagOut(w)(TAGW)
  }
  val hitAny = wayHit.asUInt.orR
  val replaceWay = RegInit(false.B)
  val hitWay = wayHit(1).asUInt
  val pickWay = Mux(wayInvalid(0), 0.U, Mux(wayInvalid(1), 1.U, replaceWay.asUInt))

  val lookupHit = (state === sLookup) && !reqUncached && hitAny && !fullInvNow
  io.ifuDataOk := (lookupHit || (state === sResp)) && !fullInvNow
  val dataOutV = VecInit(dataOut)
  io.ifuRline := Mux(lookupHit, dataOutV(hitWay), respLine)
  // Expose the same three line sources to frontend boundary predecode.
  // Only the small predecode result needs to wait for the tag comparison.
  io.ifuDecodeLines(0) := dataOut(0)
  io.ifuDecodeLines(1) := dataOut(1)
  io.ifuDecodeLines(2) := respLine
  io.ifuDecodeSelect := Cat(!lookupHit, lookupHit && wayHit(1), lookupHit && !wayHit(1))
  io.ifuError := state === sResp && responseError

  val reqWindow = (state === sIdle) || lookupHit || (state === sResp)
  val reqTake = reqWindow && !fullInvNow && io.ifuReq
  io.ifuAddrOk := reqTake
  when(reqTake) { responseError := false.B }

  io.axiRdReq := (state === sRreq) || (!cacheableOnly.B && state === sUcRreq)
  io.axiRdType := Mux(cacheableOnly.B || state === sRreq, "b100".U, "b010".U)
  io.axiRdAddr := Mux(cacheableOnly.B || state === sRreq,
    Cat(reqPaddr(31, CACHE_LINE_W), 0.U(CACHE_LINE_W.W)),
    Cat(reqPaddr(31, CACHE_LINE_W), ucWord, 0.U(2.W)))

  // ---- BRAM 单口控制 ----
  val rdSetIdle = io.ifuPaddr(IDXW + CACHE_LINE_W - 1, CACHE_LINE_W)
  val ramRe = reqTake
  val refillLine = Cat(io.axiRetData, refillB0)
  // Share one pad across both RAM write ports, leaving the response bypass raw.
  // Unit tests and simulation elaboration need no vendor primitive model.
  val refillWriteLow = if (sys.props.get("e91c.synthesis").contains("true")) {
    val refillWritePad = Module(new PangoIdentityPad)
    refillWritePad.io.dataIn := refillB0
    refillWritePad.io.dataOut
  } else refillB0
  val refillWriteLine = Cat(io.axiRetData, refillWriteLow)
  // Each uncached response owns exactly one word; no wide variable shifter.
  val ucNext = VecInit((0 until 8).map(w =>
    Mux(ucWord === w.U, io.axiRetData(31, 0), ucLine(w * 32 + 31, w * 32)))).asUInt
  val refillWr = (state === sRdata) && io.axiRetValid && io.axiRetLast && !io.axiRetError
  val ramAddr = Mux(refillWr, reqSet, rdSetIdle)
  for (w <- 0 until NWAY) {
    when(ramRe || (refillWr && victimWay === w.U)) {
      when(refillWr && victimWay === w.U) { wayMem(w).write(ramAddr, refillWriteLine) }
        .otherwise { dataOut(w) := wayMem(w).read(ramAddr) }
    }
    // tag 重填写（与原 gen_tag 同拍同条件；复位不清，valid=0 即无效）
    val installTag = refillWr && !refillKilled && !fullInvNow && victimWay === w.U
    // One explicit write port: PDS cannot infer RAM from two Chisel writers.
    when(clearing || installTag) {
      tagMem(w).write(Mux(clearing, clearSet, reqSet),
        Mux(clearing, 0.U, Cat(1.U(1.W), reqTag)))
    }.elsewhen(ramRe) { tagOut(w) := tagMem(w).read(rdSetIdle) }
  }

  when(io.invalidate) { clearing := true.B; clearSet := 0.U }
    .elsewhen(clearing) {
      when(clearSet === (I_NSET - 1).U) { clearing := false.B }
        .otherwise { clearSet := clearSet + 1.U }
    }

  // ---- 主 FSM ----
  when(reset.asBool) {
    state := sIdle
    invalidatePending := false.B
    refillKilled := false.B
  }.otherwise {
    invalidatePending := io.invalidate
    when(invalidatePending) {
      refillKilled := (state === sRreq) || (state === sRdata) ||
                      (state === sUcRreq) || (state === sUcRdata)
    }

    switch(state) {
      is(sIdle) {
        when(reqTake) {
          reqPaddr := io.ifuPaddr
          reqUncached := !cacheableOnly.B && io.ifuUncached
          state := sLookup
        }
      }
      is(sLookup) {
        when(fullInvNow && !reqUncached && hitAny) {
          respLine := dataOutV(hitWay)
          state := sResp
        }.elsewhen(reqUncached) {
          ucWord := reqPaddr(4, 2)
          ucLine := 0.U
          state := sUcRreq
        }.elsewhen(hitAny) {
          when(reqTake) {
            reqPaddr := io.ifuPaddr
            reqUncached := !cacheableOnly.B && io.ifuUncached
            state := sLookup
          }.otherwise { state := sIdle }
        }.otherwise {
          victimWay := pickWay
          state := sRreq
        }
      }
      is(sRreq) { when(io.axiRdRdy) { state := sRdata } }
      is(sRdata) {
        when(io.axiRetValid) {
          when(io.axiRetLast) {
            responseError := io.axiRetError
            when(refillKilled || fullInvNow || io.axiRetError) {
              refillKilled := false.B
              respLine := refillLine
              state := sResp
            }.otherwise {
              replaceWay := !victimWay(0)
              respLine := refillLine
              state := sResp
            }
          }.otherwise {
            refillB0 := io.axiRetData
          }
        }
      }
      is(sResp) {
        when(fullInvNow) {
          state := sResp
        }.elsewhen(reqTake) {
          reqPaddr := io.ifuPaddr
          reqUncached := !cacheableOnly.B && io.ifuUncached
          state := sLookup
        }.otherwise { state := sIdle }
      }
      is(sUcRreq) { if (!cacheableOnly) { when(io.axiRdRdy) { state := sUcRdata } } }
      is(sUcRdata) {
        if (!cacheableOnly) {
        when(io.axiRetValid) {
          responseError := responseError || io.axiRetError
          ucLine := ucNext
          when(ucWord === 7.U) {
            when(refillKilled || fullInvNow || io.axiRetError) { refillKilled := false.B }
            respLine := ucNext
            state := sResp
          }.otherwise {
            ucWord := ucWord + 1.U
            state := sUcRreq
          }
        }
        }
      }
    }
  }
}
