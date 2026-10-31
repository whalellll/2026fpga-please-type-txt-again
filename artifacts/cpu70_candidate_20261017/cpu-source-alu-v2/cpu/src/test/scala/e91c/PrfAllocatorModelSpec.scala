package e91c
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.reg.PhysicalRegisterFile
import scala.collection.mutable.ArrayBuffer

class PrfAllocatorModelSpec extends AnyFlatSpec with ChiselScalatestTester {
  "PRF allocation" should "match lowest-free sequential allocation with port holes, WAW, retirement reuse and flush" in {
    test(new PhysicalRegisterFile) { d =>
      val random=new scala.util.Random(91006)
      val committed=Array.tabulate(32)(identity)
      val speculative=committed.clone()
      var free=(32 until d.entries).toSet
      val live=ArrayBuffer.empty[(Int,Int,Int)] // ROB tag, architectural RD, physical RD
      for(i <- 0 until 5) {
        d.io.write(i).poke(false.B); d.io.writeTag(i).poke(0.U); d.io.writeData(i).poke(0.U)
        if (i < 4) d.io.archRead(i).poke(0.U)
      }
      for(i <- 0 until d.tagReads) d.io.tagRead(i).poke(0.U)
      for(cycle <- 0 until 400) {
        d.io.freeCount.expect(free.size.U)
        for(i <- 0 until 32) {
          d.io.committedMap(i).expect(committed(i).U)
          d.io.speculativeMap(i).expect(speculative(i).U)
        }
        val retireCount=if(cycle%13<7) 0 else random.nextInt(math.min(2,live.size)+1)
        var available=free
        for(i <- 0 until 2) {
          d.io.retire(i).poke((i<retireCount).B)
          val entry=if(i<retireCount) live(i) else (0,0,0)
          d.io.retireTag(i).poke(entry._1.U); d.io.retireRd(i).poke(entry._2.U)
          if(i<retireCount) { available+=committed(entry._2); committed(entry._2)=entry._3 }
        }
        live.remove(0,retireCount)
        d.io.canAllocate.expect((available.size>=2).B)
        val flush=cycle%29==28
        d.io.flush.poke(flush.B)
        val tags=random.shuffle((0 until 32).filter(t => !live.exists(_._1==t))).iterator
        val newborn=ArrayBuffer.empty[(Int,Int,Int)]
        val allow=available.size>=2
        for(i <- 0 until 2) {
          val valid=allow && tags.hasNext && random.nextInt(4)!=0
          val tag=if(valid) tags.next() else 0
          val rd=random.nextInt(8) // Frequent WAW and rd=x0.
          d.io.allocate(i).poke(valid.B); d.io.allocateTag(i).poke(tag.U); d.io.allocateRd(i).poke(rd.U)
          val physical=if(valid && rd!=0) available.min else 0
          d.io.allocatedPhysical(i).expect(physical.U,s"cycle=$cycle port=$i")
          if(valid && rd!=0) { available-=physical; newborn+=((tag,rd,physical)) }
        }
        if(flush) {
          live.clear(); free=(0 until d.entries).toSet--committed.toSet
          Array.copy(committed,0,speculative,0,32)
        } else {
          newborn.foreach { case(_,rd,physical) => speculative(rd)=physical }
          live++=newborn; free=available
        }
        d.clock.step()
      }
    }
  }
}
