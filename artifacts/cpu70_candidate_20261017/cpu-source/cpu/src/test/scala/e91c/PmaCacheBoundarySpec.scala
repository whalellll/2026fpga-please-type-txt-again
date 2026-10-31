package e91c

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import e91c.mem.{Dcache, PhysicalMemoryAttributes}

class PmaDcacheHarness extends Module {
  val io = IO(new Bundle {
    val request = Input(Bool())
    val store = Input(Bool())
    val paddr = Input(UInt(32.W))
    val writeData = Input(UInt(32.W))
    val mat = Output(UInt(2.W))
    val addrOk = Output(Bool())
    val loadDataOk = Output(Bool())
    val loadData = Output(UInt(32.W))
    val loadMiss = Output(Bool())
    val mshrDataOk = Output(Bool())
    val storeDone = Output(Bool())
    val quiescent = Output(Bool())
    val busReadReq = Output(Bool())
    val busReadType = Output(UInt(3.W))
    val busReadAddr = Output(UInt(32.W))
    val busReadReady = Input(Bool())
    val busReturnValid = Input(Bool())
    val busReturnError = Input(Bool())
    val busReturnData = Input(UInt(128.W))
    val busWriteReq = Output(Bool())
    val busWriteType = Output(UInt(3.W))
    val busWriteAddr = Output(UInt(32.W))
    val busWriteReady = Input(Bool())
  })

  val attributes = Module(new PhysicalMemoryAttributes)
  attributes.io.iPaddr := io.paddr
  attributes.io.iDirectPaddr := io.paddr
  attributes.io.dPaddr := io.paddr
  io.mat := attributes.io.dMat

  val cache = Module(new Dcache)
  val uncached = attributes.io.dMat =/= PhysicalMemoryAttributes.MatCacheable
  cache.io.ldReq := io.request && !io.store
  cache.io.ldVindex := io.paddr(11, 5)
  cache.io.ldPaddr := io.paddr
  cache.io.ldSize := 2.U
  cache.io.ldOp := 0.U
  cache.io.ldUncached := uncached
  cache.io.ldRobid := 1.U
  cache.io.ldRespReady := true.B
  cache.io.ldCancel := false.B
  cache.io.ldPairValid := false.B
  cache.io.ldPairWord := 0.U
  cache.io.ldPairPaddr := 0.U
  cache.io.stReq := io.request && io.store
  cache.io.stPaddr := io.paddr
  cache.io.stData := io.writeData
  cache.io.stStrb := "hf".U
  cache.io.stSize := 2.U
  cache.io.stUncached := uncached
  cache.io.fenceI := false.B
  cache.io.axiRdRdy := io.busReadReady
  cache.io.axiRetValid := io.busReturnValid
  cache.io.axiRetLast := io.busReturnValid
  cache.io.axiRetError := io.busReturnError
  cache.io.axiRetData := io.busReturnData
  cache.io.axiWrRdy := io.busWriteReady

  io.addrOk := Mux(io.store, cache.io.stAddrOk, cache.io.ldAddrOk)
  io.loadDataOk := cache.io.ldDataOk
  io.loadData := cache.io.ldRdata
  io.loadMiss := cache.io.ldMiss
  io.mshrDataOk := cache.io.ldMshrDataOk
  io.storeDone := cache.io.stDone
  io.quiescent := cache.io.quiescent
  io.busReadReq := cache.io.axiRdReq
  io.busReadType := cache.io.axiRdType
  io.busReadAddr := cache.io.axiRdAddr
  io.busWriteReq := cache.io.axiWrReq
  io.busWriteType := cache.io.axiWrType
  io.busWriteAddr := cache.io.axiWrAddr
}

class PmaCacheBoundarySpec extends AnyFlatSpec with ChiselScalatestTester {
  private def initialize(d: PmaDcacheHarness): Unit = {
    d.io.request.poke(false.B)
    d.io.store.poke(false.B)
    d.io.paddr.poke(0.U)
    d.io.writeData.poke(0.U)
    d.io.busReadReady.poke(false.B)
    d.io.busReturnValid.poke(false.B)
    d.io.busReturnError.poke(false.B)
    d.io.busReturnData.poke(0.U)
    d.io.busWriteReady.poke(false.B)
    d.clock.step(260)
  }

  behavior of "PMA at the D-cache request boundary"
  it should "route a peripheral load as one uncached transfer without an MSHR allocation" in {
    test(new PmaDcacheHarness) { d =>
      initialize(d)
      d.io.paddr.poke("h1fe02000".U)
      d.io.mat.expect(0.U)
      d.io.request.poke(true.B)
      d.io.addrOk.expect(true.B)
      d.clock.step()
      d.io.request.poke(false.B)
      d.io.loadMiss.expect(false.B)
      d.io.mshrDataOk.expect(false.B)
      d.clock.step()
      d.io.busReadReq.expect(true.B)
      d.io.busReadType.expect(2.U)
      d.io.busReadAddr.expect("h1fe02000".U)
      d.io.loadMiss.expect(false.B)
      d.io.busReadReady.poke(true.B)
      d.clock.step()
      d.io.busReadReady.poke(false.B)
      d.io.busReturnData.poke("h000000000000000000000000deadbeef".U)
      d.io.busReturnValid.poke(true.B)
      d.clock.step()
      d.io.busReturnValid.poke(false.B)
      d.io.loadDataOk.expect(true.B)
      d.io.loadData.expect("hdeadbeef".U)
      d.io.loadMiss.expect(false.B)
      d.io.mshrDataOk.expect(false.B)
      d.clock.step()
      d.io.quiescent.expect(true.B)
    }
  }

  it should "route a committed peripheral store only through the uncached write channel" in {
    test(new PmaDcacheHarness) { d =>
      initialize(d)
      d.io.paddr.poke("h1fe20ffc".U)
      d.io.writeData.poke("h12345678".U)
      d.io.store.poke(true.B)
      d.io.request.poke(true.B)
      d.io.mat.expect(0.U)
      d.io.addrOk.expect(true.B)
      d.clock.step()
      d.io.request.poke(false.B)
      d.clock.step()
      d.io.busWriteReq.expect(true.B)
      d.io.busWriteType.expect(2.U)
      d.io.busWriteAddr.expect("h1fe20ffc".U)
      d.io.busWriteReady.poke(true.B)
      d.io.storeDone.expect(true.B)
      d.clock.step()
      d.io.busWriteReady.poke(false.B)
      d.io.busWriteReq.expect(false.B)
      d.io.quiescent.expect(true.B)
    }
  }
}
