package e91c

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.reg.PhysicalRegisterFile

class PhysicalRegisterFileSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def idle(d: PhysicalRegisterFile): Unit = {
    d.io.flush.poke(false.B)
    for (i <- 0 until 2) {
      d.io.allocate(i).poke(false.B); d.io.allocateRd(i).poke(0.U); d.io.allocateTag(i).poke(0.U)
    }
    for (i <- 0 until 2) {
      d.io.retire(i).poke(false.B); d.io.retireRd(i).poke(0.U); d.io.retireTag(i).poke(0.U)
    }
    for (i <- 0 until 5) {
      d.io.write(i).poke(false.B); d.io.writeTag(i).poke(0.U); d.io.writeData(i).poke(0.U)
      if (i < 4) d.io.archRead(i).poke(0.U)
    }
    for (i <- 0 until d.tagReads) d.io.tagRead(i).poke(0.U)
  }
  behavior of "PhysicalRegisterFile"
  it should "retain committed values across tag reuse and recover after simultaneous retirement" in {
    test(new PhysicalRegisterFile) { d =>
      idle(d); d.clock.step()
      d.io.allocate(0).poke(true.B); d.io.allocateRd(0).poke(1.U)
      d.clock.step(); idle(d)
      d.io.write(0).poke(true.B); d.io.writeData(0).poke(0xaa.U)
      d.clock.step(); idle(d)
      d.io.retire(0).poke(true.B); d.io.retireRd(0).poke(1.U)
      d.io.allocate(0).poke(true.B); d.io.allocateRd(0).poke(1.U); d.io.allocateTag(0).poke(1.U)
      d.io.archRead(0).poke(1.U); d.io.archData(0).expect(0xaa.U)
      d.clock.step(); idle(d)
      d.io.write(1).poke(true.B); d.io.writeTag(1).poke(1.U); d.io.writeData(1).poke(0xbb.U)
      d.io.retire(0).poke(true.B); d.io.retireRd(0).poke(1.U); d.io.retireTag(0).poke(1.U)
      d.io.flush.poke(true.B)
      d.io.allocate(0).poke(true.B); d.io.allocateRd(0).poke(2.U); d.io.allocateTag(0).poke(2.U)
      d.io.archRead(0).poke(1.U); d.io.archData(0).expect(0xbb.U)
      d.clock.step(); idle(d)
      d.io.freeCount.expect((d.entries - 32).U)
      for (i <- 0 until 32) d.io.speculativeMap(i).expect(d.io.committedMap(i).peek())
      d.io.allocate(0).poke(true.B); d.io.allocateRd(0).poke(2.U); d.io.allocateTag(0).poke(0.U)
      d.clock.step(); idle(d)
      d.io.write(0).poke(true.B); d.io.writeData(0).poke(0xcc.U)
      d.clock.step(); idle(d)
      d.io.archRead(0).poke(1.U); d.io.archData(0).expect(0xbb.U)
      d.io.tagRead(0).poke(0.U); d.io.tagData(0).expect(0xcc.U)
      d.io.archRead(1).poke(0.U); d.io.archData(1).expect(0.U)
    }
  }
  it should "retire same-register WAW chains in program order without leaking registers" in {
    test(new PhysicalRegisterFile) { d =>
      idle(d); d.clock.step()
      val tags = Seq(0,16)
      for (i <- 0 until 2) {
        d.io.allocate(i).poke(true.B); d.io.allocateRd(i).poke(5.U); d.io.allocateTag(i).poke(tags(i).U)
      }
      d.clock.step(); idle(d)
      for (i <- 0 until 2) {
        d.io.write(i).poke(true.B); d.io.writeTag(i).poke(tags(i).U); d.io.writeData(i).poke((100+i).U)
        d.io.retire(i).poke(true.B); d.io.retireRd(i).poke(5.U); d.io.retireTag(i).poke(tags(i).U)
      }
      d.io.flush.poke(true.B)
      d.io.archRead(0).poke(5.U); d.io.archData(0).expect(101.U)
      d.clock.step(); idle(d)
      d.io.archRead(0).poke(5.U); d.io.archData(0).expect(101.U)
      d.io.freeCount.expect((d.entries - 32).U)
      val mapped = (0 until 32).map(i => d.io.committedMap(i).peek().litValue)
      assert(mapped.distinct.size == 32)
    }
  }
  it should "clear a valid value when retirement releases and reallocates its physical register" in {
    test(new PhysicalRegisterFile) { d =>
      idle(d); d.clock.step()

      // Commit tag 0 in physical 32, making that physical register valid.
      d.io.allocate(0).poke(true.B); d.io.allocateRd(0).poke(1.U); d.io.allocateTag(0).poke(0.U)
      d.io.allocatedPhysical(0).expect(32.U)
      d.clock.step(); idle(d)
      d.io.write(0).poke(true.B); d.io.writeTag(0).poke(0.U); d.io.writeData(0).poke("hfeedface".U)
      d.io.retire(0).poke(true.B); d.io.retireRd(0).poke(1.U); d.io.retireTag(0).poke(0.U)
      d.clock.step(); idle(d)

      // Move r1 to physical 1.  Retiring it releases valid physical 32 while
      // a new r2 destination reuses physical 32 in that very cycle.
      d.io.allocate(0).poke(true.B); d.io.allocateRd(0).poke(1.U); d.io.allocateTag(0).poke(1.U)
      d.io.allocatedPhysical(0).expect(1.U)
      d.clock.step(); idle(d)
      d.io.write(0).poke(true.B); d.io.writeTag(0).poke(1.U); d.io.writeData(0).poke("h12345678".U)
      d.io.retire(0).poke(true.B); d.io.retireRd(0).poke(1.U); d.io.retireTag(0).poke(1.U)
      d.io.allocate(0).poke(true.B); d.io.allocateRd(0).poke(2.U); d.io.allocateTag(0).poke(2.U)
      d.io.allocatedPhysical(0).expect(32.U)
      d.clock.step(); idle(d)

      d.io.tagRead(0).poke(2.U)
      d.io.tagData(0).expect(0.U)
      d.io.write(0).poke(true.B); d.io.writeTag(0).poke(2.U); d.io.writeData(0).poke("hcafebabe".U)
      d.clock.step(); idle(d)
      d.io.tagRead(0).poke(2.U)
      d.io.tagData(0).expect("hcafebabe".U)
    }
  }
}
