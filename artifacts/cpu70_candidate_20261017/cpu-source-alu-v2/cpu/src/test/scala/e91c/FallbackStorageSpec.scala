package e91c
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.frontend.{FallbackBtb,FallbackBtbReference}
class FallbackStorageHarness extends Module {
  val d=Module(new FallbackBtb)
  val r=Module(new FallbackBtbReference)
  val io=IO(chiselTypeOf(d.io))
  io <> d.io
  r.io.queryValid:=io.queryValid; r.io.queryPc:=io.queryPc
  r.io.updValid:=io.updValid; r.io.updBlockPc:=io.updBlockPc
  r.io.updTaken:=io.updTaken; r.io.updTarget:=io.updTarget
  r.io.updLength:=io.updLength; r.io.updBrType:=io.updBrType; r.io.updEarly:=io.updEarly
  assert(d.io.hit===r.io.hit)
  when(d.io.hit) {
    assert(d.io.taken===r.io.taken && d.io.target===r.io.target && d.io.length===r.io.length)
    assert(d.io.brType===r.io.brType && d.io.strongTaken===r.io.strongTaken && d.io.staticDirect===r.io.staticDirect)
  }
}
class FallbackStorageSpec extends AnyFlatSpec with ChiselScalatestTester {
  "Fallback storage" should "match frozen register implementation through collisions, training and same-address updates" in {
    test(new FallbackStorageHarness) { d =>
      val rng=new scala.util.Random(91054)
      for(cycle<-0 until 400) {
        val pc=0x1000+(rng.nextInt(3)*32+rng.nextInt(8))*4
        val qp=if(cycle%3==0) pc else 0x1000+(rng.nextInt(3)*32+rng.nextInt(8))*4
        d.io.queryValid.poke((cycle%11!=0).B); d.io.queryPc.poke(qp.U)
        d.io.updValid.poke((cycle%5!=0).B); d.io.updBlockPc.poke(pc.U)
        d.io.updTaken.poke(rng.nextBoolean().B); d.io.updTarget.poke((0x2000+cycle*4).U)
        d.io.updLength.poke((if(cycle%17==0) 0 else 1+rng.nextInt(4)).U)
        d.io.updBrType.poke(rng.nextInt(4).U); d.io.updEarly.poke((cycle%3==1).B)
        d.clock.step()
      }
    }
  }
}
