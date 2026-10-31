// StoreBuffer: post-commit scalar store drain buffer with load forwarding.
// Ported from cpu/store_buffer.v. Key semantics:
// - flush does NOT clear (all entries are committed stores); only reset clears
// - drain preserves FIFO order and sends one committed scalar store at a time
// - done is registered one cycle (dc_wr_done_r) before pop/inflight/count update
// - query is combinational youngest-first byte merge; UC store blocks its bytes
// - query_word_filter: sticky 64b alias filter, cleared only when queue empties
package e91c.mem

import chisel3._
import chisel3.util.Cat
import e91c.config.Params.{SB_SIZE, SB_W}

class StoreBuffer extends Module {
  val io = IO(new Bundle {
    val pushValid = Input(Bool())
    val pushPaddr = Input(UInt(32.W))
    val pushData = Input(UInt(32.W))
    val pushWstrb = Input(UInt(4.W))
    val pushSize = Input(UInt(3.W))
    val pushUncached = Input(Bool())
    val sbFull = Output(Bool())
    val sbEmpty = Output(Bool())
    val dcWrReq = Output(Bool())
    val dcWrPaddr = Output(UInt(32.W))
    val dcWrData = Output(UInt(32.W))
    val dcWrStrb = Output(UInt(4.W))
    val dcWrSize = Output(UInt(3.W))
    val dcWrUncached = Output(Bool())
    val dcWrAddrOk = Input(Bool())
    val dcWrDone = Input(Bool())
    val queryValid = Input(Bool())
    val queryPaddr = Input(UInt(30.W))
    val queryUncached = Input(Bool())
    val queryRespValid = Output(Bool())
    val queryRespPaddr = Output(UInt(30.W))
    val queryRespUncached = Output(Bool())
    val queryMaybe = Output(Bool())
    val queryHit = Output(Bool())
    val queryData = Output(UInt(32.W))
    val queryPartial = Output(Bool())
    val pairQueryPaddr = Input(UInt(30.W))
    val pairQueryMaybe = Output(Bool())
  })

  import io._

  // 存储体：全部用 Vec 寄存器（硬件可动态索引）
  val validR = RegInit(VecInit(Seq.fill(SB_SIZE)(false.B)))
  val paddrR = RegInit(VecInit(Seq.fill(SB_SIZE)(0.U(32.W))))
  val dataR = RegInit(VecInit(Seq.fill(SB_SIZE)(0.U(32.W))))
  val strbR = RegInit(VecInit(Seq.fill(SB_SIZE)(0.U(4.W))))
  val sizeR = RegInit(VecInit(Seq.fill(SB_SIZE)(0.U(3.W))))
  val uncR = RegInit(VecInit(Seq.fill(SB_SIZE)(false.B)))
  val head = RegInit(0.U(SB_W.W))
  val tail = RegInit(0.U(SB_W.W))
  val count = RegInit(0.U((SB_W + 1).W))
  val inflight = RegInit(false.B)

  val doneR = RegInit(false.B)
  doneR := Mux(reset.asBool, false.B, dcWrDone)

  val cz = 0.U((SB_W + 1).W)
  val popFire = (count =/= cz) && doneR
  val fullW = count === SB_SIZE.U
  val emptyW = count === cz
  sbFull := fullW
  sbEmpty := emptyW
  val pushFire = pushValid && (!fullW || popFire)
  // An accepted transaction remains resident until the registered done pulse.
  // While it is in flight, the next FIFO entry may be staged independently.
  val drainHead = Mux(inflight, head + 1.U, head)
  val drainCount = Mux(inflight, count - 1.U, count)

  val drainValid = RegInit(false.B)
  val drainData = RegInit(0.U(32.W))
  val drainStrb = RegInit(0.U(4.W))
  val drainPaddr = RegInit(0.U(32.W))
  val drainSize = RegInit(0.U(3.W))
  val drainUnc = RegInit(false.B)

  val drainPrepare = !drainValid && (drainCount =/= cz) && validR(drainHead)

