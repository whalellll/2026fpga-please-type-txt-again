package e91c

import chisel3._
import chisel3.reflect.DataMirror
import chiseltest._
import e91c.backend.Rob
import org.scalatest.flatspec.AnyFlatSpec

class RobBaseProbeSharingSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def clear(x: Data): Unit = x match {
    case r: Record => r.elements.values.foreach(clear)
    case v: Vec[_] => v.foreach(clear)
    case b: Bool if DataMirror.directionOf(b) == ActualDirection.Input => b.poke(false.B)
    case u: UInt if DataMirror.directionOf(u) == ActualDirection.Input => u.poke(0.U)
    case _ => ()
  }

  private def allocatePair(d: Rob): Unit = {
    d.io.a.foreach { a =>
      a.valid.poke(true.B)
      a.rfWe.poke(true.B)
    }
    d.io.a(0).rd.poke(1.U)
    d.io.a(1).rd.poke(2.U)
    d.io.allocEn.poke(true.B)
    d.clock.step()
    d.io.allocEn.poke(false.B)
    d.io.a.foreach(_.valid.poke(false.B))
  }

  "Shared ROB LSU base-result read" should "serve distinct stored tags in bounded round-robin order" in {
    test(new Rob) { d =>
      clear(d.io)
      d.clock.step()
      allocatePair(d)

      d.io.alu(0).valid.poke(true.B)
      d.io.alu(0).robid.poke(0.U)
      d.io.alu(0).data.poke("h11112222".U)
      d.io.alu(1).valid.poke(true.B)
      d.io.alu(1).robid.poke(16.U)
      d.io.alu(1).data.poke("h33334444".U)
      d.clock.step()
      d.io.alu.foreach(_.valid.poke(false.B))

      d.io.baseProbeRobid(0).poke(0.U)
      d.io.baseProbeRobid(1).poke(16.U)
      d.io.baseProbeReady(0).expect(true.B)
      d.io.baseProbeReady(1).expect(false.B)
      d.io.baseProbeData(0).expect("h11112222".U)
      d.clock.step()
      d.io.baseProbeReady(0).expect(false.B)
      d.io.baseProbeReady(1).expect(true.B)
      d.io.baseProbeData(1).expect("h33334444".U)
    }
  }

  it should "share identical tags and retain independent same-cycle memory forwarding" in {
    test(new Rob) { d =>
      clear(d.io)
      d.clock.step()
      allocatePair(d)

      d.io.alu(0).valid.poke(true.B)
      d.io.alu(0).robid.poke(0.U)
      d.io.alu(0).data.poke("ha5a55a5a".U)
      d.clock.step()
      d.io.alu(0).valid.poke(false.B)
      d.io.baseProbeRobid.foreach(_.poke(0.U))
      d.io.baseProbeReady.foreach(_.expect(true.B))
      d.io.baseProbeData.foreach(_.expect("ha5a55a5a".U))

      d.io.baseProbeRobid(0).poke(5.U)
      d.io.baseProbeRobid(1).poke(21.U)
      d.io.memFwd.valid.poke(true.B)
      d.io.memFwd.robid.poke(5.U)
      d.io.memFwd.data.poke("h01234567".U)
      d.io.mem2Wb.valid.poke(true.B)
      d.io.mem2Wb.robid.poke(21.U)
      d.io.mem2Wb.data.poke("h89abcdef".U)
      d.io.baseProbeReady.foreach(_.expect(true.B))
      d.io.baseProbeData(0).expect("h01234567".U)
      d.io.baseProbeData(1).expect("h89abcdef".U)
    }
  }
}
