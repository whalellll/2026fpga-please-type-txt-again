// AxiLineBridge: 32B cache line <-> 32-bit AXI burst converter.
// Ported from cpu/axi_line_bridge.v. Key semantics:
// - line read: 8-beat INCR, upstream 128b return every 4 beats (last on beat 7)
// - line write: 2-beat 128b capture, AWLEN=7 burst; AW first then W (ordered policy)
// - uncached: single transfer, wr rdy = own B completion
// - up to 2 in-flight B for line writes (b_cnt); uncached writes never overlap
// - dual read engines (arid 0=ic / 1=dc), R routed by rid; strict one-reader
//   admission while both idle; reads never pass outstanding writes
package e91c.mem

import chisel3._
import chisel3.util.{Cat, is, switch}
import e91c.config.Params.CACHE_LINE_W

class AxiLineBridge extends Module {
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
    val dcWrRdy = Output(Bool())
    val awValid = Output(Bool()); val awAddr = Output(UInt(32.W))
    val awLen = Output(UInt(4.W)); val awSize = Output(UInt(3.W)); val awReady = Input(Bool())
    val wValid = Output(Bool()); val wData = Output(UInt(32.W)); val wStrb = Output(UInt(4.W))
    val wLast = Output(Bool()); val wReady = Input(Bool())
    val bValid = Input(Bool()); val bReady = Output(Bool())
    val arValid = Output(Bool()); val arId = Output(UInt(4.W)); val arAddr = Output(UInt(32.W))
    val arLen = Output(UInt(4.W)); val arSize = Output(UInt(3.W)); val arReady = Input(Bool())
    val rValid = Input(Bool()); val rId = Input(UInt(4.W)); val rData = Input(UInt(32.W))
    val rResp = Input(UInt(2.W))
    val rLast = Input(Bool()); val rReady = Output(Bool())
  })

  import io._

  val ARID_IC = 0.U(4.W); val ARID_DC = 1.U(4.W)
  val wrIdle = 0.U(2.W); val wrCap1 = 1.U(2.W); val wrIssue = 2.U(2.W); val wrUcB = 3.U(2.W)

  val wrState = RegInit(wrIdle)
  val wrAddrBuf = Reg(UInt(32.W))
  val wrLineBuf = Reg(UInt(256.W))
  val wrStrbBuf = Reg(UInt(4.W))
  val wrIsLine = RegInit(false.B)   // 原 RTL 无复位（X→黄金消毒为 0），这里以 0 对齐
  val wrAxSize = Reg(UInt(3.W))
  val wrBeat = RegInit(0.U(3.W))
  val awPend = RegInit(false.B)
  val wPend = RegInit(false.B)
  val bCnt = RegInit(0.U(2.W))

  val awHs = awValid && awReady
  val wHs = wValid && wReady
  val bHs = bValid && bReady

  val wLastBeat = Mux(wrIsLine, wrBeat === 7.U, true.B)
  val issueDone = (wrState === wrIssue) && (!awPend || awHs) && (!wPend || (wHs && wLastBeat))

  val wrAllIdle = (wrState === wrIdle) && (bCnt === 0.U)

  val rdIdle = 0.U(2.W); val rdAr = 1.U(2.W); val rdRdata = 2.U(2.W)

  val icState = RegInit(rdIdle)
  val icIsLine = RegInit(false.B)
  val icAddrBuf = Reg(UInt(32.W))
  val icAxSize = Reg(UInt(3.W))
  val icBeat = RegInit(0.U(3.W))
  val icBuf = Reg(UInt(96.W))
  val icRetValidR = RegInit(false.B)
  val icRetLastR = RegInit(false.B)
  val icRetDataR = Reg(UInt(128.W))

  val dcState = RegInit(rdIdle)
  val dcIsLine = RegInit(false.B)
  val dcAddrBuf = Reg(UInt(32.W))
  val dcAxSize = Reg(UInt(3.W))
  val dcBeat = RegInit(0.U(3.W))
  val dcBuf = Reg(UInt(96.W))
  val dcRetValidR = RegInit(false.B)
  val dcRetLastR = RegInit(false.B)
  val dcRetDataR = Reg(UInt(128.W))

  val icError = RegInit(false.B); val dcError = RegInit(false.B)
  val icRetError = RegInit(false.B); val dcRetError = RegInit(false.B)
  io.icRetError := icRetError; io.dcRetError := dcRetError
  val arRrDc = RegInit(false.B)

  val rdAllIdle = (icState === rdIdle) && (dcState === rdIdle)
  // 接纳条件（先声明线，后赋值解依赖）
  val wrLineCanTake = Wire(Bool()); val wrUcCanTake = Wire(Bool())
  val rdFireOk = Wire(Bool())
  val strictIcPick = Wire(Bool()); val strictDcPick = Wire(Bool())
  val icRdFire = Wire(Bool()); val dcRdFire = Wire(Bool())
  val rdPending = Wire(Bool())
  val wrTakeLine = Wire(Bool()); val wrTakeUc = Wire(Bool())

  rdFireOk := wrAllIdle && !(wrTakeLine || wrTakeUc)
  strictIcPick := icRdReq && (!dcRdReq || !arRrDc)
  strictDcPick := dcRdReq && (!icRdReq || arRrDc)
  icRdFire := rdAllIdle && rdFireOk && strictIcPick
  dcRdFire := rdAllIdle && rdFireOk && strictDcPick
  rdPending := ((icState === rdIdle) && icRdReq) || ((dcState === rdIdle) && dcRdReq)
  wrLineCanTake := (wrState === wrIdle) && (bCnt === 0.U) && rdAllIdle && !rdPending
  wrUcCanTake := (wrState === wrIdle) && (bCnt === 0.U) && rdAllIdle && !rdPending
  wrTakeLine := wrLineCanTake && dcWrReq && (dcWrType === "b100".U)
  wrTakeUc := wrUcCanTake && dcWrReq && (dcWrType =/= "b100".U)

  // AR 仲裁
  val icWantAr = (icState === rdAr)
  val dcWantAr = (dcState === rdAr)
  val arGrantDc = dcWantAr && (!icWantAr || arRrDc)
  val arGrantIc = icWantAr && (!dcWantAr || !arRrDc)
  val icArHs = arGrantIc && arReady
  val dcArHs = arGrantDc && arReady

  // R 按 rid 路由
  val rToIc = rValid && (rId === ARID_IC)
  val rToDc = rValid && (rId === ARID_DC)
  val icRHs = rToIc && (icState === rdRdata)
  val dcRHs = rToDc && (dcState === rdRdata)

  icRetValidR := false.B
  icRetLastR := false.B
  dcRetValidR := false.B
  dcRetLastR := false.B

  // ---- 写 FSM ----
  switch(wrState) {
    is(wrIdle) {
      when(wrTakeLine) {
        wrAddrBuf := dcWrAddr
        wrAxSize := dcWrType
        wrIsLine := true.B
        wrLineBuf := Cat(0.U(128.W), dcWrData)   // 低 128b = beat0
        wrBeat := 0.U
        wrState := wrCap1
      }.elsewhen(wrTakeUc) {
        wrAddrBuf := dcWrAddr
        wrAxSize := dcWrType
        wrIsLine := false.B
        wrLineBuf := Cat(0.U(128.W), dcWrData)
        wrStrbBuf := dcWrStrb
        wrBeat := 0.U
        awPend := true.B
        wPend := true.B
        wrState := wrIssue
      }
    }
    is(wrCap1) {
      wrLineBuf := Cat(dcWrData, wrLineBuf(127, 0))
      awPend := true.B
      wPend := true.B
      wrState := wrIssue
    }
    is(wrIssue) {
      when(awHs) { awPend := false.B }
      when(wHs) {
        when(wLastBeat) { wPend := false.B }.otherwise { wrBeat := wrBeat + 1.U }
      }
      when(issueDone) {
        wrState := Mux(wrIsLine, wrIdle, wrUcB)
      }
    }
    is(wrUcB) {
      when(bHs && (bCnt === 1.U)) { wrState := wrIdle }
    }
  }

  when(issueDone && !bHs) { bCnt := bCnt + 1.U }
    .elsewhen(!issueDone && bHs) { bCnt := bCnt - 1.U }

  // ---- ic 读引擎 ----
  switch(icState) {
    is(rdIdle) {
      when(icRdFire) {
        icError := false.B
        icAddrBuf := icRdAddr
        icAxSize := icRdType
        icIsLine := (icRdType === "b100".U)
        icBeat := 0.U
        icState := rdAr
      }
    }
    is(rdAr) {
      when(icArHs) {
        icState := rdRdata
        arRrDc := true.B
      }
    }
    is(rdRdata) {
      when(icRHs) {
        icError := icError || rResp(1)
        icRetError := icError || rResp(1)
        when(icIsLine) {
          when(icBeat(1, 0) === 3.U) {
            icRetDataR := Cat(rData, icBuf)
            icRetValidR := true.B
            icRetLastR := (icBeat === 7.U)
          }.elsewhen(icBeat(1, 0) === 0.U) {
            icBuf := Cat(icBuf(95, 32), rData)       // 槽 0
          }.elsewhen(icBeat(1, 0) === 1.U) {
            icBuf := Cat(icBuf(95, 64), rData, icBuf(31, 0))  // 槽 1
          }.otherwise {
            icBuf := Cat(rData, icBuf(63, 0))         // 槽 2
          }
          icBeat := icBeat + 1.U
          when(rLast) { icState := rdIdle }
        }.otherwise {
          icRetDataR := Cat(0.U(96.W), rData)
          icRetValidR := true.B
          icRetLastR := true.B
          icState := rdIdle
        }
      }
    }
  }

  // ---- dc 读引擎 ----
  switch(dcState) {
    is(rdIdle) {
      when(dcRdFire) {
        dcError := false.B
        dcAddrBuf := dcRdAddr
        dcAxSize := dcRdType
        dcIsLine := (dcRdType === "b100".U)
        dcBeat := 0.U
        dcState := rdAr
      }
    }
    is(rdAr) {
      when(dcArHs) {
        dcState := rdRdata
        arRrDc := false.B
      }
    }
    is(rdRdata) {
      when(dcRHs) {
        dcError := dcError || rResp(1)
        dcRetError := dcError || rResp(1)
        when(dcIsLine) {
          when(dcBeat(1, 0) === 3.U) {
            dcRetDataR := Cat(rData, dcBuf)
            dcRetValidR := true.B
            dcRetLastR := (dcBeat === 7.U)
          }.elsewhen(dcBeat(1, 0) === 0.U) {
            dcBuf := Cat(dcBuf(95, 32), rData)
          }.elsewhen(dcBeat(1, 0) === 1.U) {
            dcBuf := Cat(dcBuf(95, 64), rData, dcBuf(31, 0))
          }.otherwise {
            dcBuf := Cat(rData, dcBuf(63, 0))
          }
          dcBeat := dcBeat + 1.U
          when(rLast) { dcState := rdIdle }
        }.otherwise {
          dcRetDataR := Cat(0.U(96.W), rData)
          dcRetValidR := true.B
          dcRetLastR := true.B
          dcState := rdIdle
        }
      }
    }
  }

  // ---- 上行握手/返回 ----
  icRdRdy := icArHs
  dcRdRdy := dcArHs
  icRetValid := icRetValidR
  icRetLast := icRetLastR
  icRetData := icRetDataR
  dcRetValid := dcRetValidR
  dcRetLast := dcRetLastR
  dcRetData := dcRetDataR
  dcWrRdy := wrTakeLine || ((wrState === wrUcB) && bHs && (bCnt === 1.U))

  // ---- AXI 引脚 ----
  awValid := (wrState === wrIssue) && awPend
  awAddr := Mux(wrIsLine, Cat(wrAddrBuf(31, CACHE_LINE_W), 0.U(CACHE_LINE_W.W)), wrAddrBuf)
  awLen := Mux(wrIsLine, 7.U, 0.U)
  awSize := Mux(wrIsLine, "b010".U, wrAxSize)

  wValid := (wrState === wrIssue) && wPend && !awPend
  wData := Mux(wrIsLine, (wrLineBuf >> (32.U * wrBeat))(31, 0), wrLineBuf(31, 0))
  wStrb := Mux(wrIsLine, "hf".U, wrStrbBuf)
  wLast := wLastBeat

  bReady := (bCnt =/= 0.U)

  arValid := arGrantIc || arGrantDc
  arId := Mux(arGrantDc, ARID_DC, ARID_IC)
  arAddr := Mux(arGrantDc,
    Mux(dcIsLine, Cat(dcAddrBuf(31, CACHE_LINE_W), 0.U(CACHE_LINE_W.W)), dcAddrBuf),
    Mux(icIsLine, Cat(icAddrBuf(31, CACHE_LINE_W), 0.U(CACHE_LINE_W.W)), icAddrBuf))
  arLen := Mux(arGrantDc, Mux(dcIsLine, 7.U, 0.U), Mux(icIsLine, 7.U, 0.U))
  arSize := Mux(arGrantDc, Mux(dcIsLine, "b010".U, dcAxSize), Mux(icIsLine, "b010".U, icAxSize))

  rReady := (rToIc && (icState === rdRdata)) || (rToDc && (dcState === rdRdata))
}
