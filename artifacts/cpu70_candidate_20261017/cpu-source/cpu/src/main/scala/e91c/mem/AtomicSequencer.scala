package e91c.mem

import chisel3._
import chisel3.util._
import e91c.config.Params.ROB_W

class AtomicRequest extends Bundle {
  val robid = UInt(ROB_W.W)
  val operation = UInt(5.W) // instruction funct5
  val physicalAddress = UInt(32.W)
  val virtualAddress = UInt(32.W)
  val operand = UInt(32.W)
}
class AtomicResult extends Bundle {
  val robid = UInt(ROB_W.W)
  val data = UInt(32.W)
  val storeData = UInt(32.W)
  val storeMask = UInt(4.W)
  val accessFault = Bool()
  val physicalAddress = UInt(32.W)
  val virtualAddress = UInt(32.W)
}

/** One-hart atomic operation, admitted at the ROB head after older memory drains.
  * The owner locks memory issue through retirement. Writes are returned as a
  * commit-only store-buffer payload; no speculative atomic write reaches RAM.
  * A coherent external writer must assert invalidateReservation.
  */
class AtomicSequencer extends Module {
  val io = IO(new Bundle {
    val request = Flipped(Decoupled(new AtomicRequest))
    val result = Decoupled(new AtomicResult)
    val readRequest = Decoupled(UInt(32.W))
    val readResponse = Flipped(Decoupled(new PageTableReadResponse))
    val commit = Input(Bool())
    val commitRobid = Input(UInt(ROB_W.W))
    val flush = Input(Bool())
    val invalidateReservation = Input(Bool())
    val busy = Output(Bool())
  })
  val idle :: read :: waitRead :: respond :: waitCommit :: drain :: Nil = Enum(6)
  val state = RegInit(idle)
  val request = Reg(new AtomicRequest)
  val result = Reg(new AtomicResult)
  val reserved = RegInit(false.B)
  val reservedWord = Reg(UInt(30.W))
  val isLr = request.operation === 2.U
  val isSc = request.operation === 3.U
  val validOperation = Seq(0,1,2,3,4,8,12,16,20,24,28).map(_.U === io.request.bits.operation).reduce(_ || _)
  io.request.ready := state === idle && !io.flush
  io.result.valid := state === respond && !io.flush
  io.result.bits := result
  io.readRequest.valid := state === read && !io.flush
  io.readRequest.bits := request.physicalAddress
  io.readResponse.ready := state === waitRead || state === drain
  io.busy := state =/= idle
  val committed = io.commit && io.commitRobid === request.robid &&
    (state === waitCommit || (state === respond && io.result.ready))

  when(io.request.fire) {
    request := io.request.bits
    result.robid := io.request.bits.robid
    result.physicalAddress := io.request.bits.physicalAddress
    result.virtualAddress := io.request.bits.virtualAddress
    result.data := 0.U
    result.storeData := io.request.bits.operand
    result.storeMask := 0.U
    result.accessFault := false.B
    when(!validOperation || io.request.bits.physicalAddress(1,0).orR) {
      result.accessFault := true.B
      state := respond
    }.elsewhen(io.request.bits.operation === 3.U) {
      val success = reserved && reservedWord === io.request.bits.physicalAddress(31,2) &&
        !io.invalidateReservation
      result.data := Mux(success,0.U,1.U)
      result.storeMask := Mux(success,15.U,0.U)
      reserved := false.B
      state := respond
    }.otherwise { state := read }
  }
  when(io.readRequest.fire) { state := waitRead }
  val old = io.readResponse.bits.data
  val rhs = request.operand
  val modified = MuxLookup(request.operation,rhs)(Seq(
    0.U -> (old + rhs), 1.U -> rhs, 4.U -> (old ^ rhs),
    8.U -> (old | rhs), 12.U -> (old & rhs),
    16.U -> Mux(old.asSInt < rhs.asSInt,old,rhs),
    20.U -> Mux(old.asSInt > rhs.asSInt,old,rhs),
    24.U -> Mux(old < rhs,old,rhs), 28.U -> Mux(old > rhs,old,rhs)))
  when(io.readResponse.fire) {
    when(state === drain) { state := idle }.otherwise {
      result.data := old
      result.storeData := modified
      result.storeMask := Mux(isLr || io.readResponse.bits.error,0.U,15.U)
      result.accessFault := io.readResponse.bits.error
      state := respond
    }
  }
  when(io.result.fire) { state := waitCommit }
  when(committed) {
    state := idle
    when(isLr && !result.accessFault) {
      reserved := true.B
      reservedWord := request.physicalAddress(31,2)
    }.elsewhen(!isLr) { reserved := false.B }
  }
  when(io.invalidateReservation) { reserved := false.B }
  when(io.flush) {
    reserved := false.B
    state := Mux((state === waitRead || state === drain) && !io.readResponse.fire,drain,idle)
  }
}
