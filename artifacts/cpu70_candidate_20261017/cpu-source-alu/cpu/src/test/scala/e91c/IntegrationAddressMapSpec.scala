package e91c

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.mem.PmaMmu

/** Contract exercised by performance_soc's bootloader, DDR loaders and DMA. */
class IntegrationAddressMapSpec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "CPU physical address map"
  for ((name, addresses) <- Seq(
      "boot BRAM including the production CoreMark workspace" -> Seq(
        "1c000000", "1c017ffc", "1c018000", "1c01b0a8", "1c01b874",
        "1c01bffc", "1c01c000", "1c01fffc"),
      "former PLIC window" -> Seq("0bfffffc", "0c000000", "0c001000", "0ffffffc"),
      "former UART window" -> Seq("10000000", "10000ffc", "10001000"),
      "former peripheral hi16 windows" -> Seq("1fbffffc", "1fc00000", "1fc0fffc", "1fc10000",
        "1fcffffc", "1fd00000", "1fd0fffc", "1fd10000", "1ff00000", "1ff0fffc", "1ff10000",
        "1d00fffc", "1d010000", "1d020000", "1d030000", "1d03fffc", "1d040000"))) {
    it should s"keep the $name cacheable and its high data alias uncached" in {
      test(new PmaMmu) { d =>
        d.io.privilege.poke(3.U); d.io.dataPrivilege.poke(3.U)
        d.io.satp.poke(0.U); d.io.status.poke(0.U)
        d.io.flush.poke(false.B); d.io.instructionCancel.poke(false.B)
        d.io.fence.poke(false.B)
        d.io.iReq.poke(true.B); d.io.iAccept.poke(false.B)
        d.io.dReq.poke(true.B); d.io.dAccept.poke(false.B)
        d.io.dIsStore.poke(false.B)
        d.io.pageRequest.ready.poke(false.B)
        d.io.pageResponse.valid.poke(false.B)
        d.io.pageResponse.bits.data.poke(0.U)
        d.io.pageResponse.bits.error.poke(false.B)
        for (hex <- addresses; alias <- Seq(false, true)) {
          val address = BigInt(hex, 16) | (if (alias) BigInt("80000000", 16) else BigInt(0))
          d.io.iVaddr.poke(address.U); d.io.dVaddr.poke(address.U)
          d.io.iReady.expect(true.B); d.io.iFaults.expect(0.U)
          d.io.iDirectExcp.expect(false.B); d.io.iMat.expect(1.U)
          d.io.dReady.expect(true.B); d.io.dAccessFault.expect(false.B)
          d.io.dMat.expect((if (alias) 0 else 1).U)
          d.clock.step()
        }
      }
    }
  }
  it should "execute low DDR and keep the full DDR data alias uncached" in {
    test(new PmaMmu) { d =>
      d.io.privilege.poke(3.U); d.io.dataPrivilege.poke(3.U)
      d.io.satp.poke(0.U); d.io.status.poke(0.U)
      d.io.flush.poke(false.B); d.io.instructionCancel.poke(false.B)
      d.io.fence.poke(false.B)
      d.io.iReq.poke(true.B); d.io.iAccept.poke(false.B)
      d.io.dReq.poke(true.B); d.io.dAccept.poke(false.B)
      d.io.dIsStore.poke(false.B)
      d.io.pageRequest.ready.poke(false.B)
      d.io.pageResponse.valid.poke(false.B)
      d.io.pageResponse.bits.data.poke(0.U)
      d.io.pageResponse.bits.error.poke(false.B)

      // Loaders execute programs in low DDR; DMA drivers use uncached aliases.
      for (hex <- Seq("00000000", "01000000", "01fffffc", "02010000", "1b600000", "3ffffffc",
                      "80000000", "81000000", "9b600000", "bffffffc")) {
        val address = BigInt(hex, 16)
        d.io.iVaddr.poke(address.U); d.io.dVaddr.poke(address.U)
        d.io.iReady.expect(true.B); d.io.iFaults.expect(0.U)
        d.io.iDirectExcp.expect(false.B); d.io.iMat.expect(1.U)
        d.io.dReady.expect(true.B); d.io.dAccessFault.expect(false.B)
        d.io.dMat.expect((if (address >= BigInt("80000000", 16)) 0 else 1).U)
        d.clock.step()
      }
      val devices = Seq("02000000", "02004000", "0200bff8", "0200fffc").map(BigInt(_, 16)) ++
        (0 until 16).flatMap(page => Seq(BigInt("1fe00000", 16) + page * 0x10000,
                                       BigInt("1fe0fffc", 16) + page * 0x10000))
      for (address <- devices) {
        d.io.iVaddr.poke(address.U)
        d.io.dVaddr.poke(address.U)
        d.io.iFaults.expect(64.U); d.io.iDirectExcp.expect(true.B)
        d.io.iMat.expect(0.U); d.io.dAccessFault.expect(false.B); d.io.dMat.expect(0.U)
      }
      d.io.iVaddr.poke("h50000000".U)
      d.io.dVaddr.poke("h50000000".U)
      d.io.iFaults.expect(64.U); d.io.dAccessFault.expect(true.B)
    }
  }
}
