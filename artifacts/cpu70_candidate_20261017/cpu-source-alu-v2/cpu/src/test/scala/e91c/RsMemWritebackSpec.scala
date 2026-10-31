package e91c
import chisel3._
import chisel3.reflect.DataMirror
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.backend.RsMem
import e91c.config.MemOp
class RsMemWritebackSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def clear(x:Data):Unit=x match {
    case r:Record=>r.elements.values.foreach(clear)
    case v:Vec[_]=>v.foreach(clear)
    case b:Bool if DataMirror.directionOf(b)==ActualDirection.Input=>b.poke(false.B)
    case u:UInt if DataMirror.directionOf(u)==ActualDirection.Input=>u.poke(0.U)
    case _=>()
  }
  "MEM writeback" should "preserve all port priorities for queued and caller-finalized push data" in {
    test(new RsMem){d=>
      clear(d.io);d.clock.step()
      for(atPushReady<-Seq(false,true); first<-0 until 5){
        d.io.lsuReady.poke(false.B)
        d.io.pushRobid.poke(3.U);d.io.pushMemOp.poke((BigInt(1)<<MemOp.ST_W).U)
        d.io.pushSrc0Ready.poke(atPushReady.B);d.io.pushSrc1Ready.poke(atPushReady.B)
        d.io.pushSrc0Robid.poke(7.U);d.io.pushSrc1Robid.poke(7.U)
        d.io.pushSrc0Val.poke((0x1000+first*4).U);d.io.pushSrc1Val.poke((0x1000+first*4).U)
        for(i<-0 until 5){
          d.io.wb(i).bits.robid.poke(7.U);d.io.wb(i).bits.data.poke((0x1000+i*4).U)
          d.io.wb(i).valid.poke((atPushReady && i>=first).B)
        }
        d.io.canAccept.expect(true.B);d.io.pushValid.poke(true.B);d.clock.step();d.io.pushValid.poke(false.B)
        if(!atPushReady){
          for(i<-0 until 5)d.io.wb(i).valid.poke((i>=first).B)
          d.clock.step()
        }
        d.io.wb.foreach(_.valid.poke(false.B));d.clock.step()
        d.io.lsuReady.poke(true.B);d.io.issueValid.expect(true.B)
        d.io.issueBase.expect((0x1000+first*4).U);d.io.issueWdata.expect((0x1000+first*4).U)
        d.io.issueBaseReady.expect(true.B);d.io.issueWdataReady.expect(true.B)
        d.clock.step();d.io.lsuReady.poke(false.B);d.io.occupancy.expect(0.U)
      }
    }
  }
  it should "keep a newly woken CLINT load behind an older store while its address hint refreshes" in {
    test(new RsMem) { d =>
      clear(d.io); d.clock.step()
      d.io.lsuReady.poke(true.B)
      d.io.pushValid.poke(true.B); d.io.push1Valid.poke(true.B)
      d.io.pushRobid.poke(11.U); d.io.push1Robid.poke(29.U)
      d.io.pushMemOp.poke((BigInt(1) << MemOp.ST_W).U)
      d.io.push1MemOp.poke((BigInt(1) << MemOp.LD_W).U)
      d.io.pushSrc0Ready.poke(true.B)
      d.io.pushSrc0Val.poke("h1c000100".U)
      d.io.pushSrc0KeyVal.poke("h1c000100".U)
      d.io.pushSrc1Ready.poke(false.B); d.io.pushSrc1Robid.poke(7.U)
      d.io.push1Src0Ready.poke(false.B); d.io.push1Src0Robid.poke(8.U)
      d.io.push1Src1Ready.poke(true.B)
      d.clock.step()
      d.io.pushValid.poke(false.B); d.io.push1Valid.poke(false.B)
      d.io.issueValid.expect(false.B)
      d.io.wb(0).valid.poke(true.B); d.io.wb(0).bits.robid.poke(8.U)
      d.io.wb(0).bits.data.poke("h0200bff8".U)
      d.clock.step(); d.io.wb(0).valid.poke(false.B)
      // The operand is ready, but pairKey still contains the old zero address.
      // Issuing here lets this younger uncached load deadlock an older store.
      d.io.issueValid.expect(false.B)
      d.clock.step(); d.io.issueValid.expect(false.B)
      d.io.wb(1).valid.poke(true.B); d.io.wb(1).bits.robid.poke(7.U)
      d.io.wb(1).bits.data.poke("h12345678".U)
      d.io.issueValid.expect(true.B); d.io.issueRobid.expect(11.U)
      d.clock.step(); d.io.wb(1).valid.poke(false.B)
      d.io.issueValid.expect(true.B); d.io.issueRobid.expect(29.U)
      d.io.issueBase.expect("h0200bff8".U)
    }
  }
  it should "accept caller-finalized operands on both push lanes" in {
    test(new RsMem){d=>
      clear(d.io);d.clock.step()
      d.io.lsuReady.poke(false.B)
      d.io.pushValid.poke(true.B);d.io.push1Valid.poke(true.B)
      d.io.pushRobid.poke(3.U);d.io.push1Robid.poke(4.U)
      d.io.pushMemOp.poke((BigInt(1)<<MemOp.ST_W).U)
      d.io.push1MemOp.poke((BigInt(1)<<MemOp.ST_W).U)
      d.io.pushSrc0Ready.poke(true.B);d.io.pushSrc0Val.poke("h1c000100".U);d.io.pushSrc0Robid.poke(7.U)
      d.io.pushSrc1Ready.poke(true.B);d.io.pushSrc1Val.poke("h11112222".U);d.io.pushSrc1Robid.poke(8.U)
      d.io.push1Src0Ready.poke(true.B);d.io.push1Src0Val.poke("h1c000200".U);d.io.push1Src0Robid.poke(9.U)
      d.io.push1Src1Ready.poke(true.B);d.io.push1Src1Val.poke("h33334444".U);d.io.push1Src1Robid.poke(10.U)
      for(i<-0 until 4){
        d.io.wb(i).valid.poke(true.B);d.io.wb(i).bits.robid.poke((7+i).U)
        d.io.wb(i).bits.data.poke(Seq(BigInt("1c000100",16),BigInt("11112222",16),BigInt("1c000200",16),BigInt("33334444",16))(i).U)
      }
      d.io.canAcceptTwo.expect(true.B);d.clock.step()
      d.io.pushValid.poke(false.B);d.io.push1Valid.poke(false.B);d.io.wb.foreach(_.valid.poke(false.B))
      d.io.occupancy.expect(2.U);d.io.lsuReady.poke(true.B)
      d.io.issueRobid.expect(3.U);d.io.issueBase.expect("h1c000100".U);d.io.issueWdata.expect("h11112222".U)
      d.clock.step()
      d.io.issueRobid.expect(4.U);d.io.issueBase.expect("h1c000200".U);d.io.issueWdata.expect("h33334444".U)
    }
  }
  it should "forbid pre-translation load bypass while Sv32 data translation is active" in {
    test(new RsMem){d=>
      clear(d.io); d.clock.step()
      d.io.dataTranslationActive.poke(true.B)
      d.io.lsuReady.poke(true.B)
      d.io.pushValid.poke(true.B); d.io.push1Valid.poke(true.B)
      d.io.pushRobid.poke(1.U); d.io.push1Robid.poke(2.U)
      d.io.pushMemOp.poke((BigInt(1)<<MemOp.LD_W).U)
      d.io.push1MemOp.poke((BigInt(1)<<MemOp.LD_W).U)
      d.io.pushSrc0Ready.poke(false.B); d.io.pushSrc0Robid.poke(7.U)
      d.io.pushSrc1Ready.poke(true.B)
      d.io.push1Src0Ready.poke(true.B); d.io.push1Src0Val.poke("h1c018000".U)
      d.io.push1Src1Ready.poke(true.B)
      d.clock.step()
      d.io.pushValid.poke(false.B); d.io.push1Valid.poke(false.B)
      d.io.issueValid.expect(false.B)
      d.io.wb(0).valid.poke(true.B); d.io.wb(0).bits.robid.poke(7.U)
      d.io.wb(0).bits.data.poke("h80001000".U)
      d.io.issueValid.expect(true.B); d.io.issueRobid.expect(1.U)
    }
  }
  it should "never issue a younger store around an unready cached load" in {
    test(new RsMem){d=>
      clear(d.io); d.clock.step()
      d.io.dataTranslationActive.poke(false.B)
      d.io.lsuReady.poke(true.B)
      d.io.pushValid.poke(true.B); d.io.push1Valid.poke(true.B)
      d.io.pushRobid.poke(1.U); d.io.push1Robid.poke(2.U)
      d.io.pushMemOp.poke((BigInt(1)<<MemOp.LD_W).U)
      d.io.push1MemOp.poke((BigInt(1)<<MemOp.ST_W).U)
      d.io.pushSrc0Ready.poke(true.B); d.io.pushSrc0Val.poke("h1c000000".U)
      d.io.pushSrc1Ready.poke(false.B); d.io.pushSrc1Robid.poke(7.U)
      d.io.push1Src0Ready.poke(true.B); d.io.push1Src0Val.poke("h1c007338".U)
      d.io.push1Src1Ready.poke(true.B); d.io.push1Src1Val.poke("h1c007340".U)
      d.clock.step()
      d.io.pushValid.poke(false.B); d.io.push1Valid.poke(false.B)
      d.io.issueValid.expect(false.B)
    }
  }
  it should "bypass only a younger load whose direct address is known cacheable" in {
    def check(candidateAddress: BigInt, shouldIssue: Boolean): Unit = {
      test(new RsMem){d=>
        clear(d.io); d.clock.step()
        d.io.dataTranslationActive.poke(false.B)
        d.io.lsuReady.poke(true.B)
        d.io.pushValid.poke(true.B); d.io.push1Valid.poke(true.B)
        d.io.pushRobid.poke(1.U); d.io.push1Robid.poke(2.U)
        d.io.pushMemOp.poke((BigInt(1)<<MemOp.LD_W).U)
        d.io.push1MemOp.poke((BigInt(1)<<MemOp.LD_W).U)
        d.io.pushSrc0Ready.poke(true.B); d.io.pushSrc0Val.poke("h1c000000".U)
        d.io.pushSrc0KeyVal.poke("h1c000000".U)
        d.io.pushSrc1Ready.poke(false.B); d.io.pushSrc1Robid.poke(7.U)
        d.io.push1Src0Ready.poke(true.B); d.io.push1Src0Val.poke(candidateAddress.U)
        d.io.push1Src0KeyVal.poke(candidateAddress.U)
        d.io.push1Src1Ready.poke(true.B)
        d.clock.step()
        d.io.pushValid.poke(false.B); d.io.push1Valid.poke(false.B)
        if (!shouldIssue) d.clock.step()
        d.io.issueValid.expect(shouldIssue.B)
        if (shouldIssue) d.io.issueRobid.expect(2.U)
      }
    }
    check(BigInt("1c000100", 16), shouldIssue = true)
    check(BigInt("1c018000", 16), shouldIssue = true)
    check(BigInt("1c01b0a8", 16), shouldIssue = true)
    check(BigInt("0200bff8", 16), shouldIssue = false)
    check(BigInt("1fe02000", 16), shouldIssue = false)
    check(BigInt("9b000000", 16), shouldIssue = false)
  }
}
