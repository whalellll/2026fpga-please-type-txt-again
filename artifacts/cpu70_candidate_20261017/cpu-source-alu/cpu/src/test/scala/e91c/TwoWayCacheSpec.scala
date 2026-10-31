package e91c

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.frontend.Icache
import e91c.mem.Dcache

class TwoWayCacheSpec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "Two-way caches"
  private val base = BigInt("1c000000", 16)
  private def line(word: BigInt): BigInt = (0 until 8).map(i => word << (32*i)).reduce(_ | _)

  it should "retain two same-set instruction lines, replace one and invalidate both" in {
    test(new Icache) { d =>
      d.io.ifuReq.poke(false.B); d.io.ifuVindex.poke(0.U); d.io.ifuPaddr.poke(base.U)
      d.io.ifuUncached.poke(false.B); d.io.invalidate.poke(false.B)
      d.io.axiRdRdy.poke(false.B); d.io.axiRetError.poke(false.B)
      d.io.axiRetValid.poke(false.B); d.io.axiRetLast.poke(false.B); d.io.axiRetData.poke(0.U)
      d.clock.step(2)
      def request(addr: BigInt): Unit = {
        d.io.ifuReq.poke(true.B); d.io.ifuPaddr.poke(addr.U)
        var wait = 0
        while (!d.io.ifuAddrOk.peek().litToBoolean && wait < 400) { d.clock.step(); wait += 1 }
        assert(wait < 400); d.clock.step(); d.io.ifuReq.poke(false.B)
      }
      def miss(addr: BigInt, value: BigInt): Unit = {
        request(addr); d.io.ifuDataOk.expect(false.B); d.clock.step()
        d.io.axiRdReq.expect(true.B); d.io.axiRdAddr.expect(addr.U)
        d.clock.step(3); d.io.axiRdReq.expect(true.B)
        d.io.axiRdRdy.poke(true.B); d.clock.step(); d.io.axiRdRdy.poke(false.B)
        d.io.axiRetValid.poke(true.B); d.io.axiRetData.poke((line(value) & ((BigInt(1)<<128)-1)).U)
        d.clock.step(); d.io.axiRetLast.poke(true.B); d.clock.step()
        d.io.axiRetValid.poke(false.B); d.io.axiRetLast.poke(false.B)
        d.io.ifuDataOk.expect(true.B); d.io.ifuRline.expect(line(value).U); d.clock.step()
      }
      def hit(addr: BigInt, value: BigInt): Unit = {
        request(addr); d.io.ifuDataOk.expect(true.B); d.io.axiRdReq.expect(false.B)
        d.io.ifuRline.expect(line(value).U); d.clock.step()
      }
      miss(base, 0x111); miss(base+4096, 0x222)
      hit(base, 0x111); hit(base+4096, 0x222)
      miss(base+8192, 0x333); hit(base+4096, 0x222); hit(base+8192, 0x333)
      d.io.invalidate.poke(true.B); d.clock.step(); d.io.invalidate.poke(false.B); d.clock.step(2)
      miss(base+4096, 0x444); miss(base+8192, 0x555)
    }
  }

  it should "retain two data lines and write back the dirty replacement with its own tag" in {
    test(new Dcache) { d =>
      d.io.ldReq.poke(false.B); d.io.ldVindex.poke(0.U); d.io.ldPaddr.poke(base.U)
      d.io.ldSize.poke(2.U); d.io.ldOp.poke(0.U); d.io.ldUncached.poke(false.B)
      d.io.ldRobid.poke(1.U); d.io.ldRespReady.poke(true.B); d.io.ldCancel.poke(false.B)
      d.io.ldPairValid.poke(false.B); d.io.ldPairWord.poke(0.U); d.io.ldPairPaddr.poke(0.U)
      d.io.stReq.poke(false.B); d.io.stPaddr.poke(base.U); d.io.stData.poke(0.U)
      d.io.stStrb.poke(15.U); d.io.stSize.poke(2.U); d.io.stUncached.poke(false.B)
      d.io.fenceI.poke(false.B); d.io.axiRdRdy.poke(false.B); d.io.axiRetError.poke(false.B)
      d.io.axiRetValid.poke(false.B); d.io.axiRetLast.poke(false.B); d.io.axiRetData.poke(0.U)
      d.io.axiWrRdy.poke(false.B); d.clock.step(260)
      def until(p: => Boolean): Unit = {
        var n=0; while (!p && n<500) { d.clock.step(); n+=1 }; assert(n<500)
      }
      def request(addr: BigInt): Unit = {
        d.io.ldPaddr.poke(addr.U); d.io.ldReq.poke(true.B)
        until(d.io.ldAddrOk.peek().litToBoolean); d.clock.step(); d.io.ldReq.poke(false.B)
      }
      def fill(value: BigInt): Unit = {
        until(d.io.axiRdReq.peek().litToBoolean)
        d.io.axiRdRdy.poke(true.B); d.clock.step(); d.io.axiRdRdy.poke(false.B)
        d.io.axiRetData.poke((line(value) & ((BigInt(1)<<128)-1)).U)
        d.io.axiRetValid.poke(true.B); d.clock.step(); d.io.axiRetLast.poke(true.B)
        d.io.ldMshrDataOk.expect(true.B); d.io.ldMshrRdata.expect(value.U)
        d.clock.step(); d.io.axiRetValid.poke(false.B); d.io.axiRetLast.poke(false.B)
        d.clock.step(4)
      }
      def hit(addr: BigInt, value: BigInt): Unit = {
        request(addr); d.io.ldDataOk.expect(true.B); d.io.ldRdata.expect(value.U)
        d.io.ldMiss.expect(false.B); d.clock.step(2)
      }
      request(base); fill(0x111); request(base+4096); fill(0x222)
      hit(base, 0x111); hit(base+4096, 0x222)
      d.io.stReq.poke(true.B); d.io.stPaddr.poke(base.U); d.io.stData.poke(0xabc.U)
      until(d.io.stAddrOk.peek().litToBoolean); d.clock.step(); d.io.stReq.poke(false.B)
      d.io.stDone.expect(true.B); d.clock.step(2); hit(base, 0xabc)
      request(base+8192)
      until(d.io.axiWrReq.peek().litToBoolean)
      d.io.axiWrAddr.expect(base.U); d.io.axiWrData.expect(((line(0x111) & ((BigInt(1)<<128)-1) & ~BigInt("ffffffff",16)) | 0xabc).U)
      d.clock.step(3); d.io.axiWrAddr.expect(base.U)
      d.io.axiWrRdy.poke(true.B); d.clock.step(2); d.io.axiWrRdy.poke(false.B)
      fill(0x333); hit(base+4096, 0x222); hit(base+8192, 0x333)
      d.io.fenceI.poke(true.B); d.clock.step(); d.io.fenceI.poke(false.B)
      var n=0
      while (!d.io.fullFlushDone.peek().litToBoolean && n<2000) { d.clock.step(); n+=1 }
      assert(n<2000); d.clock.step(2)
      request(base+4096); d.io.ldDataOk.expect(false.B); fill(0x444)
      request(base+8192); d.io.ldDataOk.expect(false.B); fill(0x555)
      // Store miss plus same-line byte merges while the AXI request is stalled.
      def store(addr: BigInt, value: BigInt, mask: Int): Unit = {
        d.io.stPaddr.poke(addr.U); d.io.stData.poke(value.U); d.io.stStrb.poke(mask.U)
        d.io.stReq.poke(true.B); until(d.io.stAddrOk.peek().litToBoolean)
        d.clock.step(); d.io.stReq.poke(false.B)
        until(d.io.stDone.peek().litToBoolean); d.clock.step(2)
      }
      store(base+12288+4,BigInt("abcdef01",16),15)
      store(base+12288+4,BigInt("00123400",16),6)
      store(base+12288+20,BigInt("99000000",16),8)
      until(d.io.axiRdReq.peek().litToBoolean)
      d.io.axiRdRdy.poke(true.B); d.clock.step(); d.io.axiRdRdy.poke(false.B)
      d.io.axiRetData.poke((line(0x555) & ((BigInt(1)<<128)-1)).U)
      d.io.axiRetValid.poke(true.B); d.clock.step(); d.io.axiRetLast.poke(true.B); d.clock.step()
      d.io.axiRetValid.poke(false.B); d.io.axiRetLast.poke(false.B); d.clock.step(4)
      hit(base+12288+4,BigInt("ab123401",16))
      hit(base+12288+20,BigInt("99000555",16))
      hit(base+12288+8,0x555)
    }
  }
}
