package e91c

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.mem.Sv32

class Sv32Spec extends AnyFlatSpec with ChiselScalatestTester {
  private def init(d: Sv32): Unit = {
    d.io.cancel.poke(false.B); d.io.invalidate.poke(false.B)
    d.io.request.valid.poke(false.B); d.io.response.ready.poke(false.B)
    d.io.memoryRequest.ready.poke(true.B); d.io.memoryResponse.valid.poke(false.B)
    d.io.memoryResponse.bits.data.poke(0.U); d.io.memoryResponse.bits.error.poke(false.B)
    d.io.request.bits.virtualAddress.poke(0.U); d.io.request.bits.access.poke(1.U)
    d.io.request.bits.privilege.poke(1.U); d.io.request.bits.satp.poke(0.U)
    d.io.request.bits.sum.poke(false.B); d.io.request.bits.mxr.poke(false.B)
    d.io.request.bits.identity.poke(17.U)
    d.clock.step()
  }
  private def translate(d: Sv32, va: BigInt, satp: BigInt, access: Int,
      privilege: Int, pages: Map[BigInt,BigInt] = Map.empty,
      mxr: Boolean = false, sum: Boolean = false, busError: Boolean = false): (BigInt,Boolean,Boolean,Int) = {
    d.io.request.ready.expect(true.B)
    d.io.request.bits.virtualAddress.poke(va.U); d.io.request.bits.satp.poke(satp.U)
    d.io.request.bits.access.poke(access.U); d.io.request.bits.privilege.poke(privilege.U)
    d.io.request.bits.mxr.poke(mxr.B); d.io.request.bits.sum.poke(sum.B)
    d.io.request.valid.poke(true.B); d.clock.step(); d.io.request.valid.poke(false.B)
    var steps = 0; var reads = 0
    while (!d.io.response.valid.peek().litToBoolean && steps < 24) {
      if (d.io.memoryRequest.valid.peek().litToBoolean) {
        val a = d.io.memoryRequest.bits.peek().litValue
        assert(busError || pages.contains(a), s"unexpected page-table read ${a.toString(16)}")
        d.clock.step()
        d.io.memoryResponse.bits.data.poke(pages.getOrElse(a,BigInt(0)).U)
        d.io.memoryResponse.bits.error.poke(busError.B)
        d.io.memoryResponse.valid.poke(true.B)
        d.io.memoryResponse.ready.expect(true.B)
        d.clock.step(); d.io.memoryResponse.valid.poke(false.B)
        reads += 1
      } else d.clock.step()
      steps += 1
    }
    d.io.response.valid.expect(true.B)
    d.io.response.bits.identity.expect(17.U)
    d.io.response.bits.virtualAddress.expect(va.U)
    val result = (d.io.response.bits.physicalAddress.peek().litValue,
      d.io.response.bits.pageFault.peek().litToBoolean,
      d.io.response.bits.accessFault.peek().litToBoolean,reads)
    d.clock.step(2); d.io.response.valid.expect(true.B)
    d.io.response.ready.poke(true.B); d.clock.step(); d.io.response.ready.poke(false.B)
    result
  }
  behavior of "Sv32"
  it should "translate 4 KiB pages, cache them, and honor SFENCE invalidation" in {
    test(new Sv32) { d =>
      init(d)
      val satp = BigInt("80080000",16)
      val va = BigInt("40001234",16)
      val pages = Map(BigInt("80000400",16) -> ((BigInt("80001",16)<<10)|1),
        BigInt("80001004",16) -> ((BigInt("80002",16)<<10)|0xc7))
      assert(translate(d,va,satp,1,1,pages) == (BigInt("80002234",16),false,false,2))
      assert(translate(d,va,satp,2,1) == (BigInt("80002234",16),false,false,0))
      d.io.invalidate.poke(true.B); d.clock.step(); d.io.invalidate.poke(false.B)
      assert(translate(d,va,satp,1,1,pages)._4 == 2)
      assert(translate(d,va,satp,1,3) == (va,false,false,0))
    }
  }
  it should "recheck MXR and SUM on hits and reject user-page instruction fetch in supervisor mode" in {
    test(new Sv32) { d =>
      init(d)
      val satp = BigInt("80080000",16); val va = BigInt("40000020",16)
      val rootAddress = BigInt("80000400",16)
      val executePage = Map(rootAddress -> ((BigInt("80000",16)<<10)|0x49))
      assert(translate(d,va,satp,1,1,executePage)._2)
      assert(!translate(d,va,satp,1,1,executePage,mxr=true)._2)
      assert(translate(d,va,satp,1,1)._2)
      d.io.invalidate.poke(true.B); d.clock.step(); d.io.invalidate.poke(false.B)
      val userPage = Map(rootAddress -> ((BigInt("80000",16)<<10)|0xdf))
      assert(!translate(d,va,satp,1,0,userPage)._2)
      assert(translate(d,va,satp,1,1)._2)
      assert(!translate(d,va,satp,1,1,sum=true)._2)
      assert(translate(d,va,satp,0,1,sum=true)._2)
    }
  }
  it should "distinguish page faults from bus faults and enforce superpage alignment and Svade" in {
    test(new Sv32) { d =>
      init(d)
      val satp=BigInt("80080000",16); val va=BigInt("40000000",16)
      val address=BigInt("80000400",16)
      assert(translate(d,va,satp,1,1,Map(address->BigInt(0)))._2)
      assert(translate(d,va,satp,1,1,Map(address->((BigInt("80001",16)<<10)|0xc7)))._2)
      assert(translate(d,va,satp,2,1,Map(address->((BigInt("80000",16)<<10)|0x47)))._2)
      val fault=translate(d,va,satp,1,1,busError=true)
      assert(!fault._2 && fault._3)
    }
  }
  it should "drain an old walk after cancellation without filling a TLB or returning its identity" in {
    test(new Sv32) { d =>
      init(d)
      d.io.request.bits.virtualAddress.poke("h40000000".U)
      d.io.request.bits.satp.poke("h80080000".U)
      d.io.request.valid.poke(true.B); d.clock.step(); d.io.request.valid.poke(false.B)
      d.clock.step(); d.io.memoryRequest.valid.expect(true.B)
      d.clock.step(); d.io.cancel.poke(true.B); d.clock.step(); d.io.cancel.poke(false.B)
      d.io.request.ready.expect(false.B)
      d.io.memoryResponse.valid.poke(true.B)
      d.io.memoryResponse.bits.data.poke(((BigInt("80000",16)<<10)|0xc7).U)
      d.clock.step(); d.io.memoryResponse.valid.poke(false.B)
      d.io.response.valid.expect(false.B); d.io.request.ready.expect(true.B)
      val pages=Map(BigInt("80000400",16)->((BigInt("80000",16)<<10)|0xc7))
      assert(translate(d,BigInt("40000000",16),BigInt("80080000",16),1,1,pages)._4==1)
    }
  }
}
