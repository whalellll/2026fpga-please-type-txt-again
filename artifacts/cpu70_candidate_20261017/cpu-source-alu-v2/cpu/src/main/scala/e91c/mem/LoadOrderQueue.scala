package e91c.mem

import chisel3._
import chisel3.util.{Cat, Fill, PriorityEncoder}
import e91c.config.Params._

// Loads remain observable until retirement, including loads still in a cache
// miss. Older stores resolving later invalidate overlapping younger loads.
// Replay happens at the architectural head, preserving all older effects.
class LoadOrderQueue extends Module {
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val head = Input(UInt(ROB_W.W))
    val retire = Input(UInt(ROB_SIZE.W))
    val loadValid = Input(Bool()); val loadTag = Input(UInt(ROB_W.W))
    val loadAddress = Input(UInt(32.W)); val loadMask = Input(UInt(4.W))
    val storeValid = Input(Bool()); val storeTag = Input(UInt(ROB_W.W))
    val storeAddress = Input(UInt(32.W)); val storeMask = Input(UInt(4.W))
    val replay = Output(UInt(ROB_SIZE.W))
  })
  val live = RegInit(VecInit(Seq.fill(ROB_SIZE)(false.B)))
  val poisoned = RegInit(VecInit(Seq.fill(ROB_SIZE)(false.B)))
  // Fold the 30-bit word address into a conservative CAM signature. Equal
  // addresses always match; a collision between different addresses can only
  // request an extra replay and therefore cannot hide a true dependency.
  val signature = Reg(Vec(ROB_SIZE, UInt(8.W)))
  val mask = Reg(Vec(ROB_SIZE, UInt(4.W)))
  val loadSignature12 = io.loadAddress(13,2) ^ io.loadAddress(25,14) ^
    Cat(0.U(6.W), io.loadAddress(31,26))
  val storeSignature12 = io.storeAddress(13,2) ^ io.storeAddress(25,14) ^
    Cat(0.U(6.W), io.storeAddress(31,26))
  // Fold the prior signature again so every old equality/collision remains a
  // collision.  Extra collisions are conservative replays only.
  val loadSignature = loadSignature12(7,0) ^ Cat(0.U(4.W), loadSignature12(11,8))
  val storeSignature = storeSignature12(7,0) ^ Cat(0.U(4.W), storeSignature12(11,8))
  // The head can advance only past retired entries.  Every address compared
  // below belongs to a still-live store/load, so one-cycle-old head position
  // preserves their circular relative order, including across wraparound.
  val orderHead = RegNext(io.head, 0.U(ROB_W.W))
  def ordinal(tag: UInt): UInt = Cat(tag(ROB_PAIR_W-1,0),tag(ROB_W-1))
  def age(tag: UInt): UInt = (ordinal(tag)-ordinal(orderHead))(ROB_W-1,0)
  val storeOrdinal = ordinal(io.storeTag)
  val headOrdinal = ordinal(orderHead)
  val storeBeforeHead = storeOrdinal < headOrdinal
  val conflicts = Wire(Vec(ROB_SIZE, Bool()))
  for(i <- 0 until ROB_SIZE) {
    val loadOrdinal = ordinal(i.U(ROB_W.W))
    val storeBeforeLoad = (storeOrdinal < loadOrdinal) ^ storeBeforeHead ^ (loadOrdinal < headOrdinal)
    if (!sys.props.get("e91c.synthesis").contains("true")) {
      when(live(i) && io.storeValid) {
        assert(storeBeforeLoad === (age(io.storeTag) < age(i.U(ROB_W.W))), "circular memory age mismatch")
      }
    }
    conflicts(i) := live(i) && io.storeValid && storeBeforeLoad &&
      signature(i) === storeSignature && (mask(i)&io.storeMask).orR
    when(io.flush) { live(i):=false.B; poisoned(i):=false.B }
      .otherwise {
        when(io.retire(i)) { live(i):=false.B; poisoned(i):=false.B }
        when(conflicts(i)) { poisoned(i):=true.B }
        when(io.loadValid && io.loadTag===i.U) {
          live(i):=true.B; signature(i):=loadSignature; mask(i):=io.loadMask
          poisoned(i):=false.B
        }
      }
  }
  // A resolving store is itself not commit-visible until the following cycle:
  // the LSU completion crosses the existing top-level memory-WB register.  By
  // then this bitmap has captured every same-cycle conflict, so forwarding the
  // conflict CAM directly to Commit only creates a long DCache->flush path and
  // is not required to protect retirement.
  io.replay := poisoned.asUInt
}

// Only loads explicitly issued around an unresolved store need validation.
// All conflicts are compressed into the oldest poisoned load owner because a
// replay there flushes every younger conflict as well.
class CompactLoadOrderQueue extends Module {
  private val Depth = 4

