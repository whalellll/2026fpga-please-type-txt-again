package e91c

import chisel3._
import chiseltest._
import e91c.decode.Decoder
import e91c.config.{FuType, MemOp, PrivType}
import org.scalatest.flatspec.AnyFlatSpec

class DecoderSpec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "RV32IMA decoder"

  it should "reject every 16-bit instruction encoding" in {
    test(new Decoder) { dut =>
      dut.io.privilege.poke(3.U)
      dut.io.status.poke(0.U)
      dut.io.counterAccess.poke(7.U)
      for (encoding <- 0 until 65536 if (encoding & 3) != 3) {
        dut.io.inst.poke(encoding.U)
        assert((dut.io.excp.peek().litValue & 2) != 0, f"0x$encoding%04x was accepted")
      }
    }
  }
  it should "select the M unit only for supported full-width integer encodings" in {
    test(new Decoder) { dut =>
      dut.io.privilege.poke(3.U)
      dut.io.status.poke(0.U)
      dut.io.counterAccess.poke(7.U)
      dut.io.inst.poke(0x022081b3L.U) // MUL x3,x1,x2
      assert((dut.io.futype.peek().litValue & (1 << FuType.MDU)) != 0)
      dut.io.inst.poke(0x0080.U) // Unsupported 16-bit encoding.
      assert((dut.io.excp.peek().litValue & 2) != 0)
      assert((dut.io.futype.peek().litValue & (1 << FuType.MDU)) == 0)
    }
  }
  it should "decode MRET and full-width EBREAK while rejecting 16-bit EBREAK" in {
    test(new Decoder) { dut =>
      dut.io.privilege.poke(3.U)
      dut.io.status.poke(0.U)
      dut.io.counterAccess.poke(7.U)
      dut.io.inst.poke("h30200073".U)
      assert((dut.io.privVec.peek().litValue & (1 << PrivType.MRET)) != 0)
      dut.io.inst.poke("h00100073".U)
      assert((dut.io.excp.peek().litValue & (1 << 3)) != 0)
      dut.io.inst.poke("h9002".U)
      assert((dut.io.excp.peek().litValue & 2) != 0)
      assert((dut.io.excp.peek().litValue & (1 << 3)) == 0)
    }
  }
  it should "serialize an unsupported CSR encoding while reporting it illegal" in {
    test(new Decoder) { dut =>
      dut.io.privilege.poke(3.U)
      dut.io.status.poke(0.U)
      dut.io.counterAccess.poke(7.U)
      dut.io.inst.poke("h999010f3".U) // CSRRW x1, 0x999, x0
      assert((dut.io.excp.peek().litValue & 2) != 0)
      assert((dut.io.futype.peek().litValue & (1 << FuType.MDU)) != 0)
    }
  }
  it should "decode all raw atomic operations and reject reserved encodings" in {
    test(new Decoder) { dut =>
      dut.io.privilege.poke(3.U)
      dut.io.status.poke(0.U)
      dut.io.counterAccess.poke(7.U)
      val supported = Set(0, 1, 2, 3, 4, 8, 12, 16, 20, 24, 28)
      for (funct <- 0 until 32; source2 <- Seq(0, 3); aqrl <- 0 until 4) {
        val encoding = (BigInt(funct) << 27) | (BigInt(aqrl) << 25) |
          (BigInt(source2) << 20) | (BigInt(1) << 15) | (BigInt(2) << 12) | (BigInt(5) << 7) | 0x2f
        val legal = supported(funct) && (funct != 2 || source2 == 0)
        dut.io.inst.poke(encoding.U)
        assert(((dut.io.memOp.peek().litValue >> MemOp.ATOMIC) & 1) == (if (legal) 1 else 0))
        assert(((dut.io.excp.peek().litValue & 2) != 0) == !legal)
      }
      for (encoding <- Seq(0x0080, 0x9002, 0x0000, 0x600d, 0x9c05)) {
        dut.io.inst.poke((BigInt("f8000000", 16) | encoding).U)
        assert(((dut.io.memOp.peek().litValue >> MemOp.ATOMIC) & 1) == 0)
      }
    }
  }
}
