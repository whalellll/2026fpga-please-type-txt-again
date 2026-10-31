package e91c

import chisel3._
import chisel3.reflect.DataMirror
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.mem.{CompactLoadOrderQueue, LoadOrderQueue}
import e91c.backend.{Commit, Ctrl, EarlyBranchRecovery}
import e91c.config.PrivType

class LoadOrderSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def clear(x: Data): Unit = x match {
    case r: Record => r.elements.values.foreach(clear)
    case v: Vec[_] => v.foreach(clear)
    case b: Bool if DataMirror.directionOf(b)==ActualDirection.Input => b.poke(false.B)
    case u: UInt if DataMirror.directionOf(u)==ActualDirection.Input => u.poke(0.U)
    case _ => ()
  }
  "Load order validation" should "compare physical byte overlap and ROB age across pointer wrap" in {
    test(new LoadOrderQueue) { d =>
      clear(d.io); d.io.head.poke(14.U); d.clock.step()
      // In program order: tag 14, 30, 15, 31, 0, 16, 1, 17 ...
      d.io.loadValid.poke(true.B); d.io.loadTag.poke(0.U)
      d.io.loadAddress.poke("h80001000".U); d.io.loadMask.poke(2.U); d.clock.step()
      d.io.loadValid.poke(false.B); d.io.storeValid.poke(true.B); d.io.storeTag.poke(31.U)
      d.io.storeAddress.poke("h80001000".U); d.io.storeMask.poke(1.U)
      d.io.replay.expect(0.U); d.clock.step()
      d.io.storeMask.poke(2.U); d.io.replay.expect(0.U); d.clock.step()
      d.io.storeValid.poke(false.B); d.io.replay.expect(1.U)
      d.io.flush.poke(true.B); d.clock.step(); d.io.flush.poke(false.B)
      d.io.replay.expect(0.U)
      d.io.loadValid.poke(true.B); d.io.loadTag.poke(15.U); d.clock.step()
      d.io.loadValid.poke(false.B); d.io.storeValid.poke(true.B); d.io.storeTag.poke(0.U)
      d.io.replay.expect(0.U) // A younger store must not invalidate an older load.
      d.io.storeValid.poke(false.B); d.io.retire.poke((BigInt(1)<<15).U); d.clock.step()
      d.io.retire.poke(0.U); d.io.storeValid.poke(true.B); d.io.storeTag.poke(14.U)
      d.io.replay.expect(0.U) // Retired entries cannot poison a reused ROB tag.
    }
  }
  it should "conservatively replay unequal word addresses with the same folded signature" in {
    test(new LoadOrderQueue) { d =>
      clear(d.io); d.io.head.poke(0.U); d.clock.step()
      d.io.loadValid.poke(true.B); d.io.loadTag.poke(1.U)
      d.io.loadAddress.poke("h80001000".U); d.io.loadMask.poke(1.U); d.clock.step()
      d.io.loadValid.poke(false.B); d.io.storeValid.poke(true.B); d.io.storeTag.poke(0.U)
      // Toggling address bits 2 and 14 preserves the XOR-folded signature.
      d.io.storeAddress.poke("h80005004".U); d.io.storeMask.poke(1.U)
      d.io.replay.expect(0.U)
      d.clock.step(); d.io.storeValid.poke(false.B); d.io.replay.expect(2.U)
    }
  }
  it should "compress multiple conflicts into the oldest precise replay owner" in {
    test(new CompactLoadOrderQueue) { d =>
      clear(d.io); d.clock.step()
      d.io.headTag.poke(12.U)

      def reserve(load: Int): Unit = {
        d.io.reserveValid.poke(true.B)
        d.io.reserveLoadTag.poke(load.U)
        d.io.reserveStoreTag.poke(28.U)
        d.io.reserveReady.expect(true.B)
        d.clock.step(); d.io.reserveValid.poke(false.B)
        d.io.resolveValid.poke(true.B)
        d.io.resolveTag.poke(load.U)
        d.io.resolveCacheable.poke(true.B)
        d.io.resolveAddress.poke("h80001000".U)
        d.io.resolveMask.poke("hf".U)
        d.clock.step(); d.io.resolveValid.poke(false.B)
      }

      // For store tag28 the circular order is 28, tag13, tag29, ..., tag30.
      // Allocate the younger conflict first to prove selection is not slot order.
      reserve(30)
      reserve(14)
      reserve(29)
      reserve(13)
      d.io.storeValid.poke(true.B)
      d.io.storeTag.poke(28.U)
      d.io.storeAddress.poke("h80001000".U)
      d.io.storeMask.poke("hf".U)
      d.clock.step(); d.io.storeValid.poke(false.B)
      d.io.replayValid.expect(true.B)
      d.io.replayTag.expect(13.U)
      // Store resolution released all table entries even though one poison
      // owner remains registered until the precise flush.
      d.io.reserveReady.expect(true.B)
      d.io.flush.poke(true.B); d.clock.step(); d.io.flush.poke(false.B)
      d.io.replayValid.expect(false.B)
    }
  }
  it should "release non-conflicts and backpressure only the fifth unresolved owner" in {
    test(new CompactLoadOrderQueue) { d =>
      clear(d.io); d.clock.step()
      d.io.reserveValid.poke(true.B)
      for (i <- 0 until 4) {
        d.io.reserveReady.expect(true.B)
        d.io.reserveLoadTag.poke((i + 1).U)
        d.io.reserveStoreTag.poke((i + 16).U)
        d.clock.step()
      }
      d.io.reserveReady.expect(false.B)
      d.io.flush.poke(true.B); d.clock.step()
      d.io.flush.poke(false.B); d.io.reserveValid.poke(false.B)

      d.io.reserveValid.poke(true.B)
      d.io.reserveLoadTag.poke(5.U); d.io.reserveStoreTag.poke(4.U)
      d.clock.step(); d.io.reserveValid.poke(false.B)
      d.io.resolveValid.poke(true.B); d.io.resolveTag.poke(5.U)
      d.io.resolveCacheable.poke(true.B)
      d.io.resolveAddress.poke("h80002000".U); d.io.resolveMask.poke("hf".U)
      d.clock.step(); d.io.resolveValid.poke(false.B)
      d.io.storeValid.poke(true.B); d.io.storeTag.poke(4.U)
      d.io.storeAddress.poke("h80003000".U); d.io.storeMask.poke("hf".U)
      d.clock.step(); d.io.storeValid.poke(false.B)
      d.io.replayValid.expect(false.B); d.io.reserveReady.expect(true.B)
    }
  }
  it should "refetch a poisoned head without retirement and block dual retirement across it" in {
    test(new Commit) { d =>
      clear(d.io); d.io.headRobid0.poke(3.U); d.io.sbEmpty.poke(true.B)
      for(i <- 0 until 2) {
        d.io.c(i).valid.poke(true.B); d.io.c(i).complete.poke(true.B)
        d.io.c(i).rfWe.poke(true.B); d.io.c(i).rd.poke((i+1).U)
        d.io.c(i).pc.poke((BigInt("80000000",16)+i*4).U)
      }
      d.io.replayValid.poke(true.B); d.io.replayTag.poke(19.U)
      d.io.retire0Valid.expect(true.B); d.io.retire1Valid.expect(false.B)
      d.io.flushReq.expect(false.B)
      d.io.c(0).valid.poke(false.B)
      d.io.flushReq.expect(true.B); d.io.flushPc.expect("h80000004".U)
      d.io.retire1Valid.expect(false.B); d.io.arfWe(1).expect(false.B); d.io.csrCmtEx.expect(false.B)
      d.io.c(0).valid.poke(true.B); d.io.replayTag.poke(3.U)
      d.io.flushReq.expect(true.B); d.io.flushPc.expect("h80000000".U)
      d.io.retire0Valid.expect(false.B); d.io.retire1Valid.expect(false.B)
      d.io.csrCmtValid.expect(false.B); d.io.sbPushValid.expect(false.B)
      d.io.replayTag.poke(4.U)
      d.io.retire0Valid.expect(true.B); d.io.retire1Valid.expect(true.B); d.io.csrCmtRetireCount.expect(2.U)
    }
  }
  it should "form a FENCE.I command from the selected retired PC" in {
    test(new Commit) { d =>
      clear(d.io); d.io.sbEmpty.poke(true.B); d.io.headRobid0.poke(5.U)
      d.io.c(0).valid.poke(true.B); d.io.c(0).complete.poke(true.B)
      d.io.c(0).pc.poke("h80000120".U)
      d.io.c(0).privVec.poke((BigInt(1) << PrivType.FENCE_I).U)
      d.io.fenceIV.expect(true.B)
      d.io.flushReq.expect(true.B); d.io.flushPc.expect("h80000124".U)
      d.io.ftqCmtPc.expect("h80000120".U)
      d.io.retire0Valid.expect(true.B)
      d.io.sbEmpty.poke(false.B)
      d.io.fenceIV.expect(false.B); d.io.retire0Valid.expect(false.B)
    }
  }
  it should "redirect the oldest aligned conditional direction miss and retain its owner" in {
    test(new EarlyBranchRecovery) { d =>
      clear(d.io)
      d.io.headRobid.poke(14.U)
      // Program order across this pair boundary is 14, 30, 15, 31, 0, ...
      d.io.laneValid(0).poke(true.B); d.io.laneIsCond(0).poke(true.B)
      d.io.laneRobid(0).poke(15.U); d.io.lanePc(0).poke("h80000100".U)
      d.io.lanePredTaken(0).poke(false.B); d.io.laneTaken(0).poke(true.B)
      d.io.laneTarget(0).poke("h80000200".U); d.io.laneFtqId(0).poke(5.U)
      d.io.laneValid(1).poke(true.B); d.io.laneIsCond(1).poke(true.B)
      d.io.laneRobid(1).poke(30.U); d.io.lanePc(1).poke("h80000080".U)
      d.io.lanePredTaken(1).poke(true.B); d.io.laneTaken(1).poke(false.B)
      d.io.laneTarget(1).poke("h80000300".U); d.io.laneFtqId(1).poke(4.U)
      d.clock.step()
      d.io.redirectValid.expect(true.B); d.io.redirectPc.expect("h80000084".U)
      d.io.redirectFtqId.expect(4.U); d.io.redirectTaken.expect(false.B)
      d.io.pendingValid.expect(true.B); d.io.pendingRobid.expect(30.U)
      d.io.recoveryStall.expect(true.B)

      // A younger miss cannot replace the recovery owner.
      d.io.laneValid(1).poke(false.B); d.io.laneRobid(0).poke(15.U)
      d.clock.step(); d.io.redirectValid.expect(false.B); d.io.pendingRobid.expect(30.U)

      // A truly older miss can replace it, while a misaligned taken target cannot.
      d.io.laneRobid(0).poke(14.U); d.io.lanePc(0).poke("h80000040".U)
      d.io.laneTarget(0).poke("h80000400".U); d.clock.step()
      d.io.redirectValid.expect(true.B); d.io.pendingRobid.expect(14.U)
      d.io.laneRobid(0).poke(13.U); d.io.laneTarget(0).poke("h80000402".U)
      d.clock.step(); d.io.redirectValid.expect(false.B)

      d.io.globalFlush.poke(true.B); d.clock.step()
      d.io.pendingValid.expect(false.B); d.io.recoveryStall.expect(false.B)
    }
  }
  it should "preserve recovered frontend state only for the matching precise branch flush" in {
    test(new Commit) { d =>
      clear(d.io); d.io.headRobid0.poke(3.U); d.io.sbEmpty.poke(true.B)
      d.io.c(0).valid.poke(true.B); d.io.c(0).complete.poke(true.B)
      d.io.c(0).pc.poke("h80000080".U); d.io.c(0).isBranch.poke(true.B)
      d.io.c(0).brType.poke(0.U); d.io.c(0).predTaken.poke(false.B)
      d.io.c(0).brTaken.poke(true.B); d.io.c(0).brTarget.poke("h80000100".U)
      d.io.c(0).isLast.poke(true.B); d.io.c(0).ftqId.poke(4.U)
      d.io.earlyRecoveryValid.poke(true.B); d.io.earlyRecoveryRobid.poke(3.U)
      d.io.flushReq.expect(true.B); d.io.flushPc.expect("h80000100".U)
      d.io.preserveFrontend.expect(true.B)
      d.io.earlyRecoveryRobid.poke(4.U); d.io.preserveFrontend.expect(false.B)
      d.io.earlyRecoveryRobid.poke(3.U); d.io.c(0).brTarget.poke("h80000101".U)
      d.io.preserveFrontend.expect(false.B); d.io.csrCmtEx.expect(true.B)
    }
  }
  it should "keep the precise backend flush while suppressing only its matched frontend pulse" in {
    test(new Ctrl) { d =>
      clear(d.io); d.clock.step()
      d.io.cmtFlushReq.poke(true.B); d.io.cmtFlushPc.poke("h80000100".U)
      d.io.cmtPreserveFrontend.poke(true.B); d.clock.step()
      d.io.flush.expect(true.B); d.io.frontendFlush.expect(false.B)
      d.io.flushPc.expect("h80000100".U)
      d.io.cmtPreserveFrontend.poke(false.B); d.clock.step()
      d.io.flush.expect(true.B); d.io.frontendFlush.expect(true.B)
    }
  }
}
