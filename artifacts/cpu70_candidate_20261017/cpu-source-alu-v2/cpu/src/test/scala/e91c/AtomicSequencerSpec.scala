package e91c

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.mem.AtomicSequencer

class AtomicSequencerSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def init(d: AtomicSequencer): Unit = {
    d.io.request.valid.poke(false.B); d.io.result.ready.poke(false.B)
    d.io.request.bits.robid.poke(7.U); d.io.request.bits.operation.poke(0.U)
    d.io.request.bits.physicalAddress.poke("h80001000".U); d.io.request.bits.operand.poke(0.U)
    d.io.request.bits.virtualAddress.poke("h80001000".U)
    d.io.readRequest.ready.poke(true.B); d.io.readResponse.valid.poke(false.B)
    d.io.readResponse.bits.data.poke(0.U); d.io.readResponse.bits.error.poke(false.B)
    d.io.flush.poke(false.B); d.io.commit.poke(false.B); d.io.commitRobid.poke(7.U)
    d.io.invalidateReservation.poke(false.B); d.clock.step()
  }
  private def begin(d: AtomicSequencer, op: Int, rhs: BigInt): Unit = {
    d.io.request.ready.expect(true.B)
    d.io.request.bits.operation.poke(op.U); d.io.request.bits.operand.poke(rhs.U)
    d.io.request.valid.poke(true.B); d.clock.step(); d.io.request.valid.poke(false.B)
  }
  private def load(d: AtomicSequencer, old: BigInt, error: Boolean = false): Unit = {
    d.io.readRequest.valid.expect(true.B); d.clock.step()
    d.io.readResponse.bits.data.poke(old.U); d.io.readResponse.bits.error.poke(error.B)
    d.io.readResponse.valid.poke(true.B); d.clock.step(); d.io.readResponse.valid.poke(false.B)
    d.io.result.valid.expect(true.B)
  }
  private def commit(d: AtomicSequencer): Unit = {
    d.io.result.ready.poke(true.B); d.clock.step(); d.io.result.ready.poke(false.B)
    d.io.request.ready.expect(false.B)
    d.io.commit.poke(true.B); d.clock.step(); d.io.commit.poke(false.B)
  }
  behavior of "AtomicSequencer"
  it should "return old data and defer all nine AMO write payloads until commit" in {
    test(new AtomicSequencer) { d =>
      init(d)
      val old = BigInt("80000003",16); val rhs = BigInt(5)
      val cases = Seq(0 -> BigInt("80000008",16),1 -> rhs,4 -> BigInt("80000006",16),
        8 -> BigInt("80000007",16),12 -> BigInt(1),16 -> old,20 -> rhs,24 -> rhs,28 -> old)
      for ((op,expected) <- cases) {
        begin(d,op,rhs); load(d,old)
        d.io.result.bits.data.expect(old.U); d.io.result.bits.storeData.expect(expected.U)
        d.io.result.bits.storeMask.expect(15.U); d.io.result.bits.accessFault.expect(false.B)
        d.clock.step(2); d.io.result.valid.expect(true.B)
        commit(d)
      }
    }
  }
  it should "create LR reservations at retirement and invalidate every SC attempt" in {
    test(new AtomicSequencer) { d =>
      init(d)
      begin(d,3,9); d.io.result.bits.data.expect(1.U); d.io.result.bits.storeMask.expect(0.U); commit(d)
      begin(d,2,0); load(d,42); d.io.result.bits.storeMask.expect(0.U); commit(d)
      begin(d,3,9); d.io.result.bits.data.expect(0.U); d.io.result.bits.storeMask.expect(15.U); commit(d)
      begin(d,3,9); d.io.result.bits.data.expect(1.U); commit(d)
      begin(d,2,0); load(d,42); commit(d)
      d.io.invalidateReservation.poke(true.B); d.clock.step(); d.io.invalidateReservation.poke(false.B)
      begin(d,3,9); d.io.result.bits.data.expect(1.U); commit(d)
    }
  }
  it should "drain killed reads and suppress writes on read errors" in {
    test(new AtomicSequencer) { d =>
      init(d); begin(d,0,5); d.clock.step()
      d.io.flush.poke(true.B); d.clock.step(); d.io.flush.poke(false.B)
      d.io.request.ready.expect(false.B); d.io.result.valid.expect(false.B)
      d.io.readResponse.valid.poke(true.B); d.clock.step(); d.io.readResponse.valid.poke(false.B)
      d.io.request.ready.expect(true.B)
      begin(d,0,5); load(d,99,error=true)
      d.io.result.bits.accessFault.expect(true.B); d.io.result.bits.storeMask.expect(0.U)
      d.io.flush.poke(true.B); d.clock.step(); d.io.flush.poke(false.B)
      begin(d,3,9); d.io.result.bits.data.expect(1.U)
    }
  }
}
