package e91c
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.frontend.InstBuffer
import e91c.config.Params.IB_SIZE
import scala.collection.mutable.Queue
class InstBufferCapacitySpec extends AnyFlatSpec with ChiselScalatestTester {
  "Instruction buffer" should "preserve order across every bank row, wrap, stalls and flush" in {
    test(new InstBuffer) { d =>
      val q=Queue.empty[Int]
      var serial=1
      d.io.flush.poke(false.B)
      for(i <- 0 until 4) {
        d.io.pushValid(i).poke(false.B); d.io.pushPc(i).poke(0.U); d.io.pushInst(i).poke(0.U)
        d.io.pushPredTaken(i).poke(false.B); d.io.pushIsLast(i).poke(false.B)
        d.io.pushFtqId(i).poke(0.U); d.io.pushExcp(i).poke(0.U)
      }
      d.io.popReady.foreach(_.poke(false.B)); d.clock.step()
      var maxOccupancy=0
      for(cycle <- 0 until 180) {
        val flush=cycle==95
        d.io.flush.poke(flush.B)
        val pop=if(cycle%45<12) 0 else if(cycle%3==0) 1 else 2
        for(i <- 0 until 2) {
          d.io.popReady(i).poke((i<pop).B)
          d.io.popValid(i).expect((q.size>i).B)
          if(q.size>i) {d.io.popInst(i).expect(q(i).U); d.io.popPc(i).expect((q(i)*4).U)}
        }
        val take=math.min(q.size,pop)
        d.io.canPush.expect((q.size <= IB_SIZE-4).B)
        val wanted=if(cycle%45<12) 4 else cycle%5
        val n=if(d.io.canPush.peek().litToBoolean && cycle%45<32) wanted else 0
        val values=(0 until n).map(i=>serial+i)
        for(i <- 0 until 4) {
          d.io.pushValid(i).poke((i<n).B); d.io.pushInst(i).poke((serial+i).U); d.io.pushPc(i).poke(((serial+i)*4).U)
        }
        d.clock.step()
        if(flush) q.clear() else {for(i<-0 until take) q.dequeue(); values.foreach(v => q.enqueue(v))}
        serial+=n
        maxOccupancy=math.max(maxOccupancy,q.size)
      }
      assert(maxOccupancy>=IB_SIZE-3)
    }
  }
}
