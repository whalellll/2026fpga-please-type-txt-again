package e91c.reg

import chisel3._

/** Active results use ROB-tag lifetime; committed values use architectural lifetime. */
class RobTagRegisterFile(val tagReads: Int = 8) extends Module {
  val io = IO(new Bundle {
    val flush = Input(Bool())
    // Every ROB tag reuse invalidates the old result, including instructions
    // without an architectural destination.  This control is independent of
    // decode's late rfWe decision.
    val clear = Input(Vec(2, Bool()))
    val allocate = Input(Vec(2, Bool()))
    val allocateTag = Input(Vec(2, UInt(5.W)))
    val retire = Input(Vec(2, Bool()))
    val retireRd = Input(Vec(2, UInt(5.W)))
    val retireTag = Input(Vec(2, UInt(5.W)))
    val retireData = Input(Vec(2, UInt(32.W)))
    val write = Input(Vec(5, Bool()))
    val writeTag = Input(Vec(5, UInt(5.W)))
    val writeData = Input(Vec(5, UInt(32.W)))
    val archRead = Input(Vec(4, UInt(5.W)))
    val archData = Output(Vec(4, UInt(32.W)))
    val tagRead = Input(Vec(tagReads, UInt(5.W)))
    val tagData = Output(Vec(tagReads, UInt(32.W)))
  })

  private val bankForPort = Seq(0, 1, 2, 4, 3)
  val resultBanks = Seq.fill(5)(Mem(32, UInt(32.W)))
  val resultOwner = RegInit(VecInit(Seq.fill(32)(0.U(3.W))))
  val resultValid = RegInit(VecInit(Seq.fill(32)(false.B)))
  val tagLive = RegInit(VecInit(Seq.fill(32)(false.B)))

  private def storedResult(tag: UInt): UInt =
    Mux(resultValid(tag), VecInit(resultBanks.map(_(tag)))(resultOwner(tag)), 0.U)

  for (port <- 0 until tagReads) io.tagData(port) := storedResult(io.tagRead(port))

  val archBanks = Seq.fill(2)(Mem(32, UInt(32.W)))
  val archOwner = RegInit(VecInit(Seq.fill(32)(false.B)))
  val archValid = RegInit(VecInit(Seq.fill(32)(false.B)))

  for (port <- 0 until 4) {
    val address = io.archRead(port)
    val stored = Mux(archValid(address),
      Mux(archOwner(address), archBanks(1)(address), archBanks(0)(address)), 0.U)
    val afterLane0 = Mux(io.retire(0) && io.retireRd(0) =/= 0.U &&
      io.retireRd(0) === address, io.retireData(0), stored)
    val afterLane1 = Mux(io.retire(1) && io.retireRd(1) =/= 0.U &&
      io.retireRd(1) === address, io.retireData(1), afterLane0)
    io.archData(port) := Mux(address === 0.U, 0.U, afterLane1)
  }

  val resetB = reset.asBool
  when(resetB) {
    resultValid.foreach(_ := false.B)
    tagLive.foreach(_ := false.B)
    archValid.foreach(_ := false.B)
  }.otherwise {
    when(io.flush) {
      tagLive.foreach(_ := false.B)
    }.otherwise {
      for (lane <- 0 until 2) {
        when(io.retire(lane) && io.retireRd(lane) =/= 0.U) {
          tagLive(io.retireTag(lane)) := false.B
        }
      }
      for (lane <- 0 until 2) {
        when(io.allocate(lane)) { tagLive(io.allocateTag(lane)) := true.B }
      }
    }

    for (lane <- 0 until 2) {
      when(io.retire(lane) && io.retireRd(lane) =/= 0.U) {
        archBanks(lane)(io.retireRd(lane)) := io.retireData(lane)
        archOwner(io.retireRd(lane)) := (lane == 1).B
        archValid(io.retireRd(lane)) := true.B
      }
    }

    for (port <- 0 until 5) {
      // Allocation only controls visibility, not the wide writeback datapath.
      // A stale same-cycle write may update hidden storage on tag reuse; the
      // clear below wins over its valid bit until the new producer writes.
      // This removes decode/rename -> every writeback owner/bank write enable.
      when(io.write(port) && tagLive(io.writeTag(port)) && !io.flush) {
        resultBanks(bankForPort(port))(io.writeTag(port)) := io.writeData(port)
        resultOwner(io.writeTag(port)) := bankForPort(port).U
        resultValid(io.writeTag(port)) := true.B
      }
    }
    when(!io.flush) {
      for (lane <- 0 until 2) {
        when(io.clear(lane)) {
          resultValid(io.allocateTag(lane)) := false.B
        }
      }
    }
  }

  if (!sys.props.get("e91c.synthesis").contains("true")) {
    assert(!archValid(0), "x0 must never acquire architectural storage")
    for (lane <- 0 until 2) {
      val retiresSameTag = (0 until 2).map(retireLane =>
        io.retire(retireLane) && io.retireTag(retireLane) === io.allocateTag(lane)).reduce(_ || _)
      when(io.allocate(lane)) {
        assert(!tagLive(io.allocateTag(lane)) || retiresSameTag,
          "ROB tag reused while its prior producer is still live")
      }
    }
  }
}
