package e91c
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.reg.PhysicalRegisterFile
class PrfBankLayoutSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def idle(d:PhysicalRegisterFile):Unit = {
    d.io.flush.poke(false.B)
    for(i<-0 until 2) {
      d.io.allocate(i).poke(false.B); d.io.allocateRd(i).poke(0.U); d.io.allocateTag(i).poke(0.U)
      d.io.retire(i).poke(false.B); d.io.retireRd(i).poke(0.U); d.io.retireTag(i).poke(0.U)
    }
    for(i<-0 until 5) {d.io.write(i).poke(false.B);d.io.writeTag(i).poke(0.U);d.io.writeData(i).poke(0.U)}
    d.io.archRead.foreach(_.poke(0.U)); d.io.tagRead.foreach(_.poke(0.U))
  }
  "PRF banks" should "retain every writer and last-port priority through retirement and physical reuse" in {
    test(new PhysicalRegisterFile) { d =>
      idle(d); d.clock.step()
      for(p<-0 until 5) {
        d.io.allocate(0).poke(true.B);d.io.allocateRd(0).poke((p+1).U);d.io.allocateTag(0).poke(p.U)
        d.clock.step();idle(d)
        d.io.write(p).poke(true.B);d.io.writeTag(p).poke(p.U);d.io.writeData(p).poke((0x100+p).U)
        d.clock.step();idle(d)
        d.io.tagRead(0).poke(p.U);d.io.tagData(0).expect((0x100+p).U)
        d.io.retire(0).poke(true.B);d.io.retireRd(0).poke((p+1).U);d.io.retireTag(0).poke(p.U)
        d.clock.step();idle(d)
      }
      for(p<-0 until 5) {d.io.archRead(0).poke((p+1).U);d.io.archData(0).expect((0x100+p).U)}
      d.io.allocate(0).poke(true.B);d.io.allocateRd(0).poke(6.U);d.io.allocateTag(0).poke(5.U)
      d.clock.step();idle(d)
      for(p<-0 until 5) {d.io.write(p).poke(true.B);d.io.writeTag(p).poke(5.U);d.io.writeData(p).poke((0x200+p).U)}
      d.io.retire(0).poke(true.B);d.io.retireRd(0).poke(6.U);d.io.retireTag(0).poke(5.U)
      d.io.archRead(0).poke(6.U);d.io.archData(0).expect(0x204.U)
      d.clock.step();idle(d)
      d.io.archRead(0).poke(6.U);d.io.archData(0).expect(0x204.U)
      d.io.tagRead(0).poke(5.U);d.io.tagData(0).expect(0x204.U)
    }
  }
}
