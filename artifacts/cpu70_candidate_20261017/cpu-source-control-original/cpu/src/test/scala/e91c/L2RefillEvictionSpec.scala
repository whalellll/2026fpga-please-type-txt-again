package e91c
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.mem.L2Cache
import e91c.config.Params.L2_NWAY
class L2RefillEvictionSpec extends AnyFlatSpec with ChiselScalatestTester {
  "L2 cache" should "refill each way and write back a dirty conflict before replacement" in {
    test(new L2Cache) { d =>
      Seq(d.io.icRdReq,d.io.dcRdReq,d.io.dcWrReq,d.io.dcWrWriteThrough,
        d.io.memRetError,d.io.memRetValid,d.io.memRetLast,
        d.io.mem2RetError,d.io.mem2RetValid,d.io.mem2RetLast).foreach(_.poke(false.B))
      Seq(d.io.icRdType,d.io.icRdAddr,d.io.dcRdType,d.io.dcRdAddr,
        d.io.dcWrType,d.io.dcWrAddr,d.io.dcWrStrb,d.io.dcWrData,
        d.io.memRetData,d.io.mem2RetData).foreach(_.poke(0.U))
      d.io.memRdRdy.poke(true.B); d.io.mem2RdRdy.poke(true.B); d.io.memWrRdy.poke(true.B)
      d.clock.step(520)
      def waitFor(flag: Bool): Unit = {
        var n=0
        while(!flag.peek().litToBoolean && n<24) { d.clock.step(); n+=1 }
        assert(n<24,"L2 transaction timeout")
      }
      def address(i:Int):BigInt=BigInt("80000000",16)+i*16384
      def low(v:Int):BigInt=(BigInt(v)<<96)+v
      def high(v:Int):BigInt=(BigInt(v+7)<<112)+v+11
      def refill(i:Int,dirtyEviction:Boolean):Unit={
        d.io.dcRdType.poke(4.U);d.io.dcRdAddr.poke(address(i).U);d.io.dcRdReq.poke(true.B)
        waitFor(d.io.dcRdRdy);d.clock.step();d.io.dcRdReq.poke(false.B)
        if(dirtyEviction){
          waitFor(d.io.memWrReq);d.io.memWrAddr.expect(address(0).U)
          d.io.memWrData.expect(low(90).U);d.clock.step()
          d.io.memWrReq.expect(true.B);d.io.memWrData.expect(high(90).U);d.clock.step()
        }
        waitFor(d.io.memRdReq);d.io.memRdAddr.expect(address(i).U);d.clock.step()
        d.io.memRetValid.poke(true.B);d.io.memRetLast.poke(false.B);d.io.memRetData.poke(low(20+i).U)
        d.io.dcRetValid.expect(true.B);d.io.dcRetData.expect(low(20+i).U);d.clock.step()
        d.io.memRetLast.poke(true.B);d.io.memRetData.poke(high(20+i).U)
        d.io.dcRetValid.expect(true.B);d.io.dcRetLast.expect(true.B);d.io.dcRetData.expect(high(20+i).U)
        d.clock.step();d.io.memRetValid.poke(false.B);d.io.memRetLast.poke(false.B)
      }
      def dirty(i:Int):Unit={
        d.io.dcWrType.poke(4.U);d.io.dcWrAddr.poke(address(i).U);d.io.dcWrStrb.poke(15.U)
        d.io.dcWrData.poke(low(90+i).U);d.io.dcWrReq.poke(true.B)
        waitFor(d.io.dcWrRdy);d.clock.step();d.io.dcWrReq.poke(false.B)
        d.io.dcWrData.poke(high(90+i).U);d.clock.step()
        for(k<-0 until 4){d.io.memWrReq.expect(false.B);d.clock.step()}
      }
      for(i<-0 until L2_NWAY){refill(i,false);dirty(i)}
      refill(L2_NWAY,true)
    }
  }
}
