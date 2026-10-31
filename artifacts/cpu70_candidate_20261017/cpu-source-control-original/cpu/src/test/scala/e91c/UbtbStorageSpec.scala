package e91c
import chisel3._
import chisel3.reflect.DataMirror
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.frontend.Ubtb
import e91c.config.Params.UBTB_SIZE
class UbtbStorageSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def clear(x:Data):Unit=x match {
    case r:Record=>r.elements.values.foreach(clear)
    case v:Vec[_]=>v.foreach(clear)
    case b:Bool if DataMirror.directionOf(b)==ActualDirection.Input=>b.poke(false.B)
    case u:UInt if DataMirror.directionOf(u)==ActualDirection.Input=>u.poke(0.U)
    case _=>()
  }
  "uBTB descriptors" should "preserve both banks through updates and replacement wrap" in {
    test(new Ubtb){d=>
      clear(d.io);d.clock.step()
      def pc(bank:Int,i:Int):BigInt={
        val raw=BigInt((i+1)*4)
        val hash=Seq(2,6,10,14,18,22).map(bit=>((raw>>bit)&1).toInt).reduce(_^_)
        if(hash==bank)raw else raw^(BigInt(1)<<22)
      }
      def put(bank:Int,i:Int,v:Int):Unit={
        val p=pc(bank,i)
        d.io.updValid.poke(true.B);d.io.updEarly.poke(true.B);d.io.updTaken.poke(true.B)
        d.io.updBank.poke((bank==1).B);d.io.updBlockPc.poke(p.U);d.io.updTag.poke(((p>>2)&0xfffff).U)
        d.io.updTarget.poke((0x2000+v*4).U);d.io.updLength.poke(((v%4)+1).U);d.io.updBrType.poke((v%4).U)
        d.clock.step();d.io.updValid.poke(false.B)
      }
      def check(bank:Int,i:Int,v:Int):Unit={
        d.io.queryValid.poke(true.B);d.io.queryPc.poke(pc(bank,i).U)
        d.io.hit.expect(true.B);d.io.target.expect((0x2000+v*4).U)
        d.io.length.expect(((v%4)+1).U);d.io.brType.expect((v%4).U)
        d.io.retHit.expect((v%4==3).B)
      }
      for(b<-0 until 2;i<-0 until UBTB_SIZE)put(b,i,20+b*16+i)
      for(b<-0 until 2;i<-0 until UBTB_SIZE)check(b,i,20+b*16+i)
      for(b<-0 until 2){put(b,1,99+b);check(b,1,99+b)}
      for(b<-0 until 2;i<-UBTB_SIZE until UBTB_SIZE+2){put(b,i,60+b*16+i);check(b,i,60+b*16+i)}
      for(b<-0 until 2;i<-2 until UBTB_SIZE)check(b,i,20+b*16+i)
    }
  }
}
