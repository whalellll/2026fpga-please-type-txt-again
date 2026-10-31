package e91c
import chisel3._
import chisel3.reflect.DataMirror
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.backend.{Rename, Dispatch, Rob, Commit}
import e91c.rename.Rat
import e91c.config.{FuType, PrivType}

class DualIssueSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def clear(x: Data): Unit = x match {
    case r: Record => r.elements.values.foreach(clear)
    case v: Vec[_] => v.foreach(clear)
    case b: Bool if DataMirror.directionOf(b)==ActualDirection.Input => b.poke(false.B)
    case u: UInt if DataMirror.directionOf(u)==ActualDirection.Input => u.poke(0.U)
    case _ => ()
  }
  "Two-wide rename" should "allocate paired ALUs with RAW tags, WAW and half-pair wrap, then flush" in {
    test(new Rename) { d =>
      clear(d.io); d.io.dispatchReady.poke(true.B); d.io.robEmpty.poke(true.B)
      d.clock.step()
      for(i <- 0 until 2) {
        d.io.ibValid(i).poke(true.B); d.io.ibInst(i).poke("h00108093".U)
        d.io.ibRfWe(i).poke(true.B); d.io.ibRdAddr(i).poke(1.U)
        d.io.ibFutype(i).poke((1<<FuType.ALU).U)
      }
      d.io.ibUseSrc0(1).poke(true.B); d.io.ibSrc0Addr(1).poke(1.U)
      d.io.ibReady.foreach(_.expect(true.B)); d.io.ratWnum(0).expect(0.U); d.io.ratWnum(1).expect(16.U)
      d.clock.step(); d.io.disValid.foreach(_.expect(true.B))
      d.io.disSrc0Ready(1).expect(false.B); d.io.disSrc0Robid(1).expect(0.U)
      d.io.robTail.poke(15.U); d.io.robTailHalf.poke(true.B)
      d.io.ratWnum(0).expect(31.U); d.io.ratWnum(1).expect(0.U)
      d.io.robFull.poke(true.B); d.io.ibReady.foreach(_.expect(false.B))
      d.io.flush.poke(true.B); d.clock.step(); d.io.disValid.foreach(_.expect(false.B))
    }
  }
  it should "serialize CSR in either slot while retaining memory and MDU pairing" in {
    test(new Rename) { d =>
      clear(d.io); d.io.dispatchReady.poke(true.B); d.io.robEmpty.poke(true.B); d.clock.step()
      for(i <- 0 until 2) { d.io.ibValid(i).poke(true.B); d.io.ibInst(i).poke("h00100093".U); d.io.ibRfWe(i).poke(true.B) }
      for((a,b) <- Seq((FuType.ALU,FuType.MEM),(FuType.ALU,FuType.MDU),(FuType.MEM,FuType.MDU))) {
        d.io.ibFutype(0).poke((1<<a).U); d.io.ibFutype(1).poke((1<<b).U)
        d.io.ibReady.foreach(_.expect(true.B))
      }
      for(i <- 0 until 2) {
        d.io.ibPrivVec(i).poke((1<<PrivType.CSR_WR).U)
        d.io.ibReady(0).expect(true.B); d.io.ibReady(1).expect(false.B)
        d.io.robEmpty.poke(false.B); d.io.ibReady.foreach(_.expect(false.B))
        d.io.robEmpty.poke(true.B); d.io.ibPrivVec(i).poke(0.U)
      }
    }
  }
  "Two-wide dispatch" should "route ALU pairs and mixed units in order under backpressure and bypass" in {
    test(new Dispatch) { d =>
      clear(d.io)
      d.io.rsAluCanAccept.foreach(_.poke(true.B)); d.io.rsMemCanAccept.poke(true.B)
      d.io.rsMemCanAcceptTwo.poke(true.B); d.io.rsMduCanAccept.poke(true.B)
      for(i <- 0 until 2) { d.io.disValid(i).poke(true.B); d.io.disRobid(i).poke(i.U) }
      for((a,b) <- Seq((FuType.ALU,FuType.ALU),(FuType.ALU,FuType.MEM),(FuType.ALU,FuType.MDU),(FuType.MEM,FuType.MDU),(FuType.MEM,FuType.MEM))) {
        d.io.disFutype(0).poke((1<<a).U); d.io.disFutype(1).poke((1<<b).U)
        d.io.disFire.foreach(_.expect(true.B)); d.io.dispatchReady.expect(true.B)
        if(a==FuType.ALU && b==FuType.ALU) d.io.rsAluPushValid.foreach(_.expect(true.B))
      }
      d.io.disFutype(0).poke((1<<FuType.MEM).U); d.io.disFutype(1).poke((1<<FuType.MDU).U)
      d.io.rsMemCanAccept.poke(false.B); d.io.disFire.foreach(_.expect(false.B))
      d.io.rsMemCanAccept.poke(true.B); d.io.rsMduCanAccept.poke(false.B)
      d.io.disFire(0).expect(true.B); d.io.disFire(1).expect(false.B)
      d.io.rsMduCanAccept.poke(true.B); d.io.robRrdy(2).poke(true.B); d.io.robRdata(2).poke(123.U)
      d.io.rsMduPushSrc0Ready.expect(true.B); d.io.rsMduPushSrc0Val.expect(123.U)

      clear(d.io)
      d.io.rsMduCanAccept.poke(true.B)
      d.io.disValid(0).poke(true.B)
      d.io.disFutype(0).poke((1 << FuType.MDU).U)
      d.io.disSrc0Ready(0).poke(false.B)
      d.io.disSrc0Robid(0).poke(9.U)
      d.io.robRrdy(0).poke(true.B)
      d.io.robRdata(0).poke("h2468ace0".U)
      d.io.rsMduPushValid.expect(true.B)
      d.io.rsMduPushSrc0Ready.expect(true.B)
      d.io.rsMduPushSrc0Val.expect("h2468ace0".U)

      clear(d.io)
      d.io.rsAluCanAccept.foreach(_.poke(true.B))
      d.io.disValid(0).poke(true.B)
      d.io.disFutype(0).poke((1 << FuType.ALU).U)
      d.io.disSrc1Ready(0).poke(false.B)
      d.io.disSrc1Robid(0).poke(10.U)
      d.io.robRrdy(1).poke(true.B)
      d.io.robRdata(1).poke("h13579bdf".U)
      d.io.rsAluPushValid(0).expect(true.B)
      d.io.rsAluPushSrc1Ready(0).expect(true.B)
      d.io.rsAluPushSrc1Val(0).expect("h13579bdf".U)
    }
  }
  "Two-wide RAT" should "keep the youngest WAW mapping across old retirement and flush" in {
    test(new Rat) { d =>
      clear(d.io); d.clock.step()
      for(i <- 0 until 2) { d.io.wen(i).poke(true.B); d.io.waddr(i).poke(7.U); d.io.wnum(i).poke(i.U) }
      d.clock.step(); d.io.wen.foreach(_.poke(false.B)); d.io.raddr(0).poke(7.U)
      d.io.rbusy(0).expect(true.B); d.io.rnum(0).expect(1.U)
      d.io.cmtEn(0).poke(true.B); d.io.cmtAddr(0).poke(7.U); d.io.cmtNum(0).poke(0.U)
      d.clock.step(); d.io.rbusy(0).expect(true.B)
      d.io.flush.poke(true.B); d.clock.step(); d.io.rbusy(0).expect(false.B)
    }
  }
  "Two-wide ROB" should "complete and retire an ALU pair and assert the allocation guard before wrap" in {
    test(new Rob) { d =>
      clear(d.io); d.clock.step()
      for(i <- 0 until 2) { d.io.a(i).valid.poke(true.B); d.io.a(i).rfWe.poke(true.B); d.io.a(i).rd.poke((i+1).U); d.io.a(i).pc.poke((0x1000+i*4).U) }
      d.io.allocEn.poke(true.B); d.clock.step(); d.io.allocEn.poke(false.B)
      for(i <- 0 until 2) { d.io.alu(i).valid.poke(true.B); d.io.alu(i).robid.poke((i*16).U); d.io.alu(i).data.poke((100+i).U) }
      d.clock.step(); d.io.alu.foreach(_.valid.poke(false.B))
      d.io.cmtValid.foreach(_.expect(true.B)); d.io.cmtComplete.foreach(_.expect(true.B))
      d.io.cmtResult(0).expect(100.U); d.io.cmtResult(1).expect(101.U)
      d.io.cmtClear0.poke(true.B); d.io.cmtClear1.poke(true.B); d.io.cmtPop.poke(true.B)
      d.clock.step(); d.io.robEmpty.expect(true.B)
      clear(d.io); d.io.flush.poke(true.B); d.clock.step(); clear(d.io)
      d.io.a.foreach { a => a.valid.poke(true.B); a.isNop.poke(true.B) }
      var pairs=0
      while(!d.io.robFull.peek().litToBoolean && pairs<16) { d.io.allocEn.poke(true.B); d.clock.step(); pairs+=1 }
      assert(pairs>0 && pairs<16); d.io.robFull.expect(true.B)
      val tail=d.io.robTail.peek(); d.clock.step(); d.io.robTail.expect(tail)
    }
  }
  "Two-wide commit" should "preserve precise exceptions, branches, stores and flush in both slots" in {
    test(new Commit) { d =>
      for(slot <- 0 until 2) {
        clear(d.io); d.io.sbEmpty.poke(true.B); d.io.c(slot).valid.poke(true.B)
        d.io.c(slot).complete.poke(true.B); d.io.c(slot).pc.poke((0x1000+slot*4).U)
        d.io.c(slot).excp.poke(2.U); d.io.c(slot).hasExcpFast.poke(true.B)
        d.io.csrCmtEx.expect(true.B); d.io.flushReq.expect(true.B); d.io.arfWe.foreach(_.expect(false.B))
        d.io.c(slot).excp.poke(0.U); d.io.c(slot).hasExcpFast.poke(false.B)
        d.io.c(slot).isStore.poke(true.B); d.io.c(slot).wstrb.poke(15.U)
        d.io.sbPushValid.expect(true.B); d.io.sbFull.poke(true.B); d.io.sbPushValid.expect(false.B)
        d.io.sbFull.poke(false.B); d.io.c(slot).isStore.poke(false.B)
        d.io.c(slot).isBranch.poke(true.B); d.io.c(slot).brTaken.poke(true.B); d.io.c(slot).brTarget.poke(0x2000.U)
        d.io.flushReq.expect(true.B)
        d.io.flushPending.poke(true.B); d.io.retire0Valid.expect(false.B); d.io.retire1Valid.expect(false.B)
      }
    }
  }
  it should "write the CSR address of the retiring ROB lane" in {
    test(new Commit) { d =>
      clear(d.io); d.io.sbEmpty.poke(true.B)
      d.io.c(1).valid.poke(true.B); d.io.c(1).complete.poke(true.B)
      d.io.c(1).privVec.poke((1 << PrivType.CSR_WR).U)
      d.io.c(1).csrNum.poke("h341".U)
      d.io.csrWe.expect(true.B); d.io.csrWnum.expect("h341".U)
      d.io.c(1).complete.poke(false.B)
      d.io.csrWe.expect(false.B)
      d.io.c(1).valid.poke(false.B)
      d.io.c(0).valid.poke(true.B); d.io.c(0).complete.poke(true.B)
      d.io.c(0).privVec.poke((1 << PrivType.CSR_WR).U)
      d.io.c(0).csrNum.poke("h342".U)
      d.io.csrWe.expect(true.B); d.io.csrWnum.expect("h342".U)
    }
  }
}
