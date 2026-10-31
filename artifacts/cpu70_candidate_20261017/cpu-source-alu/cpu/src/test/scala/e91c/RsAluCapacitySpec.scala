package e91c
import chisel3._
import chisel3.reflect.DataMirror
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.backend.RsAlu
class RsAluCapacitySpec extends AnyFlatSpec with ChiselScalatestTester {
  private def clear(x:Data):Unit=x match {
    case r:Record=>r.elements.values.foreach(clear)
    case v:Vec[_]=>v.foreach(clear)
    case b:Bool if DataMirror.directionOf(b)==ActualDirection.Input=>b.poke(false.B)
    case u:UInt if DataMirror.directionOf(u)==ActualDirection.Input=>u.poke(0.U)
    case _=>()
  }
  "Configured ALU reservation station" should "report exact full occupancy and recover from flush" in {
    test(new RsAlu){d=>
      clear(d.io);d.clock.step()
      for(round<-0 until 2){
        for(i<-0 until d.RS_DEPTH){
          d.io.canAccept.expect(true.B);d.io.pushValid.poke(true.B)
          d.io.pushRobid.poke((i+1).U);d.io.pushAluOp.poke(1.U)
          d.io.pushSrc0Robid.poke(20.U);d.io.pushSrc1Robid.poke(21.U)
          d.clock.step()
        }
        d.io.pushValid.poke(false.B);d.io.occupancy.expect(d.RS_DEPTH.U)
        d.io.canAccept.expect(false.B);d.io.issueValid.expect(false.B)
        d.io.flush.poke(true.B);d.clock.step();d.io.flush.poke(false.B)
        d.io.occupancy.expect(0.U);d.io.canAccept.expect(true.B)
      }
    }
  }
}
