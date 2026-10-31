package e91c
import chisel3._
import chisel3.reflect.DataMirror
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.exec.{Mul, RsMdu}

class RsMduWritebackSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def clear(x:Data):Unit=x match {
    case r:Record=>r.elements.values.foreach(clear)
    case v:Vec[_]=>v.foreach(clear)
    case b:Bool if DataMirror.directionOf(b)==ActualDirection.Input=>b.poke(false.B)
    case u:UInt if DataMirror.directionOf(u)==ActualDirection.Input=>u.poke(0.U)
    case _=>()
  }
  "MDU writeback" should "preserve all port priorities for queued operands" in {
    test(new RsMdu){d=>
      clear(d.io);d.clock.step()
      for(first<-0 until 5){
        d.io.mduReady.poke(false.B)
        d.io.pushRobid.poke(3.U);d.io.pushAluOpMdu.poke(1.U)
        d.io.pushSrc0Ready.poke(false.B);d.io.pushSrc1Ready.poke(false.B)
        d.io.pushSrc0Robid.poke(7.U);d.io.pushSrc1Robid.poke(7.U)
        for(i<-0 until 5){
          d.io.wbRobid(i).poke(7.U);d.io.wbData(i).poke((0x1000+i*4).U)
          d.io.wbValid(i).poke(false.B)
        }
        d.io.canAccept.expect(true.B);d.io.pushValid.poke(true.B);d.clock.step();d.io.pushValid.poke(false.B)
        for(i<-0 until 5)d.io.wbValid(i).poke((i>=first).B)
        d.clock.step()
        d.io.wbValid.foreach(_.poke(false.B));d.clock.step()
        d.io.mduReady.poke(true.B);d.io.issueValid.expect(true.B)
        d.io.issueSrc0.expect((0x1000+first*4).U);d.io.issueSrc1.expect((0x1000+first*4).U)
        
        d.clock.step();d.io.mduReady.poke(false.B);d.io.occupancy.expect(0.U)
      }
    }
  }

  "Multiplier decomposition" should "preserve unsigned, signed and mixed full products" in {
    test(new Mul) { d =>
      d.io.valid.poke(false.B)
      d.io.a.poke(0.U)
      d.io.b.poke(0.U)
      d.io.signedA.poke(false.B)
      d.io.signedB.poke(false.B)
      d.clock.step()
      d.io.done.expect(false.B)

      val cases = Seq(
        (BigInt("ffffffff", 16), BigInt("ffffffff", 16), false, false, BigInt("fffffffe00000001", 16)),
        (BigInt("00010000", 16), BigInt("00010000", 16), false, false, BigInt("0000000100000000", 16)),
        (BigInt("ffffffff", 16), BigInt(2), false, false, BigInt("00000001fffffffe", 16)),
        (BigInt("ffffffff", 16), BigInt(2), true, true, BigInt("fffffffffffffffe", 16)),
        (BigInt("fffffffe", 16), BigInt("fffffffd", 16), true, true, BigInt(6)),
        (BigInt("fffffffe", 16), BigInt("ffffffff", 16), true, false, BigInt("fffffffe00000002", 16)),
        (BigInt("ffffffff", 16), BigInt("fffffffe", 16), false, true, BigInt("fffffffe00000002", 16))
      )
      for ((a, b, signedA, signedB, expected) <- cases) {
        d.io.a.poke(a.U)
        d.io.b.poke(b.U)
        d.io.signedA.poke(signedA.B)
        d.io.signedB.poke(signedB.B)
        d.io.valid.poke(true.B)
        d.clock.step()
        d.io.done.expect(true.B)
        d.io.result.expect(expected.U)
      }
      d.io.valid.poke(false.B)
      d.clock.step()
      d.io.done.expect(false.B)
    }
  }
}

