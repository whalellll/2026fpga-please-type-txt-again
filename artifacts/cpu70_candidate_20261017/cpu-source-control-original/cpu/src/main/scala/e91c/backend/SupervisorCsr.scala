package e91c.backend

import chisel3._
import chisel3.util._
import e91c.config.Params.ENABLE_SUPERVISOR

object CsrAddressMap {
  private val allAddresses: Seq[Int] = Seq(0x100,0x104,0x105,0x106,0x10a,0x140,0x141,0x142,0x143,0x144,0x180,
    0x300,0x301,0x302,0x303,0x304,0x305,0x306,0x30a,0x310,0x31a,0x320,
    0x340,0x341,0x342,0x343,0x344,0xb00,0xb02,0xb80,0xb82,
    0xc00,0xc01,0xc02,0xc80,0xc81,0xc82,0xf11,0xf12,0xf13,0xf14,0xf15) ++
    (0x3a0 to 0x3a3) ++ (0x3b0 to 0x3bf)
  val addresses = if (ENABLE_SUPERVISOR) allAddresses else
    allAddresses.filter(n => (n >> 8) != 1 && n != 0x302 && n != 0x303)
}

/** RV32 M/S/U control, precise delegated traps and Sv32 context.
  * Svade (software A/D faults), no floating point, no PMP entries or H extension.
  * Reference: RISC-V privileged architecture, 20240411.
  */
