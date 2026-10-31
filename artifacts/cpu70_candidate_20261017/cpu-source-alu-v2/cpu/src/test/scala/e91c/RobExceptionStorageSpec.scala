package e91c
import chisel3._
import chisel3.reflect.DataMirror
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.backend.Rob
import e91c.config.Params.EXCP_NUM
class RobExceptionStorageSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def clear(x:Data):Unit=x match {
    case r:Record=>r.elements.values.foreach(clear)
    case v:Vec[_]=>v.foreach(clear)
    case b:Bool if DataMirror.directionOf(b)==ActualDirection.Input=>b.poke(false.B)
    case u:UInt if DataMirror.directionOf(u)==ActualDirection.Input=>u.poke(0.U)
    case _=>()
  }
  "ROB static exception storage" should "retain every bit across pairs, split allocation, wrap and reset" in {
    test(new Rob){d=>
      clear(d.io);d.clock.step()
      for(n<-0 until 40){
        val e0=BigInt(1)<<(n%EXCP_NUM)
        val e1=BigInt(1)<<((n+1)%EXCP_NUM)
        d.io.a(0).valid.poke(true.B);d.io.a(0).excp.poke(e0.U)
        d.io.a(1).excp.poke(e1.U);d.io.a(1).valid.poke((n%2==0).B)
        d.io.robFull.expect(false.B);d.io.allocEn.poke(true.B);d.clock.step()
        if(n%2==1){d.io.a(0).excp.poke(e1.U);d.clock.step()}
        d.io.allocEn.poke(false.B);d.io.a.foreach(_.valid.poke(false.B))
        d.io.cmtValid.foreach(_.expect(true.B))
        d.io.cmtExcp(0).expect(e0.U);d.io.cmtExcp(1).expect(e1.U)
        d.io.cmtClear0.poke(true.B);d.io.cmtClear1.poke(true.B);d.io.cmtPop.poke(true.B)
        d.clock.step();d.io.cmtClear0.poke(false.B);d.io.cmtClear1.poke(false.B);d.io.cmtPop.poke(false.B)
      }
      d.io.flush.poke(true.B);d.clock.step();d.io.flush.poke(false.B)
      d.io.cmtValid.foreach(_.expect(false.B))
      d.reset.poke(true.B);d.clock.step();d.reset.poke(false.B);d.clock.step()
      d.io.cmtExcp.foreach(_.expect(0.U))
    }
  }
}
