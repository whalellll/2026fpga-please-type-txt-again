package e91c

import chisel3._
import chiseltest._
import e91c.exec.FuAlu
import org.scalatest.flatspec.AnyFlatSpec

class FuAluTimingHarness extends Module {
  val candidate = Module(new FuAlu)
  val original = Module(new OriginalFuAluTimingReference)
  val io = IO(chiselTypeOf(candidate.io))
  candidate.io <> io
  original.io.flush := io.flush
  original.io.issueValid := io.issueValid
  original.io.issueRobid := io.issueRobid
  original.io.issuePc := io.issuePc
  original.io.issueAluOp := io.issueAluOp
  original.io.issueBrOp := io.issueBrOp
  original.io.issueSrc0 := io.issueSrc0
  original.io.issueSrc1 := io.issueSrc1
  original.io.issueImm := io.issueImm
  original.io.issueUseImm := io.issueUseImm
  original.io.issueBrOffs := io.issueBrOffs
  original.io.issuePredTaken := io.issuePredTaken
  original.io.issueFtqId := io.issueFtqId
  val known = RegInit(false.B)
  when(io.issueValid && !io.flush && !reset.asBool) { known := true.B }
  val mismatch = IO(Output(Bool()))
  mismatch := known && (candidate.io.asUInt =/= original.io.asUInt)
}

class FuAluTimingSpec extends AnyFlatSpec with ChiselScalatestTester {
  "FuAlu timing rewrite" should "match every observable bit and original capture cycle" in {
    test(new FuAluTimingHarness) { d =>
      val random = new scala.util.Random(0x704a1eafL)
      val edges = Seq[BigInt](0,1,3,4,31,32,0x7fffffffL,0x80000000L,0xfffffffcL,0xffffffffL)
      for (cycle <- 0 until 16384) {
        def value(index: Int): BigInt =
          if (cycle < 4096) edges((cycle+index)%edges.size) else BigInt(32,random)
        val br = if(cycle<8192) (cycle>>5)&255 else random.nextInt(256)
        val alu = if(cycle%16<15) 1<<(cycle%16) else random.nextInt(32768)
        d.reset.poke((cycle<2 || cycle%509==0).B)
        d.io.flush.poke((cycle%61==0 || random.nextInt(256)==0).B)
        d.io.issueValid.poke((cycle%7!=0).B)
        d.io.issueRobid.poke((cycle&31).U)
        d.io.issuePc.poke(value(0).U)
        d.io.issueAluOp.poke(alu.U)
        d.io.issueBrOp.poke(br.U)
        d.io.issueSrc0.poke(value(1).U)
        d.io.issueSrc1.poke((if(cycle%3==0) value(1) else value(2)).U)
        d.io.issueImm.poke(value(3).U)
        d.io.issueUseImm.poke((cycle%2==0).B)
        d.io.issueBrOffs.poke(value(4).U)
        d.io.issuePredTaken.poke((cycle%2!=0).B)
        d.io.issueFtqId.poke((cycle&15).U)
        d.clock.step()
        d.mismatch.expect(false.B)
      }
      println("FUALU_TIMING_CONTRACT_PASS cycles=16384 branches=256 multi_hot=wrap=flush=reset=bubble=invalid_payload")
    }
  }
}
