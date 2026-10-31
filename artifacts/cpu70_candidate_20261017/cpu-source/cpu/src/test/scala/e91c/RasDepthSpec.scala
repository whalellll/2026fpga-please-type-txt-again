package e91c

import chisel3._
import chisel3.reflect.DataMirror
import chiseltest._
import e91c.config.Params.RAS_DEPTH
import e91c.frontend.Ras
import org.scalatest.flatspec.AnyFlatSpec

class RasDepthSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def idle(data: Data): Unit = data match {
    case record: Record => record.elements.values.foreach(idle)
    case vector: Vec[_] => vector.foreach(idle)
    case value: Bool if DataMirror.directionOf(value) == ActualDirection.Input => value.poke(false.B)
    case value: UInt if DataMirror.directionOf(value) == ActualDirection.Input => value.poke(0.U)
    case _ => ()
  }

  "Configured return stack" should "retain nested returns up to its full capacity and recover the committed stack" in {
    test(new Ras) { d =>
      idle(d.io); d.clock.step(); d.io.empty.expect(true.B)
      for (level <- 0 until RAS_DEPTH) {
        d.io.specPush.poke(true.B); d.io.specPushAddr.poke((0x1000 + level * 4).U)
        d.io.cmtPush.poke(true.B); d.io.cmtPushAddr.poke((0x1000 + level * 4).U)
        d.clock.step(); idle(d.io)
        d.io.empty.expect(false.B); d.io.topAddr.expect((0x1000 + level * 4).U)
      }
      // Extra speculative nesting overwrites the oldest speculative slot.
      d.io.specPush.poke(true.B); d.io.specPushAddr.poke(0x2000.U)
      d.clock.step(); idle(d.io); d.io.topAddr.expect(0x2000.U)
      // Commit a return on the same edge as recovery, then use the updated
      // committed pointer/count and backing data throughout the remaining pops.
      d.io.flush.poke(true.B); d.io.cmtPop.poke(true.B)
      d.clock.step(); idle(d.io)
      for (level <- (0 until RAS_DEPTH - 1).reverse) {
        d.io.empty.expect(false.B); d.io.topAddr.expect((0x1000 + level * 4).U)
        d.io.specPop.poke(true.B); d.clock.step(); idle(d.io)
      }
      d.io.empty.expect(true.B)
    }
  }

  it should "restore a saved return position after a speculative pop" in {
    test(new Ras) { d =>
      idle(d.io); d.clock.step()
      for (level <- 0 until RAS_DEPTH) {
        d.io.specPush.poke(true.B); d.io.specPushAddr.poke((0x3000 + level * 4).U)
        d.clock.step(); idle(d.io)
      }
      d.io.cpSave.poke(true.B); d.io.cpId.poke(7.U)
      d.clock.step(); idle(d.io)
      d.io.cpQueryId.poke(7.U); d.io.cpNonempty.expect(true.B)
      d.io.cpTopAddr.expect((0x3000 + (RAS_DEPTH - 1) * 4).U)
      d.io.specPop.poke(true.B); d.clock.step(); idle(d.io)
      d.io.restore.poke(true.B); d.io.restoreId.poke(7.U)
      d.clock.step(); idle(d.io)
      d.io.empty.expect(false.B); d.io.topAddr.expect((0x3000 + (RAS_DEPTH - 1) * 4).U)
    }
  }
}
