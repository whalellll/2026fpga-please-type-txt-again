package e91c.reg

import chisel3._
import chisel3.util._

/** Physical storage is independent of ROB slot reuse. ROB tags only identify
  * live producers on the existing wakeup network; they are translated here.
  * Retirement changes the committed map and releases the previous physical
  * destination. A full recovery retains precisely the post-retirement map.
  */
class PhysicalRegisterFile(val entries: Int = e91c.config.Params.PRF_ENTRIES, val tagReads: Int = 8) extends Module {
  require(entries > 32 && entries <= 64)
  private val pw = log2Ceil(entries)
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val allocate = Input(Vec(2, Bool()))
    val allocateRd = Input(Vec(2, UInt(5.W)))
    val allocateTag = Input(Vec(2, UInt(5.W)))
    val allocatedPhysical = Output(Vec(2, UInt(pw.W)))
    val canAllocate = Output(Bool())
    val retire = Input(Vec(2, Bool()))
    val retireRd = Input(Vec(2, UInt(5.W)))
    val retireTag = Input(Vec(2, UInt(5.W)))
    val write = Input(Vec(5, Bool()))
    val writeTag = Input(Vec(5, UInt(5.W)))
    val writeData = Input(Vec(5, UInt(32.W)))
    val archRead = Input(Vec(4, UInt(5.W)))
    val archData = Output(Vec(4, UInt(32.W)))
    val tagRead = Input(Vec(tagReads, UInt(5.W)))
    val tagData = Output(Vec(tagReads, UInt(32.W)))
    val freeCount = Output(UInt(log2Ceil(entries + 1).W))
    val committedMap = Output(Vec(32, UInt(pw.W)))
    val speculativeMap = Output(Vec(32, UInt(pw.W)))
  })

  val committed = RegInit(VecInit((0 until 32).map(_.U(pw.W))))
  val speculative = RegInit(VecInit((0 until 32).map(_.U(pw.W))))
  val tagPhysical = RegInit(VecInit(Seq.fill(32)(0.U(pw.W))))
  val tagLive = RegInit(VecInit(Seq.fill(32)(false.B)))
  val free = RegInit((((BigInt(1) << entries) - 1) ^ ((BigInt(1) << 32) - 1)).U(entries.W))
  // Each execution source owns one write bank. The owner table selects the
  // most recent bank; no architectural data is copied at retirement.
  val banks = Seq.fill(5)(Mem(entries, UInt(32.W)))
  // Keep the four active production writers in contiguous owner codes.
  // All five interfaces remain supported; input port3 uses bank4.
  private val bankForPort = Seq(0, 1, 2, 4, 3)
  val owner = RegInit(VecInit(Seq.fill(entries)(0.U(3.W))))
  val initialized = RegInit(VecInit(Seq.fill(entries)(false.B)))

  val committedPhysicalMask = RegInit(((BigInt(1) << 32) - 1).U(entries.W))
  val committedMaskAfter = Wire(Vec(3, UInt(entries.W)))
  committedMaskAfter(0) := committedPhysicalMask
  val committedAfter = Wire(Vec(3, Vec(32, UInt(pw.W))))
  val released = Wire(Vec(3, UInt(entries.W)))
  committedAfter(0) := committed
  released(0) := 0.U
  for (i <- 0 until 2) {
    committedAfter(i + 1) := committedAfter(i)
    committedMaskAfter(i + 1) := committedMaskAfter(i)
    released(i + 1) := released(i)
    when(io.retire(i) && io.retireRd(i) =/= 0.U) {
      if (!sys.props.get("e91c.synthesis").contains("true"))
        assert(tagLive(io.retireTag(i)), "retirement without a physical destination")
      val oldPhysical = committedAfter(i)(io.retireRd(i))
      committedMaskAfter(i + 1) := (committedMaskAfter(i) & ~UIntToOH(oldPhysical, entries)) |
        UIntToOH(tagPhysical(io.retireTag(i)), entries)
      committedAfter(i + 1)(io.retireRd(i)) := tagPhysical(io.retireTag(i))
      released(i + 1) := released(i) | UIntToOH(oldPhysical, entries)
    }
  }
  // Committed mappings are unique physical destinations. Update their set in
  // program order, including same-register WAW retirement and flush cycles.
  val committedMask = committedMaskAfter(2)
  committedPhysicalMask := committedMask
  if (!sys.props.get("e91c.synthesis").contains("true")) {
    val referenceMask = (0 until 32).map(i => UIntToOH(committedAfter(2)(i), entries)).reduce(_ | _)
    val maskCheckArmed = RegNext(true.B, false.B)
    when(maskCheckArmed) {
      assert(committedMask === referenceMask, "incremental committed physical mask mismatch")
    }
  }
  val available = free | released(2)
  val allocationMask = Wire(Vec(3, UInt(entries.W)))
  allocationMask(0) := available & ~1.U(entries.W)
  val specAfter = Wire(Vec(3, Vec(32, UInt(pw.W))))
  specAfter(0) := speculative
  val requested = VecInit((0 until 2).map(i => io.allocate(i) && io.allocateRd(i) =/= 0.U))
  // Hierarchical parallel-prefix ranks avoid both three serial priority chains
  // and a full-width prefix cell at every entry.  Four-entry local groups feed
  // a balanced group prefix; saturation at three is sufficient because the
  // allocator only consumes ranks 0..2.
  val usable = available & ~1.U(entries.W)
  private val rankGroupSize = 4
  require(entries % rankGroupSize == 0)
  private val rankGroups = entries / rankGroupSize
  def saturatingRank(value: UInt): UInt = Mux(value >= 2.U, 2.U(2.W), value(1, 0))
  var groupPrefix: Seq[UInt] = (0 until rankGroups).map { group =>
    val high = (group + 1) * rankGroupSize - 1
    val low = group * rankGroupSize
    saturatingRank(PopCount(usable(high, low)))
  }
  for (level <- 0 until log2Ceil(rankGroups)) {
    val previous = groupPrefix
    val distance = 1 << level
    groupPrefix = (0 until rankGroups).map { group =>
      if (group < distance) previous(group)
      else {
        val sum = previous(group) +& previous(group - distance)
        saturatingRank(sum)
      }
    }
  }
  val groupBefore = (0 until rankGroups).map(group =>
    if (group == 0) 0.U(2.W) else groupPrefix(group - 1))
  val rank = (0 until entries).map { entry =>
    val group = entry / rankGroupSize
    val local = entry % rankGroupSize
    val localBefore = if (local == 0) 0.U(2.W)
      else PopCount(usable(group * rankGroupSize + local - 1, group * rankGroupSize))
    saturatingRank(groupBefore(group) +& localBefore)
  }
  val rankedPhysical = VecInit((0 until 2).map(k => OHToUInt(VecInit(
    (0 until entries).map(i => usable(i) && rank(i)===k.U)).asUInt)))
  io.canAllocate := rankedPhysical(1) =/= 0.U
  if (!sys.props.get("e91c.synthesis").contains("true")) {
    val allocCheckArmed = RegNext(true.B, false.B)
    when(allocCheckArmed) {
      assert(io.canAllocate === (PopCount(available) >= 2.U), "PRF ranked availability mismatch")
    }
  }
  for (i <- 0 until 2) {
    val preceding = Wire(UInt(2.W))
    preceding := (if(i==0) 0.U else PopCount(requested.take(i)))
    val selected = rankedPhysical(preceding)
    io.allocatedPhysical(i) := Mux(requested(i), selected, 0.U)
    val taken = PopCount(requested.take(i+1))
    allocationMask(i + 1) := VecInit((0 until entries).map(j => usable(j) && rank(j)>=taken)).asUInt
    specAfter(i + 1) := specAfter(i)
    when(requested(i) && !io.flush) {
      if (!sys.props.get("e91c.synthesis").contains("true"))
        assert(allocationMask(i).orR, "physical register exhaustion")
      specAfter(i + 1)(io.allocateRd(i)) := selected
    }
  }

  // Committed reads include this cycle's retirement map update. Execution
  // writeback bypass handles the raw load completion/retirement coincidence.
  val writePhysical = VecInit((0 until 5).map(i => tagPhysical(io.writeTag(i))))
  val writeEnable = VecInit((0 until 5).map(i => io.write(i) && tagLive(io.writeTag(i)) &&
    writePhysical(i) =/= 0.U && (!io.flush || committedMask(writePhysical(i)))))
  def readPhysical(address: UInt, forward: Boolean = true): UInt = {
    val stored = Mux(initialized(address), VecInit(banks.map(_(address)))(owner(address)), 0.U)
    val bypass = (0 until 5).foldLeft(stored) { (value, i) =>
      if (forward) Mux(writeEnable(i) && writePhysical(i) === address, io.writeData(i), value) else value
    }
    Mux(address === 0.U, 0.U, bypass)
  }
  for (i <- 0 until 4) io.archData(i) := readPhysical(committedAfter(2)(io.archRead(i)))
  // ROB keeps its deliberately distinct forwarding paths (including NoAlu)
  // outside this stored-data interface to avoid an execute/issue combinational loop.
  for (i <- 0 until tagReads) io.tagData(i) := readPhysical(tagPhysical(io.tagRead(i)), forward = false)
  io.freeCount := PopCount(free)
  io.committedMap := committed
  io.speculativeMap := speculative

  committed := committedAfter(2)
  when(io.flush) {
    speculative := committedAfter(2)
    free := ~committedMask
    tagLive.foreach(_ := false.B)
    // Keep every newly free physical register unreadable until a later
    // writeback initializes it.  Clearing at the free transition preserves
    // the old allocation-time behavior without putting the allocator's rank
    // encoder and decode cone on each initialized bit's D input.
    for (physical <- 0 until entries) {
      when(!committedMask(physical)) { initialized(physical) := false.B }
    }
  }.otherwise {
    speculative := specAfter(2)
    free := allocationMask(2)
    // A register already in `free` is uninitialized by invariant.  Retirement
    // is the only normal-cycle transition into `free`, including a physical
    // register that is released and reallocated in this same cycle.
    for (physical <- 0 until entries) {
      when(released(2)(physical)) { initialized(physical) := false.B }
    }
    for (i <- 0 until 2) {
      when(io.retire(i) && io.retireRd(i) =/= 0.U) { tagLive(io.retireTag(i)) := false.B }
    }
    for (i <- 0 until 2) {
      when(io.allocate(i)) {
        tagLive(io.allocateTag(i)) := requested(i)
        tagPhysical(io.allocateTag(i)) := io.allocatedPhysical(i)
      }
    }
  }
  for (i <- 0 until 5) {
    when(writeEnable(i)) {
      banks(bankForPort(i))(writePhysical(i)) := io.writeData(i)
      owner(writePhysical(i)) := bankForPort(i).U
      initialized(writePhysical(i)) := true.B
    }
  }
  if (!sys.props.get("e91c.synthesis").contains("true"))
    assert(committed(0) === 0.U && speculative(0) === 0.U && !free(0))
}