class SupervisorCsr(val supervisorEnabled: Boolean = ENABLE_SUPERVISOR) extends Module {
  val io = IO(new Bundle {
    val csrRnum=Input(UInt(12.W)); val csrNum=Input(UInt(12.W)); val csrWe=Input(Bool())
    val csrWmask=Input(UInt(32.W)); val csrWvalue=Input(UInt(32.W))
    val hwInt=Input(UInt(8.W)); val ipiInt=Input(Bool())
    val wbValid=Input(Bool()); val wbPc=Input(UInt(32.W))
    val wbIsMret=Input(Bool()); val wbIsSret=Input(Bool())
    val wbVaddr=Input(UInt(32.W)); val wbIsStore=Input(Bool()); val retireCount=Input(UInt(3.W))
    val wbEx=Input(Bool()); val intValid=Input(Bool())
    val misalignValid=Input(Bool()); val accessFaultValid=Input(Bool())
    val lsMisalignValid=Input(Bool()); val ecallMValid=Input(Bool())
    val breakpointValid=Input(Bool()); val illegalValid=Input(Bool())
    val instructionAccessFault=Input(Bool())
    val instructionPageFault=Input(Bool()); val loadPageFault=Input(Bool()); val storePageFault=Input(Bool())
    val csrNextPc=Output(UInt(32.W)); val hasInt=Output(Bool()); val csrRvalue=Output(UInt(32.W))
    val cycleCounter=Output(UInt(64.W)); val privilege=Output(UInt(2.W))
    val dataPrivilege=Output(UInt(2.W)); val satp=Output(UInt(32.W)); val status=Output(UInt(32.W))
    val counterAccess=Output(UInt(3.W))
  })
  if (supervisorEnabled) {
  val privilege = RegInit(3.U(2.W))
  val status = RegInit("h00001800".U(32.W))
  val mie=RegInit(0.U(32.W)); val mipSoftware=RegInit(0.U(32.W))
  val medeleg=RegInit(0.U(32.W)); val mideleg=RegInit(0.U(32.W))
  val mtvec=RegInit("h1c000000".U(32.W)); val stvec=RegInit(0.U(32.W))
  val mepc=RegInit(0.U(32.W)); val sepc=RegInit(0.U(32.W))
  val mcause=RegInit(0.U(32.W)); val scause=RegInit(0.U(32.W))
  val mtval=RegInit(0.U(32.W)); val stval=RegInit(0.U(32.W))
  val mscratch=RegInit(0.U(32.W)); val sscratch=RegInit(0.U(32.W))
  val satp=RegInit(0.U(32.W))
  val mcounteren=RegInit(0.U(3.W)); val scounteren=RegInit(0.U(3.W))
  val countInhibit=RegInit(0.U(3.W))
  val cycle=RegInit(0.U(64.W)); val instret=RegInit(0.U(64.W))
  val sstatusMask="h000c0122".U(32.W)
  val mstatusMask="h007e19aa".U(32.W)
  val interruptMask=(if (supervisorEnabled) "h00000aaa" else "h00000888").U(32.W)
  val supervisorInterruptMask="h00000222".U(32.W)
  // Platform pins: bit 0 MEIP, bit 1 MSIP, bit 6 SEIP, bit 7 MTIP.
  // Bits 2..5 remain machine external sources for legacy integrations.
  val mip = mipSoftware | Mux(io.hwInt(0) || io.hwInt(5,2).orR,"h800".U,0.U) |
    Mux(io.hwInt(6),"h200".U,0.U) | Mux(io.hwInt(7),"h80".U,0.U) |
    Mux(io.ipiInt || io.hwInt(1),"h8".U,0.U)
  val pending = mie & mip & interruptMask
  val candidates = Seq(11,3,7,9,1,5).map { bit =>
    val delegated = mideleg(bit)
    val enabled = Mux(delegated,privilege === 0.U || (privilege === 1.U && status(1)),
      privilege =/= 3.U || status(3))
    pending(bit) && enabled
  }
  val interruptCause = PriorityMux(candidates.zip(Seq(11,3,7,9,1,5).map(_.U(5.W))))
  io.hasInt := candidates.reduce(_ || _)
  val exceptionCause = MuxCase(2.U(5.W),Seq(
    io.misalignValid -> 0.U, io.instructionAccessFault -> 1.U,
    io.illegalValid -> 2.U, io.breakpointValid -> 3.U,
    io.lsMisalignValid -> Mux(io.wbIsStore,6.U,4.U),
    io.accessFaultValid -> Mux(io.wbIsStore,7.U,5.U),
    io.ecallMValid -> (8.U + privilege),
    io.instructionPageFault -> 12.U, io.loadPageFault -> 13.U, io.storePageFault -> 15.U))
  val cause = Mux(io.intValid,interruptCause,exceptionCause)
  // Keep the synchronous exception path out of a dynamic medeleg index.  The
  // ordering exactly mirrors exceptionCause, including load/store cause pairs.
  val exceptionDelegatedBit = MuxCase(false.B,Seq(
    io.misalignValid -> medeleg(0), io.instructionAccessFault -> medeleg(1),
    io.illegalValid -> medeleg(2), io.breakpointValid -> medeleg(3),
    io.lsMisalignValid -> Mux(io.wbIsStore,medeleg(6),medeleg(4)),
    io.accessFaultValid -> Mux(io.wbIsStore,medeleg(7),medeleg(5)),
    io.ecallMValid -> Mux(privilege === 0.U,medeleg(8),medeleg(9)),
    io.instructionPageFault -> medeleg(12), io.loadPageFault -> medeleg(13),
    io.storePageFault -> medeleg(15)))
  val interruptDelegated = supervisorEnabled.B && privilege =/= 3.U && mideleg(interruptCause)
  val exceptionDelegated = supervisorEnabled.B && privilege =/= 3.U && exceptionDelegatedBit
  val delegated = Mux(io.intValid,interruptDelegated,exceptionDelegated)

  // Vectored mode applies only to interrupts.  Give synchronous exceptions a
  // separate direct-base cone so commit exception signals do not traverse the
  // interrupt cause offset adder on their way to the precise flush PC.
  val mtvecBase = Cat(mtvec(31,2),0.U(2.W))
  val stvecBase = Cat(stvec(31,2),0.U(2.W))
  val exceptionVectorPc = Mux(exceptionDelegated,stvecBase,mtvecBase)
  val interruptVector = Mux(interruptDelegated,stvec,mtvec)
  val interruptVectorPc = Cat(interruptVector(31,2),0.U(2.W)) +
    Mux(interruptVector(1,0) === 1.U,Cat(interruptCause,0.U(2.W)),0.U)
  val vectorPc = Mux(io.intValid,interruptVectorPc,exceptionVectorPc)
  io.csrNextPc := Mux(io.wbIsSret,sepc,Mux(io.wbIsMret,mepc,vectorPc))
  io.privilege := privilege
  io.dataPrivilege := Mux(privilege===3.U && status(17),status(12,11),privilege)
  io.satp := satp
  io.status := status
  io.cycleCounter := cycle
  io.counterAccess := Mux(privilege===3.U,7.U,Mux(privilege===1.U,mcounteren,mcounteren & scounteren))

  def csrValue(number: UInt): UInt = MuxLookup(number,0.U(32.W))(Seq(
    0x100.U -> (status & sstatusMask), 0x104.U -> (mie & mideleg), 0x105.U -> stvec,
    0x106.U -> scounteren, 0x140.U -> sscratch, 0x141.U -> sepc, 0x142.U -> scause,
    0x143.U -> stval, 0x144.U -> (mip & mideleg), 0x180.U -> satp,
    0x300.U -> status, 0x301.U -> (if (supervisorEnabled) "h40141101" else "h40001101").U, 0x302.U -> medeleg, 0x303.U -> mideleg,
    0x304.U -> mie, 0x305.U -> mtvec, 0x306.U -> mcounteren, 0x320.U -> countInhibit,
    0x340.U -> mscratch, 0x341.U -> mepc, 0x342.U -> mcause, 0x343.U -> mtval, 0x344.U -> mip,
    0xb00.U -> cycle(31,0), 0xb80.U -> cycle(63,32), 0xb02.U -> instret(31,0), 0xb82.U -> instret(63,32),
    0xc00.U -> cycle(31,0), 0xc80.U -> cycle(63,32), 0xc01.U -> cycle(31,0), 0xc81.U -> cycle(63,32),
    0xc02.U -> instret(31,0), 0xc82.U -> instret(63,32), 0xf13.U -> 1.U))
  io.csrRvalue := csrValue(io.csrRnum)
  // Commit hardwires the mask to all ones, and FuMdu has already applied the
  // CSR instruction's read/modify/write operation to produce the full value.
  // Consuming it directly avoids a second full CSR read mux on csrNum.
  val written = io.csrWvalue
  def vectorWrite(value: UInt): UInt = Cat(value(31,2),0.U(1.W),value(1,0)===1.U)
  def statusWrite(value: UInt): UInt = {
    val implemented = value & mstatusMask
    Mux(implemented(12,11)===2.U,implemented & ~"h1800".U(32.W),implemented)
  }
  val cycleLowNext = (cycle(31,0) + 1.U)(31,0)
  val cycleHighNext = cycle(63,32) + cycle(31,0).andR
  when(!countInhibit(0)) { cycle := Cat(cycleHighNext,cycleLowNext) }
  when(!countInhibit(2)) { instret := instret+io.retireCount }
  val addressException = io.misalignValid || io.lsMisalignValid || io.accessFaultValid ||
    io.instructionAccessFault || io.instructionPageFault || io.loadPageFault || io.storePageFault
  val trapValue = Mux(addressException,io.wbVaddr,0.U)
  val trapCause = Cat(io.intValid,0.U(26.W),cause)
  when(io.wbValid && io.wbEx) {
    when(delegated) {
      sepc := io.wbPc & "hfffffffc".U; scause := trapCause; stval := trapValue
      status := (status & ~"h122".U(32.W)) | (status(1).asUInt << 5) | ((privilege=/=0.U).asUInt << 8)
      privilege := 1.U
    }.otherwise {
      mepc := io.wbPc & "hfffffffc".U; mcause := trapCause; mtval := trapValue
      status := (status & ~"h1888".U(32.W)) | (status(3).asUInt << 7) | (privilege << 11)
      privilege := 3.U
    }
  }.elsewhen(io.wbValid && io.wbIsSret) {
    privilege := Mux(status(8),1.U,0.U)
    status := (status & ~"h20122".U(32.W)) | (status(5).asUInt << 1) | "h20".U
  }.elsewhen(io.wbValid && io.wbIsMret) {
    privilege := status(12,11)
    status := (status & ~"h1888".U(32.W) & Mux(status(12,11)=/=3.U,~"h20000".U(32.W),"hffffffff".U)) |
      (status(7).asUInt << 3) | "h80".U
  }.elsewhen(io.csrWe) {
    switch(io.csrNum) {
      is(0x100.U) { status := (status & ~sstatusMask) | (written & sstatusMask) }
      is(0x104.U) { mie := (mie & ~mideleg) | (written & mideleg & supervisorInterruptMask) }
      is(0x105.U) { stvec := vectorWrite(written) }
      is(0x106.U) { scounteren := written(2,0) }
      is(0x140.U) { sscratch := written }
      is(0x141.U) { sepc := written & "hfffffffc".U }
      is(0x142.U) { scause := written }
      is(0x143.U) { stval := written }
      is(0x144.U) { mipSoftware := (mipSoftware & ~2.U(32.W)) | (written & mideleg & 2.U) }
      is(0x180.U) { satp := written }
      is(0x300.U) { status := statusWrite(written) }
      is(0x302.U) { medeleg := written & "hb3ff".U }
      is(0x303.U) { mideleg := written & supervisorInterruptMask }
      is(0x304.U) { mie := written & interruptMask }
      is(0x305.U) { mtvec := vectorWrite(written) }
      is(0x306.U) { mcounteren := written(2,0) }
      is(0x320.U) { countInhibit := written(2,0) & 5.U }
      is(0x340.U) { mscratch := written }
      is(0x341.U) { mepc := written & "hfffffffc".U }
      is(0x342.U) { mcause := written }
      is(0x343.U) { mtval := written }
      is(0x344.U) { mipSoftware := written & "h22a".U }
      is(0xb00.U) { cycle := Cat(cycle(63,32),written) }
      is(0xb80.U) { cycle := Cat(written,cycle(31,0)) }
      is(0xb02.U) { instret := Cat(instret(63,32),written) }
      is(0xb82.U) { instret := Cat(written,instret(31,0)) }
    }
  }
  } else {
    // Machine-only implementation: no unreachable supervisor CSR muxes.
    val globalEnable = RegInit(false.B)
    val previousEnable = RegInit(false.B)
    val enables = RegInit(0.U(3.W)) // MEIE, MTIE, MSIE
    val mtvec = RegInit("h1c000000".U(32.W))
    val mepc = RegInit(0.U(32.W))
    val mcause = RegInit(0.U(32.W))
    val mtval = RegInit(0.U(32.W))
    val scratch = RegInit(0.U(32.W))
    val inhibit = RegInit(0.U(3.W))
    val cycle = RegInit(0.U(64.W))
    val instret = RegInit(0.U(64.W))
    val external = io.hwInt(0) || io.hwInt(5,2).orR
    val timer = io.hwInt(7)
    val software = io.ipiInt || io.hwInt(1)
    val externalPending = external && enables(2)
    val softwarePending = software && enables(0)
    val timerPending = timer && enables(1)
    val interruptCause = Mux(externalPending,11.U(5.W),Mux(softwarePending,3.U(5.W),7.U(5.W)))
    val exceptionCause = MuxCase(2.U(5.W),Seq(
      io.misalignValid -> 0.U, io.instructionAccessFault -> 1.U,
      io.illegalValid -> 2.U, io.breakpointValid -> 3.U,
      io.lsMisalignValid -> Mux(io.wbIsStore,6.U,4.U),
      io.accessFaultValid -> Mux(io.wbIsStore,7.U,5.U), io.ecallMValid -> 11.U))
    val vectorBase = Cat(mtvec(31,2),0.U(2.W))
    val interruptVector = vectorBase + Mux(mtvec(0),Cat(interruptCause,0.U(2.W)),0.U)
    io.csrNextPc := Mux(io.wbIsMret,mepc,Mux(io.intValid,interruptVector,vectorBase))
    io.hasInt := globalEnable && (externalPending || timerPending || softwarePending)
    io.privilege := 3.U; io.dataPrivilege := 3.U; io.satp := 0.U; io.counterAccess := 7.U
    io.status := "h1800".U | (previousEnable.asUInt << 7) | (globalEnable.asUInt << 3)
    io.cycleCounter := cycle
    val mieValue = (enables(2).asUInt << 11) | (enables(1).asUInt << 7) | (enables(0).asUInt << 3)
    val mipValue = (external.asUInt << 11) | (timer.asUInt << 7) | (software.asUInt << 3)
    io.csrRvalue := MuxLookup(io.csrRnum,0.U(32.W))(Seq(
      0x300.U -> io.status, 0x301.U -> "h40001101".U,
      0x304.U -> mieValue, 0x305.U -> mtvec, 0x320.U -> inhibit,
      0x340.U -> scratch, 0x341.U -> mepc, 0x342.U -> mcause, 0x343.U -> mtval, 0x344.U -> mipValue,
      0xb00.U -> cycle(31,0), 0xb80.U -> cycle(63,32),
      0xb02.U -> instret(31,0), 0xb82.U -> instret(63,32),
      0xc00.U -> cycle(31,0), 0xc80.U -> cycle(63,32),
      0xc01.U -> cycle(31,0), 0xc81.U -> cycle(63,32),
      0xc02.U -> instret(31,0), 0xc82.U -> instret(63,32), 0xf13.U -> 1.U))
    // Independent 8-bit increment slices keep the late CSR-write select out
    // of a 32-bit carry chain on the cycle counter D input.
    val cycleLowBytes = (0 until 4).map { byte =>
      val carry = if (byte == 0) true.B else cycle(8 * byte - 1, 0).andR
      (cycle(8 * byte + 7, 8 * byte) + carry)(7, 0)
    }
    val cycleLowNext = Cat(cycleLowBytes.reverse)
    val cycleHighCarry = cycle(31,0).andR
    val cycleHighBytes = (0 until 4).map { byte =>
      val carry = cycleHighCarry &&
        (if (byte == 0) true.B else cycle(8 * byte + 31, 32).andR)
      (cycle(8 * byte + 39, 8 * byte + 32) + carry)(7, 0)
    }
    val cycleHighNext = Cat(cycleHighBytes.reverse)
    // Select CSR writes after the free-running incrementers. This keeps the
    // late retirement/CSR-write decision out of the counter carry chain.
    val csrCycleWrite = io.csrWe && !(io.wbValid && (io.wbEx || io.wbIsMret))
    val cycleWriteLow = csrCycleWrite && io.csrNum === 0xb00.U
    val cycleWriteHigh = csrCycleWrite && io.csrNum === 0xb80.U
    val cycleLowRun = Mux(inhibit(0), cycle(31,0), cycleLowNext)
    val cycleHighRun = Mux(inhibit(0), cycle(63,32), cycleHighNext)
    cycle := Cat(Mux(cycleWriteHigh, io.csrWvalue,
      Mux(cycleWriteLow, cycle(63,32), cycleHighRun)),
      Mux(cycleWriteLow, io.csrWvalue,
        Mux(cycleWriteHigh, cycle(31,0), cycleLowRun)))
    // Retire count is only three bits wide. Propagate each byte's carry from
    // the old counter in parallel, keeping the late commit decision out of
    // full-width low- and high-word carry chains.
    val retireCarry3 = (instret(2,0) +& io.retireCount)(3)
    val retireCarry8 = retireCarry3 && instret(7,3).andR
    val retireCarry16 = retireCarry8 && instret(15,8).andR
    val retireCarry24 = retireCarry16 && instret(23,16).andR
    val retireLow = Cat(
      (instret(31,24) + retireCarry24)(7,0),
      (instret(23,16) + retireCarry16)(7,0),
      (instret(15,8) + retireCarry8)(7,0),
      (instret(7,0) + io.retireCount)(7,0))
    val retireCarry = retireCarry3 && instret(31,3).andR
    val retireHighBytes = (0 until 4).map { byte =>
      val carry = retireCarry &&
        (if (byte == 0) true.B else instret(8 * byte + 31, 32).andR)
      (instret(8 * byte + 39, 8 * byte + 32) + carry)(7, 0)
    }
    val retireHigh = Cat(retireHighBytes.reverse)
    when(!inhibit(2)) { instret := Cat(retireHigh,retireLow) }
    val trapWriteMepc = io.wbValid && io.wbEx
    val mretBlocksCsr = io.wbValid && io.wbIsMret
    val csrWriteMepc = io.csrWe && !trapWriteMepc && !mretBlocksCsr && io.csrNum === 0x341.U
    when(trapWriteMepc) {
      mepc := io.wbPc & "hfffffffc".U
    }.elsewhen(csrWriteMepc) {
      mepc := io.csrWvalue & "hfffffffc".U
    }
    // Decode the CSR address before the final trap/CSR choice. A trap wins
    // even if MRET is also asserted; MRET otherwise suppresses CSR writes.
    val csrSelectMtval = io.csrWe && io.csrNum === 0x343.U
    val writeMtval = trapWriteMepc || (csrSelectMtval && !mretBlocksCsr)
    val trapMtval = Mux(io.misalignValid || io.instructionAccessFault ||
      io.lsMisalignValid || io.accessFaultValid, io.wbVaddr, 0.U)
    when(writeMtval) { mtval := Mux(trapWriteMepc, trapMtval, io.csrWvalue) }
    when(io.wbValid && io.wbEx) {
      mcause := Cat(io.intValid,0.U(26.W),Mux(io.intValid,interruptCause,exceptionCause))
      previousEnable := globalEnable; globalEnable := false.B
    }.elsewhen(io.wbValid && io.wbIsMret) {
      globalEnable := previousEnable; previousEnable := true.B
    }.elsewhen(io.csrWe) {
      val value = io.csrWvalue
      switch(io.csrNum) {
        is(0x300.U) { globalEnable := value(3); previousEnable := value(7) }
        is(0x304.U) { enables := Cat(value(11),value(7),value(3)) }
        is(0x305.U) { mtvec := Cat(value(31,2),0.U(1.W),value(1,0)===1.U) }
        is(0x320.U) { inhibit := value(2,0) & 5.U }
        is(0x340.U) { scratch := value }
        is(0x342.U) { mcause := value }
        is(0xb02.U) { instret := Cat(instret(63,32),value) }
        is(0xb82.U) { instret := Cat(value,instret(31,0)) }
      }
    }
  }
}
