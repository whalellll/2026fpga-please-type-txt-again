package e91c

import chisel3._
import chiseltest._
import e91c.reg.RobTagRegisterFile
import org.scalatest.flatspec.AnyFlatSpec

class RobTagRegisterFileSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def idle(d: RobTagRegisterFile): Unit = {
    d.io.flush.poke(false.B)
    for (i <- 0 until 2) {
      d.io.clear(i).poke(false.B)
      d.io.allocate(i).poke(false.B); d.io.allocateTag(i).poke(0.U)
      d.io.retire(i).poke(false.B); d.io.retireRd(i).poke(0.U)
      d.io.retireTag(i).poke(0.U); d.io.retireData(i).poke(0.U)
    }
    for (i <- 0 until 5) {
      d.io.write(i).poke(false.B); d.io.writeTag(i).poke(0.U); d.io.writeData(i).poke(0.U)
    }
    for (i <- 0 until 4) d.io.archRead(i).poke(0.U)
    for (i <- 0 until d.tagReads) d.io.tagRead(i).poke(0.U)
  }

  behavior of "RobTagRegisterFile"

  it should "preserve committed state across flush and clear a reused tag" in {
    test(new RobTagRegisterFile) { d =>
      idle(d); d.clock.step()
      d.io.clear(0).poke(true.B); d.io.allocate(0).poke(true.B); d.io.allocateTag(0).poke(3.U); d.clock.step(); idle(d)
      d.io.write(0).poke(true.B); d.io.writeTag(0).poke(3.U)
      d.io.writeData(0).poke("h12345678".U); d.clock.step(); idle(d)
      d.io.tagRead(0).poke(3.U); d.io.tagData(0).expect("h12345678".U)
      d.io.retire(0).poke(true.B); d.io.retireRd(0).poke(7.U); d.io.retireTag(0).poke(3.U)
      d.io.retireData(0).poke("h12345678".U); d.io.archRead(0).poke(7.U)
      d.io.archData(0).expect("h12345678".U); d.io.flush.poke(true.B); d.clock.step(); idle(d)
      d.io.archRead(0).poke(7.U); d.io.archData(0).expect("h12345678".U)
      d.io.clear(0).poke(true.B); d.io.allocate(0).poke(true.B); d.io.allocateTag(0).poke(3.U); d.clock.step(); idle(d)
      d.io.tagRead(0).poke(3.U); d.io.tagData(0).expect(0.U)
    }
  }

  it should "apply dual-retirement WAW order and reject stale writes" in {
    test(new RobTagRegisterFile) { d =>
      idle(d); d.clock.step()
      for (i <- 0 until 2) { d.io.clear(i).poke(true.B); d.io.allocate(i).poke(true.B); d.io.allocateTag(i).poke((10+i).U) }
      d.clock.step(); idle(d)
      for (i <- 0 until 2) { d.io.write(i).poke(true.B); d.io.writeTag(i).poke((10+i).U); d.io.writeData(i).poke((100+i).U) }
      d.clock.step(); idle(d)
      for (i <- 0 until 2) { d.io.retire(i).poke(true.B); d.io.retireRd(i).poke(5.U); d.io.retireTag(i).poke((10+i).U); d.io.retireData(i).poke((100+i).U) }
      d.io.archRead(0).poke(5.U); d.io.archData(0).expect(101.U); d.clock.step(); idle(d)
      d.io.archRead(0).poke(5.U); d.io.archData(0).expect(101.U)
      d.io.write(4).poke(true.B); d.io.writeTag(4).poke(10.U); d.io.writeData(4).poke("hdeadbeef".U)
      d.clock.step(); idle(d); d.io.tagRead(0).poke(10.U); d.io.tagData(0).expect(100.U)
    }
  }

  it should "discard a delayed write when a retiring tag is reused" in {
    test(new RobTagRegisterFile) { d =>
      idle(d); d.clock.step()
      d.io.clear(0).poke(true.B); d.io.allocate(0).poke(true.B); d.io.allocateTag(0).poke(6.U); d.clock.step(); idle(d)
      d.io.write(0).poke(true.B); d.io.writeTag(0).poke(6.U); d.io.writeData(0).poke(11.U)
      d.clock.step(); idle(d)
      d.io.retire(0).poke(true.B); d.io.retireRd(0).poke(9.U); d.io.retireTag(0).poke(6.U); d.io.retireData(0).poke(11.U)
      d.io.clear(1).poke(true.B); d.io.allocate(1).poke(true.B); d.io.allocateTag(1).poke(6.U)
      d.io.write(4).poke(true.B); d.io.writeTag(4).poke(6.U); d.io.writeData(4).poke("hdeadbeef".U)
      d.clock.step(); idle(d); d.io.tagRead(0).poke(6.U); d.io.tagData(0).expect(0.U)
      d.io.archRead(0).poke(9.U); d.io.archData(0).expect(11.U)
      d.io.write(1).poke(true.B); d.io.writeTag(1).poke(6.U); d.io.writeData(1).poke(22.U)
      d.clock.step(); idle(d); d.io.tagRead(0).poke(6.U); d.io.tagData(0).expect(22.U)
    }
  }

  it should "hide every writeback bank on both allocation lanes until the new producer writes" in {
    test(new RobTagRegisterFile) { d =>
      idle(d); d.clock.step()
      for (port <- 0 until 5; lane <- 0 until 2) {
        val tag = 12 + lane
        d.io.clear(lane).poke(true.B); d.io.allocate(lane).poke(true.B)
        d.io.allocateTag(lane).poke(tag.U); d.clock.step(); idle(d)
        d.io.write(port).poke(true.B); d.io.writeTag(port).poke(tag.U)
        d.io.writeData(port).poke((0x100 + port).U); d.clock.step(); idle(d)
        d.io.retire(lane).poke(true.B); d.io.retireRd(lane).poke(8.U)
        d.io.retireTag(lane).poke(tag.U); d.io.retireData(lane).poke((0x100 + port).U)
        d.io.clear(lane).poke(true.B); d.io.allocate(lane).poke(true.B)
        d.io.allocateTag(lane).poke(tag.U)
        d.io.write(port).poke(true.B); d.io.writeTag(port).poke(tag.U)
        d.io.writeData(port).poke("hdeadbeef".U); d.clock.step(); idle(d)
        d.io.tagRead(0).poke(tag.U); d.io.tagData(0).expect(0.U)
        d.io.archRead(0).poke(8.U); d.io.archData(0).expect((0x100 + port).U)
        d.clock.step(2); d.io.tagData(0).expect(0.U)
        val newPort = (port + 1) % 5
        d.io.write(newPort).poke(true.B); d.io.writeTag(newPort).poke(tag.U)
        d.io.writeData(newPort).poke((0x200 + port).U); d.clock.step(); idle(d)
        d.io.tagRead(0).poke(tag.U); d.io.tagData(0).expect((0x200 + port).U)
        d.io.flush.poke(true.B); d.clock.step(); idle(d)
      }
    }
  }
}
