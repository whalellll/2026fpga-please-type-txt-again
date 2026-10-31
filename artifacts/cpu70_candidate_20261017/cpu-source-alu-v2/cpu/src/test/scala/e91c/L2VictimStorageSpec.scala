package e91c
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.mem.L2Cache
class L2VictimStorageSpec extends AnyFlatSpec with ChiselScalatestTester {
  "L2 victim storage" should "preserve lines through hit updates and replacement wrap" in {
    test(new L2Cache) { d =>
      Seq(d.io.icRdReq,d.io.dcRdReq,d.io.dcWrReq,d.io.dcWrWriteThrough,
        d.io.memRetError,d.io.memRetValid,d.io.memRetLast,
        d.io.mem2RetError,d.io.mem2RetValid,d.io.mem2RetLast).foreach(_.poke(false.B))
      Seq(d.io.icRdType,d.io.icRdAddr,d.io.dcRdType,d.io.dcRdAddr,
        d.io.dcWrType,d.io.dcWrAddr,d.io.dcWrStrb,d.io.dcWrData,
        d.io.memRetData,d.io.mem2RetData).foreach(_.poke(0.U))
      d.io.memRdRdy.poke(true.B); d.io.mem2RdRdy.poke(true.B); d.io.memWrRdy.poke(true.B)
      d.clock.step(520)
      def awaitFlag(flag: Bool): Unit = {
        var n=0
        while(!flag.peek().litToBoolean && n<24) { d.clock.step(); n+=1 }
        assert(n<24,"L2 handshake timed out")
      }
      def address(i:Int):BigInt=BigInt("80000000",16)+i*32
      def low(v:Int):BigInt=(BigInt(v)<<96)+v
      def high(v:Int):BigInt=(BigInt(v+7)<<112)+v+11
      def write(i:Int,v:Int):Unit={
        d.io.dcWrType.poke(4.U);d.io.dcWrAddr.poke(address(i).U)
        d.io.dcWrStrb.poke(15.U);d.io.dcWrData.poke(low(v).U);d.io.dcWrReq.poke(true.B)
        awaitFlag(d.io.dcWrRdy);d.clock.step();d.io.dcWrReq.poke(false.B)
        d.io.dcWrData.poke(high(v).U);d.clock.step();d.clock.step(5)
      }
      def read(i:Int,v:Int):Unit={
        d.io.dcRdType.poke(4.U);d.io.dcRdAddr.poke(address(i).U);d.io.dcRdReq.poke(true.B)
        awaitFlag(d.io.dcRdRdy);d.clock.step();d.io.dcRdReq.poke(false.B)
        awaitFlag(d.io.dcRetValid)
        d.io.memRdReq.expect(false.B);d.io.dcRetData.expect(low(v).U);d.io.dcRetLast.expect(false.B)
        d.clock.step();d.io.dcRetValid.expect(true.B);d.io.dcRetData.expect(high(v).U)
        d.io.dcRetLast.expect(true.B);d.io.dcRetError.expect(false.B);d.clock.step()
      }
      for(i<-0 until 4) write(i,20+i)
      for(i<-0 until 4) read(i,20+i)
      write(1,91);read(1,91)
      write(4,24);write(5,25)
      for(i<-2 until 6) read(i,20+i)
    }
  }
}
