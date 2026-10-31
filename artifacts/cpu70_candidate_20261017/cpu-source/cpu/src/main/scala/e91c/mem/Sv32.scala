package e91c.mem

import chisel3._
import chisel3.util._
import e91c.config.Params.TLB_ENTRIES

class TranslationRequest extends Bundle {
  val virtualAddress = UInt(32.W)
  val access = UInt(2.W) // 0 instruction, 1 load, 2 store/AMO
  val privilege = UInt(2.W) // effective privilege, including MPRV for data
  val satp = UInt(32.W)
  val sum = Bool()
  val mxr = Bool()
  val identity = UInt(16.W)
}
class TranslationResponse extends Bundle {
  val virtualAddress = UInt(32.W)
  val physicalAddress = UInt(34.W)
  val identity = UInt(16.W)
  val pageFault = Bool()
  val accessFault = Bool()
}
class PageTableReadResponse extends Bundle {
  val data = UInt(32.W)
  val error = Bool()
}

/** Sv32 with a small fully associative TLB and software-managed A/D bits
  * (Svade). Page-table reads must be coherent with the CPU data cache.
  * A cancelled outstanding read is drained before accepting a new owner.
  */
class Sv32(val entries: Int = TLB_ENTRIES, val fastHit: Boolean = false) extends Module {
  require(entries > 0 && isPow2(entries))
  val io = IO(new Bundle {
    val request = Flipped(Decoupled(new TranslationRequest))
    val response = Decoupled(new TranslationResponse)
    val invalidate = Input(Bool()) // conservative all-ASID/all-VA SFENCE.VMA
    val cancel = Input(Bool())
    val memoryRequest = Decoupled(UInt(34.W))
    val memoryResponse = Flipped(Decoupled(new PageTableReadResponse))
  })
  val sIdle :: sLookup :: sRequest :: sWait :: sResponse :: Nil = Enum(5)
  val state = RegInit(sIdle)
  val request = Reg(new TranslationRequest)
  val response = Reg(new TranslationResponse)
  val pteAddress = Reg(UInt(34.W))
  val levelOne = Reg(Bool())
  val inheritedGlobal = RegInit(false.B)
  val killed = RegInit(false.B)
  val valid = RegInit(VecInit(Seq.fill(entries)(false.B)))
  val vpn = Reg(Vec(entries, UInt(20.W)))
  val ppn = Reg(Vec(entries, UInt(22.W)))
  val root = Reg(Vec(entries, UInt(22.W)))
  val asid = Reg(Vec(entries, UInt(9.W)))
  val global = Reg(Vec(entries, Bool()))
  val superpage = Reg(Vec(entries, Bool()))
  val flags = Reg(Vec(entries, UInt(8.W)))
  val victim = RegInit(0.U(log2Ceil(entries).max(1).W))
  val kill = io.cancel || io.invalidate

  def permitted(pteFlags: UInt, req: TranslationRequest = request): Bool = {
    val user = pteFlags(4)
    val privilegeOk = Mux(req.privilege === 0.U, user,
      !user || (req.access =/= 0.U && req.sum))
    val accessOk = Mux(req.access === 0.U, pteFlags(3),
      Mux(req.access === 2.U, pteFlags(2), pteFlags(1) || (req.mxr && pteFlags(3))))
    privilegeOk && accessOk && pteFlags(6) && (req.access =/= 2.U || pteFlags(7))
  }
  def address(physicalPage: UInt, large: Bool): UInt =
    Mux(large, Cat(physicalPage(21,10), request.virtualAddress(21,0)),
      Cat(physicalPage, request.virtualAddress(11,0)))
  def complete(pa: UInt, pageError: Bool, busError: Bool): Unit = {
    response.virtualAddress := request.virtualAddress
    response.physicalAddress := pa
    response.identity := request.identity
    response.pageFault := pageError
    response.accessFault := busError
    state := sResponse
  }

