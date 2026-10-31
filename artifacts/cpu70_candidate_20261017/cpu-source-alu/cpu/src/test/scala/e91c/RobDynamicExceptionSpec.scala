package e91c
import chisel3._
import chisel3.reflect.DataMirror
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.backend.Rob
import e91c.config.Params.{EXCP_NUM,ROB_SIZE}
class RobDynamicExceptionSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def clear(x:Data):Unit=x match {
    case r:Record=>r.elements.values.foreach(clear)
    case v:Vec[_]=>v.foreach(clear)
    case b:Bool if DataMirror.directionOf(b)==ActualDirection.Input=>b.poke(false.B)
    case u:UInt if DataMirror.directionOf(u)==ActualDirection.Input=>u.poke(0.U)
    case _=>()
  }
  "ROB dynamic exception storage" should "preserve all fault bits, allocation clearing, mem2 clearing and flush priority" in {
    test(new Rob){d=>
      clear(d.io);d.clock.step()
      for(n<-0 until 40){
        val pair=n%(ROB_SIZE/2)
        val e0=BigInt(1)<<(n%EXCP_NUM);val e1=BigInt(1)<<((n+1)%EXCP_NUM)
        d.io.a.foreach{a=>a.valid.poke(true.B);a.isLoad.poke(true.B)}
        d.io.allocEn.poke(true.B);d.clock.step();d.io.allocEn.poke(false.B);d.io.a.foreach(_.valid.poke(false.B))
        d.io.cmtExcp.foreach(_.expect(0.U))
        d.io.memFwd.valid.poke(true.B);d.io.memFwd.robid.poke(pair.U);d.io.memFwd.excp.poke(e0.U);d.clock.step()
        d.io.memFwd.robid.poke((pair+ROB_SIZE/2).U);d.io.memFwd.excp.poke(e1.U);d.clock.step();d.io.memFwd.valid.poke(false.B)
        d.io.cmtExcp(0).expect(e0.U);d.io.cmtExcp(1).expect(e1.U)
        if(n%3==0){d.io.mem2Wb.valid.poke(true.B);d.io.mem2Wb.robid.poke(pair.U);d.clock.step();d.io.mem2Wb.valid.poke(false.B);d.io.cmtExcp(0).expect(0.U)}
        d.io.cmtClear0.poke(true.B);d.io.cmtClear1.poke(true.B);d.io.cmtPop.poke(true.B);d.clock.step()
        d.io.cmtClear0.poke(false.B);d.io.cmtClear1.poke(false.B);d.io.cmtPop.poke(false.B)
      }
      d.io.memFwd.valid.poke(true.B);d.io.memFwd.robid.poke(0.U);d.io.memFwd.excp.poke(1.U)
      d.io.flush.poke(true.B);d.clock.step();d.io.flush.poke(false.B);d.io.memFwd.valid.poke(false.B)
      d.io.cmtExcp.foreach(_.expect(0.U))
      d.reset.poke(true.B);d.clock.step();d.reset.poke(false.B);d.clock.step();d.io.cmtExcp.foreach(_.expect(0.U))
    }
  }
}
