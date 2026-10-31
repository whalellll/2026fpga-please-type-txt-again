package e91c

import chisel3._
import chisel3.reflect.DataMirror
import chiseltest._
import e91c.backend.Rob
import org.scalatest.flatspec.AnyFlatSpec

class RobTagCommitBypassSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def clear(x: Data): Unit = x match {
    case r: Record => r.elements.values.foreach(clear)
    case v: Vec[_] => v.foreach(clear)
    case b: Bool if DataMirror.directionOf(b) == ActualDirection.Input => b.poke(false.B)
    case u: UInt if DataMirror.directionOf(u) == ActualDirection.Input => u.poke(0.U)
    case _ => ()
  }

  "ROB tag result retirement" should "commit a same-cycle forwarded load into the ARF" in {
    test(new Rob) { d =>
      clear(d.io); d.clock.step()
      d.io.a(0).valid.poke(true.B); d.io.a(0).rfWe.poke(true.B)
      d.io.a(0).rd.poke(7.U); d.io.a(0).isLoad.poke(true.B); d.io.allocEn.poke(true.B)
      d.clock.step(); clear(d.io)
      d.io.memFwd.valid.poke(true.B); d.io.memFwd.robid.poke(0.U); d.io.memFwd.data.poke("h13579bdf".U)
      d.io.commitRfWe(0).poke(true.B); d.io.commitRd(0).poke(7.U); d.io.commitTag(0).poke(0.U)
      d.io.archRead(0).poke(7.U); d.io.cmtResult(0).expect("h13579bdf".U); d.io.archData(0).expect("h13579bdf".U)
      d.clock.step(); clear(d.io); d.io.archRead(0).poke(7.U); d.io.archData(0).expect("h13579bdf".U)
    }
  }
}