  val io = IO(new Bundle {
    val flush = Input(Bool())
    val headTag = Input(UInt(ROB_W.W))

    val reserveValid = Input(Bool())
    val reserveLoadTag = Input(UInt(ROB_W.W))
    val reserveStoreTag = Input(UInt(ROB_W.W))
    val reserveReady = Output(Bool())

    val resolveValid = Input(Bool())
    val resolveTag = Input(UInt(ROB_W.W))
    val resolveCacheable = Input(Bool())
    val resolveAddress = Input(UInt(32.W))
    val resolveMask = Input(UInt(4.W))

    val storeValid = Input(Bool())
    val storeTag = Input(UInt(ROB_W.W))
    val storeAddress = Input(UInt(32.W))
    val storeMask = Input(UInt(4.W))

    val replayValid = Output(Bool())
    val replayTag = Output(UInt(ROB_W.W))
  })

  val valid = RegInit(VecInit(Seq.fill(Depth)(false.B)))
  val resolved = RegInit(VecInit(Seq.fill(Depth)(false.B)))
  val loadTag = Reg(Vec(Depth, UInt(ROB_W.W)))
  val barrierTag = Reg(Vec(Depth, UInt(ROB_W.W)))
  val signature = Reg(Vec(Depth, UInt(8.W)))
  val mask = Reg(Vec(Depth, UInt(4.W)))
  val poisonValid = RegInit(false.B)
  val poisonTag = RegInit(0.U(ROB_W.W))

  val free = ~valid.asUInt & Fill(Depth, 1.B)
  io.reserveReady := free.orR
  val freeIndex = PriorityEncoder(free)

  val resolveSignature12 = io.resolveAddress(13,2) ^ io.resolveAddress(25,14) ^
    Cat(0.U(6.W), io.resolveAddress(31,26))
  val storeSignature12 = io.storeAddress(13,2) ^ io.storeAddress(25,14) ^
    Cat(0.U(6.W), io.storeAddress(31,26))
  val resolveSignature = resolveSignature12(7,0) ^ Cat(0.U(4.W), resolveSignature12(11,8))
  val currentStoreSignature = storeSignature12(7,0) ^ Cat(0.U(4.W), storeSignature12(11,8))

  val barrierMatch = VecInit((0 until Depth).map(i =>
    valid(i) && barrierTag(i) === io.storeTag))
  // A store reaching resolution before its bypass load is not expected, but
  // treating that case as a conflict is conservative in production hardware.
  val conflict = VecInit((0 until Depth).map(i =>
    barrierMatch(i) && (!resolved(i) ||
      (signature(i) === currentStoreSignature && (mask(i) & io.storeMask).orR))))

  private def ordinal(tag: UInt): UInt = Cat(tag(ROB_PAIR_W - 1, 0), tag(ROB_W - 1))
  val storeOrder = ordinal(io.storeTag)
  var selectedValid: Bool = false.B
  var selectedTag: UInt = 0.U(ROB_W.W)
  var selectedDistance: UInt = 0.U(ROB_W.W)
  for (i <- 0 until Depth) {
    val distance = ordinal(loadTag(i)) - storeOrder
    val take = conflict(i) && (!selectedValid || distance < selectedDistance)
    selectedTag = Mux(take, loadTag(i), selectedTag)
    selectedDistance = Mux(take, distance, selectedDistance)
    selectedValid = selectedValid || conflict(i)
  }

  val headOrder = ordinal(io.headTag)
  val selectedAge = ordinal(selectedTag) - headOrder
  val poisonAge = ordinal(poisonTag) - headOrder
  val replacePoison = selectedValid && (!poisonValid || selectedAge < poisonAge)

  io.replayValid := poisonValid
  io.replayTag := poisonTag

  if (!sys.props.get("e91c.synthesis").contains("true")) {
    val duplicateReserve = VecInit((0 until Depth).map(i =>
      valid(i) && loadTag(i) === io.reserveLoadTag)).asUInt.orR
    val pendingBarrier = VecInit((0 until Depth).map(i =>
      valid(i) && !resolved(i) && barrierTag(i) === io.storeTag)).asUInt.orR
    when(io.reserveValid && io.reserveReady) {
      assert(!duplicateReserve, "a speculative load may own only one load-order entry")
    }
    when(io.storeValid) {
      assert(!pendingBarrier, "a barrier store resolved before its bypassing load")
    }
  }

  when(reset.asBool || io.flush) {
    valid.foreach(_ := false.B)
    resolved.foreach(_ := false.B)
    poisonValid := false.B
    poisonTag := 0.U
  }.otherwise {
    for (i <- 0 until Depth) {
      when(io.storeValid && barrierMatch(i)) {
        valid(i) := false.B
        resolved(i) := false.B
      }
      when(io.resolveValid && valid(i) && !resolved(i) && loadTag(i) === io.resolveTag) {
        when(io.resolveCacheable) {
          resolved(i) := true.B
          signature(i) := resolveSignature
          mask(i) := io.resolveMask
        }.otherwise {
          valid(i) := false.B
          resolved(i) := false.B
        }
      }
      when(io.reserveValid && io.reserveReady && freeIndex === i.U) {
        valid(i) := true.B
        resolved(i) := false.B
        loadTag(i) := io.reserveLoadTag
        barrierTag(i) := io.reserveStoreTag
      }
    }
    when(io.storeValid && replacePoison) {
      poisonValid := true.B
      poisonTag := selectedTag
    }
  }
}