  // ---- 主时序 ----
  when(reset.asBool) {
    for (i <- 0 until SB_SIZE) {
      validR(i) := false.B
      paddrR(i) := 0.U; dataR(i) := 0.U; strbR(i) := 0.U; sizeR(i) := 0.U; uncR(i) := false.B
    }
    head := 0.U; tail := 0.U; count := 0.U
    inflight := false.B
    drainValid := false.B
    drainData := 0.U; drainStrb := 0.U; drainPaddr := 0.U; drainSize := 0.U; drainUnc := false.B
  }.otherwise {
    when(doneR) {
      inflight := false.B
    }.elsewhen(dcWrAddrOk) {
      inflight := true.B
      drainValid := false.B
    }

    when(drainPrepare) {
      drainValid := true.B
      drainData := dataR(drainHead)
      drainStrb := strbR(drainHead)
      drainPaddr := paddrR(drainHead)
      drainSize := sizeR(drainHead)
      drainUnc := uncR(drainHead)
    }

    when(popFire) {
      validR(head) := false.B
      head := head + 1.U
    }

    when(pushFire) {
      paddrR(tail) := pushPaddr
      dataR(tail) := pushData
      strbR(tail) := pushWstrb
      sizeR(tail) := pushSize
      uncR(tail) := pushUncached
      validR(tail) := true.B
      tail := tail + 1.U
    }

    when(pushFire && !popFire) { count := count + 1.U }
      .elsewhen(!pushFire && popFire) { count := count - 1.U }
  }

  dcWrReq := drainValid && !inflight
  dcWrPaddr := drainPaddr
  dcWrData := drainData
  dcWrStrb := drainStrb
  dcWrSize := drainSize
  dcWrUncached := drainUnc

  // ---- 前递查询（年轻→年老；Mux 折叠链避免组合环）----
  val foundW = Wire(Vec(4, Bool()))
  val blockedW = Wire(Vec(4, Bool()))
  val dataBW = Wire(Vec(4, UInt(8.W)))
  val anyMatchW = Wire(Bool())
  val anyUncW = Wire(Bool())
  anyMatchW := (0 until SB_SIZE).map(qi => {
    val qIdx = tail - 1.U - qi.U
    validR(qIdx) && (paddrR(qIdx)(31, 2) === queryPaddr)
  }).reduce(_ || _)
  anyUncW := (0 until SB_SIZE).map(qi => {
    val qIdx = tail - 1.U - qi.U
    validR(qIdx) && uncR(qIdx)
  }).reduce(_ || _)
  val queryAliasW = (0 until SB_SIZE).map(qi => {
    val qIdx = tail - 1.U - qi.U
    validR(qIdx) && (paddrR(qIdx)(7, 2) === queryPaddr(5, 0))
  }).reduce(_ || _)
  val pairAliasW = (0 until SB_SIZE).map(qi => {
    val qIdx = tail - 1.U - qi.U
    validR(qIdx) && (paddrR(qIdx)(7, 2) === pairQueryPaddr(5, 0))
  }).reduce(_ || _)
  for (b <- 0 until 4) {
    // 年老先入链、年轻后入链（Mux 命中即覆盖）→ 年轻优先；
    // 年轻 UC 命中该字节 → 阻塞并清除 older 提供位
    var fAcc = false.B
    var bAcc = false.B
    var dAcc = 0.U(8.W)
    for (qi <- (SB_SIZE - 1) to 0 by -1) {
      val qIdx = tail - 1.U - qi.U
      val hitB = validR(qIdx) && (paddrR(qIdx)(31, 2) === queryPaddr) && strbR(qIdx)(b)
      fAcc = Mux(hitB, !uncR(qIdx), fAcc)
      bAcc = Mux(hitB && uncR(qIdx), true.B, bAcc)
      dAcc = Mux(hitB && uncR(qIdx), 0.U,
             Mux(hitB && !uncR(qIdx), dataR(qIdx)(8 * b + 7, 8 * b), dAcc))
    }
    foundW(b) := fAcc
    blockedW(b) := bAcc
    dataBW(b) := dAcc
  }
  val mergeDataQ = Cat(dataBW(3), dataBW(2), dataBW(1), dataBW(0))
  val uncOrderBlock = queryUncached && anyUncW

  val respValidR = RegInit(false.B)
  val respPaddrR = RegInit(0.U(30.W))
  val respUncR = RegInit(false.B)
  val hitR = RegInit(false.B)
  val dataQR = RegInit(0.U(32.W))
  val partialR = RegInit(false.B)
  respValidR := queryValid
  when(queryValid) {
    respPaddrR := queryPaddr
    respUncR := queryUncached
    hitR := foundW.asUInt.andR && !uncOrderBlock
    dataQR := mergeDataQ
    partialR := (anyMatchW && !foundW.asUInt.andR) || uncOrderBlock
  }

  queryRespValid := respValidR
  queryRespPaddr := respPaddrR
  queryRespUncached := respUncR
  queryMaybe := !emptyW && (queryAliasW || (queryUncached && anyUncW))
  pairQueryMaybe := !emptyW && (pairAliasW || anyUncW)
  queryHit := hitR
  queryData := dataQR
  queryPartial := partialR
}
