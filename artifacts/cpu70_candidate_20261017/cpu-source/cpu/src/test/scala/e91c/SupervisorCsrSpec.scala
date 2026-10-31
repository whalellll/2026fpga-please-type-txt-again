package e91c

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.backend.SupervisorCsr

class SupervisorCsrSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def init(d: SupervisorCsr): Unit = {
    Seq(d.io.csrWe,d.io.ipiInt,d.io.wbValid,d.io.wbIsMret,d.io.wbIsSret,d.io.wbIsStore,
      d.io.wbEx,d.io.intValid,d.io.misalignValid,d.io.accessFaultValid,d.io.lsMisalignValid,
      d.io.ecallMValid,d.io.breakpointValid,d.io.illegalValid,d.io.instructionAccessFault,
      d.io.instructionPageFault,d.io.loadPageFault,d.io.storePageFault).foreach(_.poke(false.B))
    d.io.csrRnum.poke(0.U); d.io.csrNum.poke(0.U); d.io.csrWmask.poke("hffffffff".U)
    d.io.csrWvalue.poke(0.U); d.io.hwInt.poke(0.U); d.io.wbPc.poke(0.U)
    d.io.wbVaddr.poke(0.U); d.io.retireCount.poke(0.U)
    d.clock.step()
  }
  private def write(d: SupervisorCsr, number: Int, value: BigInt): Unit = {
    d.io.csrNum.poke(number.U); d.io.csrWvalue.poke(value.U); d.io.csrWe.poke(true.B)
    d.clock.step(); d.io.csrWe.poke(false.B)
  }
  private def read(d: SupervisorCsr, number: Int, value: BigInt): Unit = {
    d.io.csrRnum.poke(number.U); d.io.csrRvalue.expect(value.U)
  }
  private def mret(d: SupervisorCsr): Unit = {
    d.io.wbValid.poke(true.B); d.io.wbIsMret.poke(true.B); d.clock.step()
    d.io.wbValid.poke(false.B); d.io.wbIsMret.poke(false.B)
  }
  behavior of "SupervisorCsr"
  it should "delegate a user ECALL precisely and return to user mode with SRET" in {
    test(new SupervisorCsr(supervisorEnabled = true)) { d =>
      init(d)
      write(d,0x302,1<<8); write(d,0x105,BigInt("80000001",16))
      write(d,0x341,BigInt("80001000",16)); write(d,0x300,0x80)
      mret(d); d.io.privilege.expect(0.U)
      d.io.wbValid.poke(true.B); d.io.wbEx.poke(true.B); d.io.ecallMValid.poke(true.B)
      d.io.wbPc.poke("h80001010".U); d.io.csrNextPc.expect("h80000000".U)
      d.clock.step(); d.io.wbValid.poke(false.B); d.io.wbEx.poke(false.B); d.io.ecallMValid.poke(false.B)
      d.io.privilege.expect(1.U); read(d,0x142,8); read(d,0x141,BigInt("80001010",16))
      d.io.wbIsSret.poke(true.B); d.io.wbValid.poke(true.B)
      d.io.csrNextPc.expect("h80001010".U); d.clock.step()
      d.io.wbValid.poke(false.B); d.io.wbIsSret.poke(false.B); d.io.privilege.expect(0.U)
    }
  }
  it should "mask delegated interrupts in M mode and vector supervisor timer interrupts" in {
    test(new SupervisorCsr(supervisorEnabled = true)) { d =>
      init(d)
      write(d,0x303,0x20); write(d,0x304,0x20); write(d,0x344,0x20)
      write(d,0x105,BigInt("80000001",16))
      d.io.hasInt.expect(false.B)
      write(d,0x300,0x882); mret(d)
      d.io.privilege.expect(1.U); d.io.hasInt.expect(true.B)
      d.io.wbValid.poke(true.B); d.io.wbEx.poke(true.B); d.io.intValid.poke(true.B)
      d.io.wbPc.poke("h80002000".U); d.io.csrNextPc.expect("h80000014".U)
      d.clock.step(); d.io.wbValid.poke(false.B); d.io.wbEx.poke(false.B); d.io.intValid.poke(false.B)
      read(d,0x142,BigInt("80000005",16)); read(d,0x141,BigInt("80002000",16))
      d.io.hasInt.expect(false.B)
    }
  }
  it should "apply MPRV only to data and preserve the faulting virtual address" in {
    test(new SupervisorCsr(supervisorEnabled = true)) { d =>
      init(d)
      write(d,0x300,0xe0800)
      d.io.privilege.expect(3.U); d.io.dataPrivilege.expect(1.U)
      write(d,0x180,BigInt("80080000",16)); d.io.satp.expect("h80080000".U)
      d.io.wbValid.poke(true.B); d.io.wbEx.poke(true.B); d.io.loadPageFault.poke(true.B)
      d.io.wbPc.poke("h80001000".U); d.io.wbVaddr.poke("hdeadbeef".U)
      d.clock.step(); d.io.wbValid.poke(false.B); d.io.wbEx.poke(false.B); d.io.loadPageFault.poke(false.B)
      read(d,0x342,13); read(d,0x343,BigInt("deadbeef",16))
      d.io.privilege.expect(3.U)
    }
  }
  it should "use the selected load/store delegation bit and keep synchronous traps direct" in {
    test(new SupervisorCsr(supervisorEnabled = true)) { d =>
      init(d)
      // Delegate store-access-fault (7), but not load-access-fault (5).  A
      // vectored stvec must still use its direct base for synchronous traps.
      write(d,0x302,1<<7); write(d,0x105,BigInt("80000101",16))
      write(d,0x341,BigInt("80001000",16)); write(d,0x300,0x80)
      mret(d); d.io.privilege.expect(0.U)

      d.io.wbValid.poke(true.B); d.io.wbEx.poke(true.B)
      d.io.accessFaultValid.poke(true.B); d.io.wbIsStore.poke(true.B)
      d.io.wbPc.poke("h80002000".U); d.io.wbVaddr.poke("h1fe80000".U)
      d.io.csrNextPc.expect("h80000100".U)
      d.clock.step()
      d.io.wbValid.poke(false.B); d.io.wbEx.poke(false.B)
      d.io.accessFaultValid.poke(false.B); d.io.wbIsStore.poke(false.B)
      d.io.privilege.expect(1.U); read(d,0x142,7)

      // Return to U, then prove the corresponding load cause is not delegated.
      d.io.wbIsSret.poke(true.B); d.io.wbValid.poke(true.B); d.clock.step()
      d.io.wbValid.poke(false.B); d.io.wbIsSret.poke(false.B)
      d.io.wbValid.poke(true.B); d.io.wbEx.poke(true.B)
      d.io.accessFaultValid.poke(true.B); d.io.wbIsStore.poke(false.B)
      d.io.csrNextPc.expect("h1c000000".U)
      d.clock.step()
      d.io.wbValid.poke(false.B); d.io.wbEx.poke(false.B); d.io.accessFaultValid.poke(false.B)
      d.io.privilege.expect(3.U); read(d,0x342,5)
    }
  }
  it should "preserve exception priority when more than one indication is present" in {
    test(new SupervisorCsr(supervisorEnabled = true)) { d =>
      init(d)
      // Misaligned instruction (cause 0) precedes illegal instruction (cause
      // 2); only cause 2 is delegated, so both next PC and mcause expose any
      // accidental OR-of-delegation implementation.
      write(d,0x302,1<<2); write(d,0x105,BigInt("80000401",16))
      write(d,0x341,BigInt("80001000",16)); write(d,0x300,0x80)
      mret(d)
      d.io.wbValid.poke(true.B); d.io.wbEx.poke(true.B)
      d.io.misalignValid.poke(true.B); d.io.illegalValid.poke(true.B)
      d.io.csrNextPc.expect("h1c000000".U)
      d.clock.step()
      d.io.wbValid.poke(false.B); d.io.wbEx.poke(false.B)
      d.io.misalignValid.poke(false.B); d.io.illegalValid.poke(false.B)
      d.io.privilege.expect(3.U); read(d,0x342,0)
    }
  }
  it should "carry the machine cycle counter across byte and word boundaries" in {
    test(new SupervisorCsr(supervisorEnabled = false)) { d =>
      init(d)
      write(d, 0x320, 1) // freeze CY before loading the boundary value
      write(d, 0xb00, BigInt("fffffffe", 16))
      read(d, 0xb00, BigInt("fffffffe", 16))
      write(d, 0x320, 0)
      d.clock.step()
      read(d, 0xb00, BigInt("ffffffff", 16))
      d.clock.step()
      read(d, 0xb00, 0)
      read(d, 0xb80, 1)
      write(d, 0xb80, BigInt("12345678", 16))
      read(d, 0xb80, BigInt("12345678", 16))
      read(d, 0xb00, 0)
      write(d, 0x320, 1)
      write(d, 0xb00, BigInt("fffffffe", 16))
      write(d, 0xb80, BigInt("ffffffff", 16))
      write(d, 0x320, 0)
      d.clock.step()
      read(d, 0xb80, BigInt("ffffffff", 16))
      d.clock.step()
      read(d, 0xb80, 0)
    }
  }
  it should "count retirement across segment boundaries and preserve partial CSR writes" in {
    test(new SupervisorCsr(supervisorEnabled = false)) { d =>
      init(d)
      val mask32 = (BigInt(1) << 32) - 1
      val mask64 = (BigInt(1) << 64) - 1
      for (seed <- Seq("0000000000000006", "00000000000000fe",
        "000000000000fffe", "00000000fffffffe", "fffffffffffffffe")) {
        var expected = BigInt(seed, 16)
        d.io.retireCount.poke(0.U)
        write(d, 0x320, 4)
        write(d, 0xb02, expected & mask32)
        write(d, 0xb82, expected >> 32)
        write(d, 0x320, 0)
        for (count <- Seq(1, 2, 0, 7)) {
          d.io.retireCount.poke(count.U)
          d.clock.step()
          expected = (expected + count) & mask64
          read(d, 0xb02, expected & mask32)
          read(d, 0xb82, expected >> 32)
        }
        d.io.retireCount.poke(2.U)
        write(d, 0xb02, 0x1234)
        read(d, 0xb02, 0x1234)
        read(d, 0xb82, expected >> 32)
        write(d, 0xb82, 0x5678)
        read(d, 0xb02, 0x1234)
        read(d, 0xb82, 0x5678)
        d.io.retireCount.poke(0.U)
      }
    }
  }
}

