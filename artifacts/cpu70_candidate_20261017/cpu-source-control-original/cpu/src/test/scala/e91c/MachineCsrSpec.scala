package e91c
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.backend.SupervisorCsr

class MachineCsrSpec extends AnyFlatSpec with ChiselScalatestTester {
  it should "preserve precise machine traps, vector interrupts, and WARL privilege on MRET" in {
    test(new SupervisorCsr(supervisorEnabled = false)) { d =>
      Seq(d.io.csrWe,d.io.ipiInt,d.io.wbValid,d.io.wbIsMret,d.io.wbIsSret,d.io.wbIsStore,
        d.io.wbEx,d.io.intValid,d.io.misalignValid,d.io.accessFaultValid,d.io.lsMisalignValid,
        d.io.ecallMValid,d.io.breakpointValid,d.io.illegalValid,d.io.instructionAccessFault,
        d.io.instructionPageFault,d.io.loadPageFault,d.io.storePageFault).foreach(_.poke(false.B))
      d.io.csrRnum.poke(0.U); d.io.csrNum.poke(0.U); d.io.csrWmask.poke("hffffffff".U)
      d.io.csrWvalue.poke(0.U); d.io.hwInt.poke(0.U); d.io.wbPc.poke(0.U)
      d.io.wbVaddr.poke(0.U); d.io.retireCount.poke(0.U); d.clock.step()
      def write(n: Int, v: BigInt): Unit = {
        d.io.csrNum.poke(n.U); d.io.csrWvalue.poke(v.U); d.io.csrWe.poke(true.B)
        d.clock.step(); d.io.csrWe.poke(false.B)
      }
      def read(n: Int, v: BigInt): Unit = { d.io.csrRnum.poke(n.U); d.io.csrRvalue.expect(v.U) }
      read(0x301,BigInt("40001101",16))
      // IALIGN=32: neither software nor a trap may retain mepc bit 1.
      write(0x341,BigInt("1c000003",16)); read(0x341,BigInt("1c000000",16))
      // Exercise a low-word overflow with the full three-bit retire count.
      write(0x320,4); write(0xb02,BigInt("fffffffc",16)); write(0xb82,0x1234)
      d.io.retireCount.poke(7.U); write(0x320,0); d.clock.step()
      read(0xb02,3); read(0xb82,0x1235); d.io.retireCount.poke(0.U)
      write(0x320,4); write(0xb02,BigInt("fffffffc",16)); write(0xb82,BigInt("ffffffff",16))
      d.io.retireCount.poke(7.U); write(0x320,0); d.clock.step()
      read(0xb02,3); read(0xb82,0); d.io.retireCount.poke(0.U)
      write(0x300,0); read(0x300,0x1800)
      write(0x305,BigInt("1c001001",16)); write(0x304,0x888); write(0x300,8)
      d.io.hwInt.poke(128.U); d.io.hasInt.expect(true.B)
      d.io.wbValid.poke(true.B); d.io.wbEx.poke(true.B); d.io.intValid.poke(true.B)
      d.io.wbPc.poke("h1c001200".U); d.io.csrNextPc.expect("h1c00101c".U); d.clock.step()
      d.io.wbValid.poke(false.B); d.io.wbEx.poke(false.B); d.io.intValid.poke(false.B)
      d.io.hasInt.expect(false.B); read(0x342,BigInt("80000007",16)); read(0x341,BigInt("1c001200",16))
      d.io.hwInt.poke(0.U); d.io.wbIsMret.poke(true.B); d.io.wbValid.poke(true.B)
      d.io.csrNextPc.expect("h1c001200".U); d.clock.step()
      d.io.wbIsMret.poke(false.B); d.io.wbValid.poke(false.B); d.io.privilege.expect(3.U)
      read(0x300,0x1888)
      for ((cause, flag) <- Seq((0,d.io.misalignValid),(1,d.io.instructionAccessFault),
        (2,d.io.illegalValid),(3,d.io.breakpointValid),(4,d.io.lsMisalignValid),
        (5,d.io.accessFaultValid),(11,d.io.ecallMValid))) {
        d.io.wbValid.poke(true.B); d.io.wbEx.poke(true.B); flag.poke(true.B)
        d.io.wbPc.poke("h1c002004".U); d.io.wbVaddr.poke("hbad00001".U)
        d.io.csrNextPc.expect("h1c001000".U); d.clock.step()
        flag.poke(false.B); d.io.wbValid.poke(false.B); d.io.wbEx.poke(false.B)
        read(0x342,cause); read(0x341,BigInt("1c002004",16))
        read(0x343,if (Set(0,1,4,5).contains(cause)) BigInt("bad00001",16) else BigInt(0))
      }
    }
  }
}
