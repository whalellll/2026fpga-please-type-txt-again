package e91c

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.backend.RsAlu

class SpeculativeWakeupSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def init(d: RsAlu): Unit = {
    d.io.flush.poke(false.B); d.io.pushValid.poke(false.B)
    d.io.pushRobid.poke(0.U); d.io.pushPc.poke(0.U); d.io.pushAluOp.poke(1.U)
    d.io.pushBrOp.poke(0.U); d.io.pushSrc0Ready.poke(false.B); d.io.pushSrc0Val.poke(0.U)
    d.io.pushSrc0Robid.poke(0.U); d.io.pushSrc1Ready.poke(true.B); d.io.pushSrc1Val.poke(7.U)
    d.io.pushSrc1Robid.poke(0.U); d.io.pushImm.poke(0.U); d.io.pushUseImm.poke(false.B)
    d.io.pushBrOffs.poke(0.U); d.io.pushPredTaken.poke(false.B); d.io.pushFtqId.poke(0.U)
    d.io.fast2Valid.poke(false.B); d.io.fast2Robid.poke(0.U)
    d.io.fast2Data.poke(0.U); d.io.pre3Valid.poke(false.B); d.io.pre3Robid.poke(0.U)
    for(i <- 0 until 5) { d.io.wbValid(i).poke(false.B); d.io.wbRobid(i).poke(0.U); d.io.wbData(i).poke(0.U) }
    for(i <- 0 until 3) { d.io.earlyValid(i).poke(false.B); d.io.earlyRobid(i).poke(0.U) }
    d.clock.step()
  }
  private def enqueue(d: RsAlu, consumer: Int, producer: Int): Unit = {
    d.io.canAccept.expect(true.B); d.io.pushRobid.poke(consumer.U)
    d.io.pushSrc0Robid.poke(producer.U); d.io.pushValid.poke(true.B)
    d.clock.step(); d.io.pushValid.poke(false.B)
  }
  private def predict(d: RsAlu, producer: Int): Unit = {
    d.io.earlyValid(2).poke(true.B); d.io.earlyRobid(2).poke(producer.U)
    d.clock.step(); d.io.earlyValid(2).poke(false.B)
    d.io.speculativeSelect.expect(true.B)
  }
  "Load-hit speculative selection" should "use validated hit data and retain the consumer after a miss" in {
    test(new RsAlu(4)) { d =>
      init(d); enqueue(d,2,1); predict(d,1)
      d.io.fast2Valid.poke(true.B); d.io.fast2Robid.poke(1.U); d.io.fast2Data.poke(123.U)
      d.io.speculativeCancel.expect(false.B); d.io.issueValid.expect(true.B)
      d.io.issueRobid.expect(2.U); d.io.issueSrc0.expect(123.U); d.io.issueSrc1.expect(7.U)
      d.clock.step(); d.io.fast2Valid.poke(false.B)
      enqueue(d,4,3); predict(d,3)
      d.io.speculativeCancel.expect(true.B); d.io.issueValid.expect(false.B)
      d.clock.step(4); d.io.occupancy.expect(1.U); d.io.issueValid.expect(false.B)
      d.io.wbValid(2).poke(true.B); d.io.wbRobid(2).poke(3.U); d.io.wbData(2).poke(456.U)
      d.clock.step(); d.io.wbValid(2).poke(false.B)
      d.io.issueValid.expect(true.B); d.io.issueSrc0.expect(456.U)
      d.clock.step(); d.io.occupancy.expect(0.U)
    }
  }
  it should "cancel on flush and reject a response with the wrong producer tag" in {
    test(new RsAlu(4)) { d =>
      init(d); enqueue(d,2,1); predict(d,1)
      d.io.fast2Valid.poke(true.B); d.io.fast2Robid.poke(9.U); d.io.fast2Data.poke(999.U)
      d.io.speculativeCancel.expect(true.B); d.io.issueValid.expect(false.B)
      d.io.flush.poke(true.B); d.clock.step(); d.io.flush.poke(false.B)
      d.io.fast2Valid.poke(false.B); d.io.occupancy.expect(0.U)
      enqueue(d,2,5)
      d.io.fast2Valid.poke(true.B); d.io.fast2Robid.poke(1.U)
      d.io.issueValid.expect(false.B); d.io.speculativeSelect.expect(false.B)
    }
  }
}
