package e91c

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.mem.{PhysicalMemoryAttributes, PmaMmu}

class PhysicalMemoryAttributesSpec extends AnyFlatSpec with ChiselScalatestTester {
  // Independent byte ranges from the performance_soc wrapper/crossbar map.
  private val peripheralWindows = Seq(
    (BigInt("02000000", 16), BigInt("00010000", 16)),
    (BigInt("1fe00000", 16), BigInt("00100000", 16)))

  private def isPeripheral(address: BigInt): Boolean =
    peripheralWindows.exists { case (start, size) => address >= start && address < start + size }

  behavior of "PhysicalMemoryAttributes"
  it should "classify peripheral, boot BRAM and uncached DDR alias boundaries" in {
    test(new PhysicalMemoryAttributes) { d =>
      def check(address: BigInt): Unit = {
        d.io.iPaddr.poke(address.U)
        d.io.iDirectPaddr.poke(address.U)
        d.io.dPaddr.poke(address.U)
        val peripheral = isPeripheral(address)
        d.io.iMat.expect((if (peripheral) 0 else 1).U)
        d.io.iDirectMat.expect((if (peripheral) 0 else 1).U)
        val ddrAlias = address >= BigInt("80000000", 16) && address < BigInt("c0000000", 16)
        d.io.dMat.expect((if (peripheral || ddrAlias) 0 else 1).U)
        d.io.iPeripheral.expect(peripheral.B)
        d.io.dPeripheral.expect(peripheral.B)
      }
      peripheralWindows.foreach { case (start, size) =>
        Seq(start - 1, start, start + size - 1, start + size).foreach(check)
      }
      // Every 64 KiB subwindow of the current 1 MiB MMIO aperture is device.
      (0 until 16).foreach { page =>
        val start = BigInt("1fe00000", 16) + page * 0x10000
        Seq(start, start + 0xffff).foreach(check)
      }
      // Former hi16 device windows and their boundaries now map to DDR.
      Seq("1fc00000", "1fd00000", "1ff00000", "1d010000", "1d020000", "1d030000").foreach { hex =>
        val start = BigInt(hex, 16)
        Seq(start - 1, start, start + 0xffff, start + 0x10000).foreach(check)
      }
      // Former PLIC/UART boundaries are DDR, not device registers.
      Seq(BigInt("0bffffff", 16), BigInt("0c000000", 16), BigInt("0fffffff", 16),
        BigInt("10000000", 16), BigInt("10000fff", 16), BigInt("10001000", 16)).foreach(check)
      Seq(BigInt("1c017fff", 16), BigInt("1c018000", 16),
        BigInt("1c01bfff", 16), BigInt("1c01c000", 16),
        BigInt("1c000000", 16)).foreach(check)
      Seq(BigInt("7fffffff", 16), BigInt("80000000", 16),
        BigInt("9affffff", 16), BigInt("9b000000", 16),
        BigInt("9bffffff", 16), BigInt("9c000000", 16),
        BigInt("bfffffff", 16), BigInt("c0000000", 16)).foreach(check)
    }
  }
}

class PmaMmuSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def init(d: PmaMmu): Unit = {
    d.io.privilege.poke(3.U); d.io.dataPrivilege.poke(3.U)
    d.io.satp.poke(0.U); d.io.status.poke(0.U)
    d.io.flush.poke(false.B); d.io.instructionCancel.poke(false.B); d.io.fence.poke(false.B)
    d.io.iReq.poke(false.B); d.io.iVaddr.poke(0.U); d.io.iAccept.poke(false.B)
    d.io.dReq.poke(false.B); d.io.dVaddr.poke(0.U); d.io.dAccept.poke(false.B)
    d.io.dIsStore.poke(false.B)
    d.io.pageRequest.ready.poke(false.B); d.io.pageResponse.valid.poke(false.B)
    d.io.pageResponse.bits.data.poke(0.U); d.io.pageResponse.bits.error.poke(false.B)
    d.clock.step()
  }
  behavior of "PmaMmu"
  it should "serve consecutive instruction TLB hits without another page-table read" in {
    test(new PmaMmu) { d =>
      init(d)
      d.io.privilege.poke(1.U); d.io.satp.poke("h80080000".U)
      d.io.iReq.poke(true.B); d.io.iVaddr.poke("h40000000".U)
      d.clock.step(2)
      d.io.pageRequest.valid.expect(true.B)
      d.io.pageRequest.ready.poke(true.B); d.clock.step()
      d.io.pageRequest.ready.poke(false.B)
      d.io.pageResponse.bits.data.poke("h200000cf".U)
      d.io.pageResponse.valid.poke(true.B); d.clock.step()
      d.io.pageResponse.valid.poke(false.B)
      d.io.iReady.expect(true.B); d.io.iPaddr.expect("h80000000".U)
      d.io.iAccept.poke(true.B); d.clock.step()
      for(i <- 1 to 12) {
        d.io.iVaddr.poke((BigInt("40000000",16)+i*16).U)
        d.io.iReady.expect(false.B)
        d.clock.step(2) // captured request -> TLB lookup -> held response
        d.io.iReady.expect(true.B)
        d.io.iPaddr.expect((BigInt("80000000",16)+i*16).U)
        d.io.iFaults.expect(0.U); d.io.pageRequest.valid.expect(false.B)
        d.clock.step() // consume the held response
      }
      // Cached permissions must still be checked for the current privilege.
      d.io.iAccept.poke(false.B); d.io.privilege.poke(0.U)
      d.clock.step(2)
      d.io.iReady.expect(true.B); d.io.iFaults.expect(128.U)
      d.io.iAccept.poke(true.B); d.clock.step()
      d.io.iAccept.poke(false.B); d.io.privilege.poke(1.U)
      d.clock.step(2)
      d.io.iFaults.expect(0.U)
      d.io.iAccept.poke(true.B); d.clock.step()
      d.io.iAccept.poke(false.B); d.io.iReq.poke(false.B)
      d.io.fence.poke(true.B); d.clock.step(); d.io.fence.poke(false.B)
      d.io.iReq.poke(true.B); d.io.iReady.expect(false.B)
      d.clock.step(2); d.io.pageRequest.valid.expect(true.B)
    }
  }
  it should "classify RAM and devices consistently without a workload switch" in {
    test(new PmaMmu) { d =>
      init(d)
      d.io.dReq.poke(true.B); d.io.iReq.poke(true.B)
      for (hex <- Seq("00000000", "01000000", "0c000000", "0ffffffc", "10000000", "10000ffc",
                      "1c000000", "1fc00000", "1fd00000", "1ff00000", "1d010000", "1d020000", "1d030000")) {
        val a = BigInt(hex, 16)
        d.io.dVaddr.poke(a.U); d.io.iVaddr.poke(a.U)
        d.io.dReady.expect(true.B); d.io.dMat.expect(1.U)
        d.io.dAccessFault.expect(false.B); d.io.iFaults.expect(0.U)
      }
      for (a <- Seq(BigInt("02000000", 16), BigInt("0200fffc", 16)) ++
                 (0 until 16).flatMap(page => Seq(BigInt("1fe00000", 16) + page * 0x10000,
                                                BigInt("1fe0fffc", 16) + page * 0x10000))) {
        d.io.dVaddr.poke(a.U); d.io.iVaddr.poke(a.U)
        d.io.dMat.expect(0.U); d.io.iMat.expect(0.U)
        d.io.dAccessFault.expect(false.B); d.io.iFaults.expect(64.U)
      }
      d.io.dVaddr.poke("h1c018000".U); d.io.iVaddr.poke("h1c018000".U)
      d.io.dMat.expect(1.U); d.io.iMat.expect(1.U)
      d.io.dAccessFault.expect(false.B); d.io.iFaults.expect(0.U)
      d.io.dVaddr.poke("h1c01bfff".U); d.io.iVaddr.poke("h1c01bfff".U)
      d.io.dMat.expect(1.U); d.io.iMat.expect(1.U)
      d.io.dVaddr.poke("h1c01c000".U); d.io.iVaddr.poke("h1c01c000".U)
      d.io.dMat.expect(1.U); d.io.iMat.expect(1.U)
      d.io.dVaddr.poke("h9b000000".U); d.io.iVaddr.poke("h9b000000".U)
      d.io.dMat.expect(0.U); d.io.iMat.expect(1.U)
      d.io.dAccessFault.expect(false.B); d.io.iFaults.expect(0.U)
      d.io.dVaddr.poke("h50000000".U); d.io.dAccessFault.expect(true.B)
      d.io.iVaddr.poke("h80000001".U); d.io.iFaults.expect(1.U)
    }
  }
  it should "keep alignment, request acceptance, and direct MAT independent" in {
    test(new PmaMmu) { d =>
      init(d)
      d.io.iVaddr.poke("h1fe80001".U); d.io.dVaddr.poke("h1c018000".U)
      d.io.iReady.expect(false.B); d.io.dReady.expect(false.B)
      d.io.iMisaligned.expect(false.B); d.io.pageRequest.valid.expect(false.B)
      d.io.iDirectOk.expect(true.B); d.io.iDirectMat.expect(0.U)
      d.io.iReq.poke(true.B)
      d.io.iReady.expect(true.B); d.io.iMisaligned.expect(true.B); d.io.iFaults.expect(1.U)
      d.io.iMat.expect(0.U)
      d.io.iVaddr.poke("h1c018000".U)
      d.io.iMisaligned.expect(false.B); d.io.iFaults.expect(0.U)
      d.io.iDirectMat.expect(1.U); d.io.iMat.expect(1.U)
    }
  }
  it should "classify the translated PA for DDR, peripheral and boot BRAM mappings" in {
    test(new PmaMmu) { d =>
      init(d)
      d.io.privilege.poke(1.U); d.io.dataPrivilege.poke(1.U)
      d.io.satp.poke("h80080000".U)

      def rootLeafPte(target: BigInt): BigInt =
        (((target & BigInt("ffc00000", 16)) >> 12) << 10) | 0xcf

      def invalidate(): Unit = {
        d.io.fence.poke(true.B); d.clock.step(); d.io.fence.poke(false.B)
      }

      def translateData(target: BigInt, expectedMat: Int): Unit = {
        val virtual = BigInt("40000000", 16) | (target & BigInt("003fffff", 16))
        d.io.dVaddr.poke(virtual.U); d.io.dReq.poke(true.B)
        d.clock.step(2)
        d.io.pageRequest.valid.expect(true.B)
        d.io.pageRequest.ready.poke(true.B); d.clock.step()
        d.io.pageRequest.ready.poke(false.B)
        d.io.pageResponse.bits.data.poke(rootLeafPte(target).U)
        d.io.pageResponse.bits.error.poke(false.B)
        d.io.pageResponse.valid.poke(true.B); d.clock.step()
        d.io.pageResponse.valid.poke(false.B)
        d.io.dReady.expect(true.B); d.io.dPaddr.expect(target.U)
        d.io.dMat.expect(expectedMat.U)
        d.io.dPageFault.expect(false.B); d.io.dAccessFault.expect(false.B)
        d.io.dAccept.poke(true.B); d.clock.step()
        d.io.dAccept.poke(false.B); d.io.dReq.poke(false.B)
        invalidate()
      }

      def translateInstruction(target: BigInt, expectedMat: Int, expectedFaults: Int): Unit = {
        val virtual = BigInt("40000000", 16) | (target & BigInt("003fffff", 16))
        d.io.iVaddr.poke(virtual.U); d.io.iReq.poke(true.B)
        d.clock.step(2)
        d.io.pageRequest.valid.expect(true.B)
        d.io.pageRequest.ready.poke(true.B); d.clock.step()
        d.io.pageRequest.ready.poke(false.B)
        d.io.pageResponse.bits.data.poke(rootLeafPte(target).U)
        d.io.pageResponse.bits.error.poke(false.B)
        d.io.pageResponse.valid.poke(true.B); d.clock.step()
        d.io.pageResponse.valid.poke(false.B)
        d.io.iReady.expect(true.B); d.io.iPaddr.expect(target.U)
        d.io.iMat.expect(expectedMat.U); d.io.iFaults.expect(expectedFaults.U)
        d.io.iAccept.poke(true.B); d.clock.step()
        d.io.iAccept.poke(false.B); d.io.iReq.poke(false.B)
        invalidate()
      }

      for (hex <- Seq("0c001000", "10000000", "1fc00000", "1fd00000", "1ff00000",
                      "1d010000", "1d020000", "1d030000")) {
        translateData(BigInt(hex, 16), 1)
        translateInstruction(BigInt(hex, 16), 1, 0)
      }
      translateData(BigInt("02004000", 16), 0)
      translateInstruction(BigInt("02004000", 16), 0, 64)
      translateData(BigInt("1fe20000", 16), 0)
      translateInstruction(BigInt("1feffffc", 16), 0, 64)
      translateData(BigInt("80004000", 16), 0)
      translateData(BigInt("1fe80000", 16), 0)
      translateData(BigInt("1c018000", 16), 1)
      translateInstruction(BigInt("1c018000", 16), 1, 0)
      translateInstruction(BigInt("1fe80000", 16), 0, 64)
    }
  }
  it should "give page faults priority over physical access classification" in {
    test(new PmaMmu) { d =>
      init(d)
      d.io.privilege.poke(1.U); d.io.dataPrivilege.poke(1.U)
      d.io.satp.poke("h80080000".U)
      d.io.dReq.poke(true.B); d.io.dVaddr.poke("h40000000".U)
      d.clock.step(2)
      d.io.pageRequest.ready.poke(true.B); d.clock.step()
      d.io.pageRequest.ready.poke(false.B)
      d.io.pageResponse.bits.data.poke(0.U)
      d.io.pageResponse.valid.poke(true.B); d.clock.step()
      d.io.pageResponse.valid.poke(false.B)
      d.io.dReady.expect(true.B); d.io.dPageFault.expect(true.B)
      d.io.dAccessFault.expect(false.B)
    }
  }
  it should "drain a cancelled instruction walk before serving a data walk" in {
    test(new PmaMmu) { d =>
      init(d)
      d.io.privilege.poke(1.U); d.io.dataPrivilege.poke(1.U)
      d.io.satp.poke("h80080000".U)
      d.io.iReq.poke(true.B); d.io.iVaddr.poke("h40000000".U)
      d.clock.step(2)
      d.io.pageRequest.valid.expect(true.B)
      d.io.pageRequest.bits.expect("h80000400".U)
      d.io.pageRequest.ready.poke(true.B); d.clock.step()
      d.io.pageRequest.ready.poke(false.B)
      d.io.instructionCancel.poke(true.B); d.io.iReq.poke(false.B)
      d.io.dReq.poke(true.B); d.io.dVaddr.poke("h40400020".U)
      d.clock.step(); d.io.instructionCancel.poke(false.B); d.clock.step(3)
      d.io.pageRequest.valid.expect(false.B)
      d.io.pageResponse.bits.data.poke("h200000cf".U)
      d.io.pageResponse.valid.poke(true.B); d.io.pageResponse.ready.expect(true.B)
      d.clock.step(); d.io.pageResponse.valid.poke(false.B)
      d.io.dReady.expect(false.B); d.io.iReady.expect(false.B)
      d.clock.step(2)
      d.io.pageRequest.valid.expect(true.B)
      d.io.pageRequest.bits.expect("h80000404".U)
      d.io.pageRequest.ready.poke(true.B); d.clock.step()
      d.io.pageRequest.ready.poke(false.B)
      d.io.pageResponse.bits.data.poke("h201000c7".U)
      d.io.pageResponse.valid.poke(true.B); d.clock.step()
      d.io.pageResponse.valid.poke(false.B)
      d.io.dReady.expect(true.B); d.io.dPaddr.expect("h80400020".U)
      d.io.dPageFault.expect(false.B); d.io.dAccessFault.expect(false.B)
      d.clock.step(3); d.io.dReady.expect(true.B)
      d.io.dAccept.poke(true.B); d.clock.step()
      d.io.dAccept.poke(false.B); d.io.dReq.poke(false.B)
      d.io.dReady.expect(false.B)
    }
  }
  it should "not allocate a new instruction walk in its cancellation cycle" in {
    test(new PmaMmu) { d =>
      init(d)
      d.io.privilege.poke(1.U); d.io.dataPrivilege.poke(1.U)
      d.io.satp.poke("h80080000".U)
      d.io.iReq.poke(true.B); d.io.iVaddr.poke("h40000000".U)
      d.io.instructionCancel.poke(true.B)
      d.io.pageRequest.ready.poke(true.B)
      d.clock.step(4)
      d.io.pageRequest.valid.expect(false.B)
      d.io.iReady.expect(false.B)

      d.io.instructionCancel.poke(false.B)
      d.clock.step(2)
      d.io.pageRequest.valid.expect(true.B)
      d.io.pageRequest.bits.expect("h80000400".U)
    }
  }
}
