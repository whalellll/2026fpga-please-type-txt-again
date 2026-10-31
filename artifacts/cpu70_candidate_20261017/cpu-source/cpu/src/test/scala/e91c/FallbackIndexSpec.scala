package e91c

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.frontend.FallbackBtb

class FallbackIndexSpec extends AnyFlatSpec with ChiselScalatestTester {
  for (sets <- Seq(32, 64, 128)) {
    s"Hashed $sets-set BTB" should "distinguish complete PCs and retain two colliding descriptors" in {
      test(new FallbackBtb(sets, true)) { d =>
        val bits = Integer.numberOfTrailingZeros(sets)
        def address(tag: Int, set: Int): BigInt =
          (BigInt(tag) << (bits + 2)) | (BigInt(set ^ (tag & (sets - 1))) << 2)
        def query(pc: BigInt, hit: Boolean, target: BigInt): Unit = {
          d.io.queryValid.poke(true.B); d.io.queryPc.poke(pc.U)
          d.io.hit.expect(hit.B)
          if (hit) { d.io.target.expect(target.U); d.io.length.expect(3.U) }
        }
        def update(pc: BigInt, target: BigInt): Unit = {
          d.io.updValid.poke(true.B); d.io.updBlockPc.poke(pc.U)
          d.io.updTarget.poke(target.U); d.clock.step(); d.io.updValid.poke(false.B)
        }
        d.io.queryValid.poke(false.B); d.io.queryPc.poke(0.U)
        d.io.updValid.poke(false.B); d.io.updBlockPc.poke(0.U)
        d.io.updTarget.poke(0.U); d.io.updLength.poke(3.U)
        d.io.updTaken.poke(true.B); d.io.updBrType.poke(1.U); d.io.updEarly.poke(true.B)
        d.clock.step()
        for (set <- 0 until sets) {
          val a = address(0x101, set); val b = address(0x202, set)
          val c = address(0x303, set)
          update(a, a + 64); update(b, b + 128)
          query(a, true, a + 64); query(b, true, b + 128)
          query(c, false, 0)
          // Lowest invalid way is filled first, then the round-robin victim.
          update(c, c + 256)
          query(a, false, 0); query(b, true, b + 128); query(c, true, c + 256)
          // Updating one colliding descriptor must not replace the other.
          update(b, b + 512)
          query(b, true, b + 512); query(c, true, c + 256)
        }
      }
    }
  }
}
