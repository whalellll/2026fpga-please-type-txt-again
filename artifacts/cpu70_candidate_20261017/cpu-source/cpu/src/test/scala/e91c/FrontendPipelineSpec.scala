
package e91c
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.core.CoreFrontend
import scala.collection.mutable.ArrayBuffer

class FrontendPipelineSpec extends AnyFlatSpec with ChiselScalatestTester {
  private val base=BigInt("1c000000",16)
  private def init(d: CoreFrontend, resetPc: BigInt = base): Unit = {
    d.io.instructionFaults.poke(0.U)
    d.io.instructionReadError.poke(false.B)
    d.io.cmt_ftq_br_type.poke(0.U)
    d.io.cmt_ftq_id.poke(0.U)
    d.io.cmt_ftq_is_branch.poke(0.U)
    d.io.cmt_ftq_mispred.poke(0.U)
    d.io.cmt_ftq_pc.poke(0.U)
    d.io.cmt_ftq_query_id.poke(0.U)
    d.io.cmt_ftq_release.poke(0.U)
    d.io.cmt_ftq_taken.poke(0.U)
    d.io.cmt_ftq_target.poke(0.U)
    d.io.cmt_ftq_valid.poke(0.U)
    d.io.cmt_ras_call.poke(0.U)
    d.io.cmt_ras_ret.poke(0.U)
    d.io.cmt_ras_retaddr.poke(0.U)
    d.io.early_redirect_valid.poke(0.U)
    d.io.early_redirect_pc.poke(0.U)
    d.io.early_redirect_ftq_id.poke(0.U)
    d.io.early_redirect_taken.poke(0.U)
    d.io.flush.poke(0.U)
    d.io.flush_pc.poke(0.U)
    d.io.ib_pop0_ready.poke(0.U)
    d.io.ib_pop1_ready.poke(0.U)
    d.io.ic_ifu_addr_ok.poke(0.U)
    d.io.ic_ifu_data_ok.poke(0.U)
    d.io.ic_invalidate.poke(0.U)
    d.io.l2_ic_rd_rdy.poke(0.U)
    d.io.l2_ic_ret_data.poke(0.U)
    d.io.l2_ic_ret_last.poke(0.U)
    d.io.l2_ic_ret_valid.poke(0.U)
    d.io.pma_i_direct_excp.poke(0.U)
    d.io.pma_i_direct_mat.poke(0.U)
    d.io.pma_i_direct_ok.poke(0.U)
    d.io.pma_i_direct_paddr.poke(0.U)
    d.io.pma_i_inst_addr_misaligned.poke(0.U)
    d.io.pma_i_mat.poke(0.U)
    d.io.pma_i_paddr.poke(0.U)
    d.io.pma_i_ready.poke(0.U)
    d.io.resetn.poke(0.U)
    d.io.resetVector.poke(resetPc.U)
    d.io.rv_fencei_hold.poke(0.U)
    d.io.rv_fencei_issue.poke(0.U)
    d.io.resetn.poke(1.U)
    d.reset.poke(true.B)
    d.clock.step()
    d.reset.poke(false.B)
    // Wait for the documented synchronous I-cache metadata reset sweep.
    d.clock.step(130)
  }
  private def jump(rd: Int, from: BigInt, to: BigInt): BigInt = {
    val off=(to-from).toInt
    BigInt((((off>>20)&1)<<31) | (((off>>1)&1023)<<21) |
      (((off>>11)&1)<<20) | (((off>>12)&255)<<12) | (rd<<7) | 0x6f) & BigInt("ffffffff",16)
  }
  private class Driver(d: CoreFrontend, word: BigInt=>BigInt, delay: Int=3) {
    var time=0; var alias=BigInt(0); var translations=0
    var pending: Option[(BigInt,Int,Int)] = None
    val observed=ArrayBuffer.empty[(BigInt,BigInt)]
    def tick(pop: Boolean=true, flush: Boolean=false, wide: Boolean=false): Unit = {
      d.io.flush.poke((if(flush) 1 else 0).U); d.io.flush_pc.poke(base.U)
      d.io.ib_pop0_ready.poke((if(pop) 1 else 0).U)
      d.io.ib_pop1_ready.poke((if(pop && wide) 1 else 0).U)
      d.io.cmt_ftq_release.poke(0.U)
      d.io.l2_ic_rd_rdy.poke((if(pending.isEmpty) 1 else 0).U)
      d.io.l2_ic_ret_valid.poke(0.U); d.io.l2_ic_ret_last.poke(0.U)
      val delivering=pending.filter(_._2<=time)
      delivering.foreach { case(address,_,beat) =>
        val data=(0 until 4).map(i => word(address+(beat*16+i*4))<<(i*32)).reduce(_|_)
        d.io.l2_ic_ret_valid.poke(1.U); d.io.l2_ic_ret_last.poke(beat.U)
        d.io.l2_ic_ret_data.poke(data.U)
      }
      d.io.pma_i_paddr.poke((d.io.ifu_pma_vaddr.peek().litValue+alias).U)
      d.io.pma_i_mat.poke(1.U)
      d.io.pma_i_ready.poke(d.io.ifu_pma_req.peek())
      d.io.ic_ifu_addr_ok.poke(d.io.ic_ifu_addr_ok_raw.peek())
      d.io.ic_ifu_data_ok.poke(d.io.ic_ifu_data_ok_raw.peek())
      if(pop && !flush && d.io.ib_pop0_valid.peek().litValue==1) {
        observed += ((d.io.ib_pop0_pc.peek().litValue,d.io.ib_pop0_inst.peek().litValue))
        if(d.io.ib_pop0_is_last.peek().litValue==1) d.io.cmt_ftq_release.poke(1.U)
      }
      if (pop && wide && !flush) {
        var released=d.io.cmt_ftq_release.peek().litValue
        for ((v,p,i,last) <- Seq(
          (d.io.ib_pop1_valid,d.io.ib_pop1_pc,d.io.ib_pop1_inst,d.io.ib_pop1_is_last))) {
          if(v.peek().litValue==1) {
            observed += ((p.peek().litValue,i.peek().litValue))
            if(last.peek().litValue==1) released+=1
          }
        }
        d.io.cmt_ftq_release.poke(released.U)
      }
      if(d.io.instructionAccept.peek().litToBoolean) translations+=1
      val accepted=pending.isEmpty && d.io.ic_l2_rd_req.peek().litValue==1
      val acceptedAddress=d.io.ic_l2_rd_addr.peek().litValue
      d.clock.step(); time+=1
      delivering.foreach { case(address,_,beat) =>
        pending=if(beat==0) Some((address,time+1,1)) else None
      }
      if(accepted) pending=Some((acceptedAddress,time+delay,0))
    }
  }
  behavior of "PF FC PD frontend"
  it should "start fetch at the selected reset vector" in {
    test(new CoreFrontend) { d =>
      val resetPc = BigInt("80000000", 16)
      init(d, resetPc)
      d.io.ifu_pma_vaddr.expect(resetPc.U)
    }
  }
  it should "register walker cancellation while restarting from an execution-stage redirect" in {
    test(new CoreFrontend) { d =>
      init(d)
      val target = base + 0x180
      d.io.early_redirect_valid.poke(1.U)
      d.io.early_redirect_pc.poke(target.U)
      d.io.early_redirect_ftq_id.poke(3.U)
      d.io.early_redirect_taken.poke(1.U)
      // The redirect immediately blocks the old PF request and updates its PC;
      // the non-cancelable translation owner is cancelled on the next cycle.
      d.io.instructionCancel.expect(false.B)
      d.io.ifu_pma_req.expect(0.U)
      d.clock.step()
      d.io.early_redirect_valid.poke(0.U)
      d.io.instructionCancel.expect(true.B)
      d.io.ifu_pma_req.expect(1.U)
      d.io.ifu_pma_vaddr.expect(target.U)
      d.clock.step()
      d.io.instructionCancel.expect(false.B)
      d.io.ifu_pma_vaddr.expect(target.U)
    }
  }
  it should "hold the PF address through translation stalls and deliver the original fault PC" in {
    test(new CoreFrontend) { d =>
      init(d)
      for(_ <- 0 until 8) {
        d.io.ifu_pma_req.expect(1.U); d.io.ifu_pma_vaddr.expect(base.U)
        d.io.instructionAccept.expect(false.B); d.io.ic_l2_rd_req.expect(0.U)
        d.clock.step()
      }
      d.io.pma_i_ready.poke(1.U); d.io.instructionFaults.poke(128.U)
      d.io.instructionAccept.expect(true.B)
      d.clock.step(); d.io.pma_i_ready.poke(0.U)
      var cycles=0
      while(d.io.ib_pop0_valid.peek().litValue==0 && cycles<12) { d.clock.step(); cycles+=1 }
      d.io.ib_pop0_valid.expect(1.U); d.io.ib_pop0_pc.expect(base.U)
      d.io.ib_pop0_inst.expect(0.U)
      d.io.ib_pop0_excp.expect(128.U); d.io.ic_l2_rd_req.expect(0.U)
    }
  }
  it should "overlap warm hit groups while preserving every instruction in order" in {
    test(new CoreFrontend) { d =>
      init(d)
      val driver=new Driver(d,a=>if(a==base+12) jump(0,a,base) else BigInt(0x13))
      for(_ <- 0 until 100) driver.tick(wide=true)
      val before=driver.translations
      val instructions=driver.observed.size
      for(_ <- 0 until 200) driver.tick(wide=true)
      println(s"FRONTEND_WARM groups=${driver.translations-before} instructions=${driver.observed.size-instructions} cycles=200")
      assert(driver.observed.zipWithIndex.forall { case((pc,inst),i) =>
        pc==base+(i%4)*4 && inst==(if(i%4==3) jump(0,base+12,base) else BigInt(0x13))
      })
      assert(driver.translations-before>=80,
        s"warm frontend accepted only ${driver.translations-before} groups in 200 cycles")
      assert(driver.observed.size-instructions>=320,
        s"warm frontend supplied only ${driver.observed.size-instructions} instructions in 200 cycles")
    }
  }
  it should "preserve nested call return order under instruction buffer backpressure and deliver zero instructions" in {
    test(new CoreFrontend) { d =>
      init(d)
      val program=(0 until 16).map(i => (base+i*4)->BigInt(0x13)).toMap ++ Map(
        (base+0x40)->jump(1,base+0x40,base+0x100),
        (base+0x100)->jump(5,base+0x100,base+0x200),
        (base+0x200)->BigInt(0x13),(base+0x204)->BigInt(0x28067),
        (base+0x104)->BigInt(0x13),(base+0x108)->BigInt(0x8067),
        (base+0x44)->jump(0,base+0x44,base+0x300),
        (base+0x300)->BigInt(0x13),(base+0x304)->BigInt(0))
      val expected=(0 until 16).map(i => base+i*4) ++ Seq(0x40,0x100,0x200,0x204,0x104,0x108,0x44,0x300,0x304).map(base+_)
      val driver=new Driver(d,a=>program.getOrElse(a,BigInt(0x13)),7)
      for(_ <- 0 until 180) driver.tick(pop=false)
      while(driver.observed.size<expected.size && driver.time<1000) driver.tick(pop=driver.time%5!=0)
      assert(driver.observed.map(_._1).toSeq==expected)
      assert(driver.observed.forall { case(pc,inst) => program(pc)==inst })
    }
  }
  it should "discard an old refill after flush remaps the same virtual PC" in {
    test(new CoreFrontend) { d =>
      init(d)
      val driver=new Driver(d,a=>if(a<base+0x1000) BigInt(0x11100093) else BigInt(0x22200093),25)
      while(driver.pending.isEmpty && driver.time<100) driver.tick(pop=false)
      assert(driver.pending.nonEmpty)
      driver.alias=0x1000
      // Repeated redirects must never resurrect the outstanding old owner.
      for (_ <- 0 until 12) driver.tick(pop=false,flush=true)
      while(driver.observed.isEmpty && driver.time<250) driver.tick()
      assert(driver.observed.nonEmpty)
      assert(driver.observed.head==(base,BigInt(0x22200093)))
    }
  }
}
