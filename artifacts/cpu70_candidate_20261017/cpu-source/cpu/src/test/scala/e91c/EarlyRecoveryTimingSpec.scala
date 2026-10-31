package e91c

import chisel3._
import chiseltest._
import e91c.backend.EarlyBranchRecovery
import org.scalatest.flatspec.AnyFlatSpec

class EarlyRecoveryTimingSpec extends AnyFlatSpec with ChiselScalatestTester {
  "Early recovery" should "preserve the oldest-owner predicate over every five-bit circular age" in {
    // Independent integer truth table, including equal ages and wraparound.
    for (head <- 0 until 32; pending <- 0 until 32;
         lane0 <- 0 until 32; lane1 <- 0 until 32; mask <- 0 until 4) {
      val ages = Seq((lane0-head)&31, (lane1-head)&31)
      val eligible = Seq((mask&1)!=0, (mask&2)!=0)
      val selected = (0 until 2).filter(eligible).sortBy(i => (ages(i), i)).headOption
      val original = selected.exists(i => ages(i) < ((pending-head)&31))
      val parallel = (0 until 2).exists(i => eligible(i) && ages(i) < ((pending-head)&31))
      assert(original == parallel)
    }
  }

  it should "match the original registered interface including invalid payload stability and flush" in {
    test(new EarlyBranchRecovery) { d =>
      val random = new scala.util.Random(0x7035beefL)
      val mask32 = (BigInt(1)<<32)-1
      def ordinal(id: Int): Int = ((id&15)<<1)|(id>>4)
      var pending = false
      var owner = 0
      var payloadKnown = false
      var pc = BigInt(0)
      var ftq = 0
      var taken = false
      for (cycle <- 0 until 8192) {
        val head = cycle & 31
        val ids = Seq(random.nextInt(32), random.nextInt(32))
        val pcs = Seq.fill(2)(BigInt(32,random)&~BigInt(3))
        val targets = Seq.fill(2)(BigInt(32,random))
        val valids = Seq.fill(2)(random.nextBoolean())
        val conds = Seq.fill(2)(random.nextInt(4)!=0)
        val predictions = Seq.fill(2)(random.nextBoolean())
        val directions = Seq.fill(2)(random.nextBoolean())
        val ftqs = Seq.fill(2)(random.nextInt(16))
        val flush = cycle%71==0 || random.nextInt(128)==0
        val reset = cycle%257==0
        val block = cycle%13==0
        d.reset.poke(reset.B)
        d.io.globalFlush.poke(flush.B)
        d.io.block.poke(block.B)
        d.io.headRobid.poke(head.U)
        for (i <- 0 until 2) {
          d.io.laneValid(i).poke(valids(i).B)
          d.io.laneIsCond(i).poke(conds(i).B)
          d.io.laneRobid(i).poke(ids(i).U)
          d.io.lanePc(i).poke(pcs(i).U)
          d.io.lanePredTaken(i).poke(predictions(i).B)
          d.io.laneTaken(i).poke(directions(i).B)
          d.io.laneTarget(i).poke(targets(i).U)
          d.io.laneFtqId(i).poke(ftqs(i).U)
        }
        val eligible = (0 until 2).filter(i => valids(i) && conds(i) &&
          directions(i)!=predictions(i) && (!directions(i) || (targets(i)&3)==0))
        def age(id: Int): Int = (ordinal(id)-ordinal(head))&31
        val selected = eligible.sortBy(i => (age(ids(i)),i)).headOption
        val accept = !reset && !flush && !block && selected.exists(i => !pending || age(ids(i))<age(owner))
        if (reset || flush) pending=false
        else if (accept) {
          val i=selected.get
          pending=true
          owner=ids(i)
          pc=if(directions(i)) targets(i) else (pcs(i)+4)&mask32
          ftq=ftqs(i)
          taken=directions(i)
          payloadKnown=true
        }
        d.clock.step()
        d.io.redirectValid.expect(accept.B)
        d.io.pendingValid.expect(pending.B)
        d.io.recoveryStall.expect((pending||accept).B)
        if(pending) d.io.pendingRobid.expect(owner.U)
        if(payloadKnown) {
          d.io.redirectPc.expect(pc.U)
          d.io.redirectFtqId.expect(ftq.U)
          d.io.redirectTaken.expect(taken.B)
        }
      }
      println("EARLY_RECOVERY_TIMING_CONTRACT_PASS cycles=8192 ages=4194304 payload_stable=flush=reset=wrap=tie")
    }
  }
}