  val hits = VecInit((0 until entries).map(i => valid(i) &&
    root(i) === request.satp(21,0) && (global(i) || asid(i) === request.satp(30,22)) &&
    Mux(superpage(i), vpn(i)(19,10) === request.virtualAddress(31,22),
      vpn(i) === request.virtualAddress(31,12))))
  val hitIndex = PriorityEncoder(hits)
  // Optional instruction-side combinational hit port. A hit is consumed only
  // with its response; a blocked PF keeps the request stable. Misses retain
  // the existing captured-request walker and cancellation/drain protocol.
  val fastResponse = WireDefault(false.B)
  val fastBits = WireDefault(0.U.asTypeOf(new TranslationResponse))
  if (fastHit) {
    val incoming = io.request.bits
    val incomingHits = VecInit((0 until entries).map(i => valid(i) &&
      root(i) === incoming.satp(21,0) && (global(i) || asid(i) === incoming.satp(30,22)) &&
      Mux(superpage(i),vpn(i)(19,10) === incoming.virtualAddress(31,22),
        vpn(i) === incoming.virtualAddress(31,12))))
    val index = PriorityEncoder(incomingHits)
    fastResponse := state===sIdle && io.request.valid && incomingHits.asUInt.orR &&
      incoming.satp(31) && incoming.privilege=/=3.U && !kill
    fastBits.virtualAddress := incoming.virtualAddress
    fastBits.identity := incoming.identity
    fastBits.physicalAddress := Mux(superpage(index),
      Cat(ppn(index)(21,10),incoming.virtualAddress(21,0)),
      Cat(ppn(index),incoming.virtualAddress(11,0)))
    fastBits.pageFault := !permitted(flags(index),incoming)
    fastBits.accessFault := false.B
  }
  io.request.ready := state === sIdle && !kill && (!fastResponse || io.response.ready)
  io.response.valid := (state === sResponse || fastResponse) && !kill
  io.response.bits := response
  when(fastResponse) { io.response.bits := fastBits }
  io.memoryRequest.valid := state === sRequest && !kill
  io.memoryRequest.bits := pteAddress
  io.memoryResponse.ready := state === sWait

  switch(state) {
    is(sIdle) {
      when(io.request.fire && !fastResponse) { request := io.request.bits; killed := false.B; state := sLookup }
    }
    is(sLookup) {
      when(!request.satp(31) || request.privilege === 3.U) {
        complete(Cat(0.U(2.W),request.virtualAddress), false.B, false.B)
      }.elsewhen(hits.asUInt.orR) {
        complete(address(ppn(hitIndex),superpage(hitIndex)), !permitted(flags(hitIndex)), false.B)
      }.otherwise {
        pteAddress := Cat(request.satp(21,0),0.U(12.W)) + Cat(request.virtualAddress(31,22),0.U(2.W))
        levelOne := true.B
        inheritedGlobal := false.B
        state := sRequest
      }
    }
    is(sRequest) { when(io.memoryRequest.fire) { state := sWait } }
    is(sWait) {
      when(io.memoryResponse.fire) {
        val pte = io.memoryResponse.bits.data
        val leaf = pte(1) || pte(3)
        val invalid = !pte(0) || (pte(2) && !pte(1))
        when(killed || kill) { state := sIdle }
          .elsewhen(io.memoryResponse.bits.error) { complete(0.U, false.B, true.B) }
          .elsewhen(invalid) { complete(0.U, true.B, false.B) }
          .elsewhen(leaf) {
            val bad = !permitted(pte(7,0)) || (levelOne && pte(19,10).orR)
            complete(address(pte(31,10),levelOne),bad,false.B)
            when(!bad) {
              valid(victim) := true.B
              vpn(victim) := request.virtualAddress(31,12)
              ppn(victim) := pte(31,10)
              root(victim) := request.satp(21,0)
              asid(victim) := request.satp(30,22)
              global(victim) := inheritedGlobal || pte(5)
              superpage(victim) := levelOne
              flags(victim) := pte(7,0)
              victim := Mux(victim === (entries-1).U,0.U,victim+1.U)
            }
          }.elsewhen(!levelOne || pte(7) || pte(6) || pte(4)) {
            complete(0.U,true.B,false.B)
          }.otherwise {
            pteAddress := Cat(pte(31,10),0.U(12.W)) + Cat(request.virtualAddress(21,12),0.U(2.W))
            inheritedGlobal := inheritedGlobal || pte(5)
            levelOne := false.B
            state := sRequest
          }
      }
    }
    is(sResponse) { when(io.response.fire) { state := sIdle } }
  }
  when(io.invalidate) { valid.foreach(_ := false.B) }
  when(kill) {
    when(state === sWait && !io.memoryResponse.fire) { killed := true.B }
      .otherwise { state := sIdle; killed := false.B }
  }
}
