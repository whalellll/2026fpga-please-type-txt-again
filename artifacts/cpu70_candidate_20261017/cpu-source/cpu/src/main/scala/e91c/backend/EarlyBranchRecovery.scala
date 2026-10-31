package e91c.backend

import chisel3._
import chisel3.util.Cat
import e91c.config.Params.{FTQ_W, ROB_W}

// Detect conditional-direction misses at ALU writeback, choose the oldest lane,
// and remember the branch until its precise commit-time backend flush.  The
// frontend redirect is registered so this path never joins the ALU result cone.
class EarlyBranchRecovery extends Module {
  val io = IO(new Bundle {
    val globalFlush = Input(Bool())
    val block = Input(Bool())
    val headRobid = Input(UInt(ROB_W.W))

    val laneValid = Input(Vec(2, Bool()))
    val laneIsCond = Input(Vec(2, Bool()))
    val laneRobid = Input(Vec(2, UInt(ROB_W.W)))
    val lanePc = Input(Vec(2, UInt(32.W)))
    val lanePredTaken = Input(Vec(2, Bool()))
    val laneTaken = Input(Vec(2, Bool()))
    val laneTarget = Input(Vec(2, UInt(32.W)))
    val laneFtqId = Input(Vec(2, UInt(FTQ_W.W)))

    val redirectValid = Output(Bool())
    val redirectPc = Output(UInt(32.W))
    val redirectFtqId = Output(UInt(FTQ_W.W))
    val redirectTaken = Output(Bool())
    val pendingValid = Output(Bool())
    val pendingRobid = Output(UInt(ROB_W.W))
    val recoveryStall = Output(Bool())
  })

  val eligible = Wire(Vec(2, Bool()))
  val ordinal = Wire(Vec(2, UInt(ROB_W.W)))
  val age = Wire(Vec(2, UInt(ROB_W.W)))
  val headOrdinal = Cat(io.headRobid(ROB_W - 2, 0), io.headRobid(ROB_W - 1))
  for (i <- 0 until 2) {
    eligible(i) := io.laneValid(i) && io.laneIsCond(i) &&
      (io.laneTaken(i) =/= io.lanePredTaken(i)) &&
      (!io.laneTaken(i) || !io.laneTarget(i)(1, 0).orR)
    ordinal(i) := Cat(io.laneRobid(i)(ROB_W - 2, 0), io.laneRobid(i)(ROB_W - 1))
    age(i) := ordinal(i) - headOrdinal
  }

  val selectLane1 = eligible(1) && (!eligible(0) || age(1) < age(0))
  val selectedRobid = Mux(selectLane1, io.laneRobid(1), io.laneRobid(0))
  val selectedPc = Mux(selectLane1, io.lanePc(1), io.lanePc(0))
  val selectedTaken = Mux(selectLane1, io.laneTaken(1), io.laneTaken(0))
  val selectedTarget = Mux(selectLane1, io.laneTarget(1), io.laneTarget(0))
  val selectedFtqId = Mux(selectLane1, io.laneFtqId(1), io.laneFtqId(0))

  val pendingValidR = RegInit(false.B)
  val pendingRobidR = Reg(UInt(ROB_W.W))
  val pendingOrdinal = Cat(pendingRobidR(ROB_W - 2, 0), pendingRobidR(ROB_W - 1))
  val pendingAge = pendingOrdinal - headOrdinal
  // An eligible lane can replace the pending owner iff it is older.  If any
  // eligible lane is older, the oldest eligible lane selected above is older
  // too.  Compare both ages before the late ALU eligibility arrives, avoiding
  // the selected-age mux followed by a pending-age comparator on accept.
  val replaceLane0 = !pendingValidR || age(0) < pendingAge
  val replaceLane1 = !pendingValidR || age(1) < pendingAge
  val accept = !io.block &&
    ((eligible(0) && replaceLane0) || (eligible(1) && replaceLane1))

  val redirectValidR = RegInit(false.B)
  val redirectPcR = Reg(UInt(32.W))
  val redirectFtqIdR = Reg(UInt(FTQ_W.W))
  val redirectTakenR = Reg(Bool())

  when(reset.asBool || io.globalFlush) {
    pendingValidR := false.B
    redirectValidR := false.B
  }.otherwise {
    redirectValidR := accept
    when(accept) {
      pendingValidR := true.B
      pendingRobidR := selectedRobid
      redirectPcR := Mux(selectedTaken, selectedTarget, selectedPc + 4.U)
      redirectFtqIdR := selectedFtqId
      redirectTakenR := selectedTaken
    }
  }

  io.redirectValid := redirectValidR && !io.globalFlush
  io.redirectPc := redirectPcR
  io.redirectFtqId := redirectFtqIdR
  io.redirectTaken := redirectTakenR
  io.pendingValid := pendingValidR
  io.pendingRobid := pendingRobidR
  io.recoveryStall := pendingValidR || redirectValidR

  if (!sys.props.get("e91c.synthesis").contains("true")) {
    when(io.redirectValid) {
      assert(io.pendingValid, "early branch redirect must retain a pending owner")
      assert(!io.redirectTaken || !io.redirectPc(1, 0).orR,
        "misaligned branch target must remain a commit-time exception")
    }
  }
}
