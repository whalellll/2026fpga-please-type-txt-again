package e91c.mem

import chisel3._
import chisel3.util._
import e91c.config.Params.EXCP_NUM
import e91c.config.Excp

object PhysicalMap {
  // performance_soc loads/executes programs in low DDR. Device windows remain
  // non-executable, even though they share that low physical address range.
  // Preserve the existing high RAM range for standalone CPU test platforms.
  def ram(address: UInt): Bool = address(31) ||
    (address(31, 30) === 0.U && !device(address))
  def device(address: UInt): Bool =
    PhysicalMemoryAttributes.isPeripheral(address)
}

/** Single elaboration-time source for the SoC MAT address map.
  *
  * MAT only describes cacheability/ordering. PhysicalMap remains the access
  * permission map, so page/access faults are resolved independently. The full
  * 128 KiB boot BRAM is ordinary cacheable RAM; DMA uses high DDR aliases.
  */
object PhysicalMemoryAttributes {
  val MatDevice = "b00".U(2.W)
  val MatCacheable = "b01".U(2.W)

  // Current performance_soc map: private CLINT plus the whole SoC MMIO
  // aperture. Former standalone PLIC/UART/hi16 windows are ordinary DDR.
  def isPeripheral(address: UInt): Bool =
    address(31, 16) === "h0200".U(16.W) || address(31, 20) === "h1fe".U(12.W)

  def instructionMat(address: UInt): UInt =
    Mux(isPeripheral(address), MatDevice, MatCacheable)

  def dataMat(address: UInt): UInt =
    Mux(isPeripheral(address) ||
      address(31, 30) === 2.U, MatDevice, MatCacheable)
}

/** Stateless three-port physical-address classifier. The ports are independent
  * combinational logic; there is no I/D arbitration or ready path here.
  */
class PhysicalMemoryAttributes extends Module {
  val io = IO(new Bundle {
    val iPaddr = Input(UInt(32.W))
    val iDirectPaddr = Input(UInt(32.W))
    val dPaddr = Input(UInt(32.W))
    val iMat = Output(UInt(2.W))
    val iDirectMat = Output(UInt(2.W))
    val dMat = Output(UInt(2.W))
    val iPeripheral = Output(Bool())
    val dPeripheral = Output(Bool())
  })

  io.iPeripheral := PhysicalMemoryAttributes.isPeripheral(io.iPaddr)
  io.dPeripheral := PhysicalMemoryAttributes.isPeripheral(io.dPaddr)
  io.iMat := Mux(io.iPeripheral, PhysicalMemoryAttributes.MatDevice,
    PhysicalMemoryAttributes.MatCacheable)
  io.iDirectMat := PhysicalMemoryAttributes.instructionMat(io.iDirectPaddr)
  io.dMat := PhysicalMemoryAttributes.dataMat(io.dPaddr)
}

/** Request/accept adapters around independent instruction/data translations.
  * Translation/permissions finish first; PhysicalMemoryAttributes then classifies
  * the resulting PA before a request can enter an I/D cache boundary.
  */
class PmaMmu extends Module {
  val io = IO(new Bundle {
    val privilege=Input(UInt(2.W)); val dataPrivilege=Input(UInt(2.W))
    val satp=Input(UInt(32.W)); val status=Input(UInt(32.W))
    val flush=Input(Bool()); val instructionCancel=Input(Bool()); val fence=Input(Bool())
    val iReq=Input(Bool()); val iVaddr=Input(UInt(32.W)); val iAccept=Input(Bool())
    val iReady=Output(Bool()); val iPaddr=Output(UInt(32.W)); val iMat=Output(UInt(2.W))
    val iMisaligned=Output(Bool()); val iFaults=Output(UInt(EXCP_NUM.W))
    val iDirectOk=Output(Bool()); val iDirectPaddr=Output(UInt(32.W))
    val iDirectMat=Output(UInt(2.W)); val iDirectExcp=Output(Bool())
    val dReq=Input(Bool()); val dVaddr=Input(UInt(32.W)); val dIsStore=Input(Bool()); val dAccept=Input(Bool())
    val dReady=Output(Bool()); val dPaddr=Output(UInt(32.W)); val dMat=Output(UInt(2.W))
    val dAccessFault=Output(Bool()); val dPageFault=Output(Bool())
    val pageRequest=Decoupled(UInt(34.W))
    val pageResponse=Flipped(Decoupled(new PageTableReadResponse))
  })
  val tlb=Module(new Sv32)
  val iTranslate=io.satp(31) && io.privilege=/=3.U
  val dTranslate=io.satp(31) && io.dataPrivilege=/=3.U
  val iMisaligned=io.iVaddr(1,0).orR
  // A PD repair can coincide with an otherwise idle walker.  Do not allocate a
  // brand-new instruction walk in that cancellation cycle: ownerValid still
  // describes the pre-edge state, so relying only on the owner cancel below
  // would let the stale request survive into the next cycle.
  val iTlbReq=io.iReq && iTranslate && !iMisaligned && !io.instructionCancel
  val dTlbReq=io.dReq && dTranslate
  val ownerValid=RegInit(false.B)
  val ownerData=RegInit(false.B)
  val preferData=RegInit(false.B)
  val chooseData=dTlbReq && (!iTlbReq || preferData)

  // 修复 D（133 潜在 TLB 所有者饿死死锁，方案取自 134，2026-09-22 用户授权
  // 的 Linux 修复战役收编）：取指翻译结果已就绪但前端无法接收（FTQ 满→
  // pfCanRequest=0→iAccept=0），同时数据侧 load 在等 TLB——若不取消取指
  // 所有者，形成 "FTQ满↔提交停↔头load等翻译" 的环死锁。取消后前端以同一
  // PF PC 重新请求。条件寄存一拍以打断 cancel→response.valid 的组合环；
  // 死锁状态稳定，晚一拍取消等价。CoreMark 为 M-mode 无翻译，此路径不激活。
  val dataPreemptCond = ownerValid && !ownerData && tlb.io.response.valid &&
    !io.iAccept && dTlbReq
  val dataPreempt = RegNext(dataPreemptCond, false.B) && ownerValid && !ownerData
  tlb.io.cancel := io.flush || (ownerValid && !ownerData && io.instructionCancel) || dataPreempt
  tlb.io.invalidate := io.fence
  tlb.io.request.valid := !ownerValid && (iTlbReq || dTlbReq)
  tlb.io.request.bits.virtualAddress := Mux(chooseData,io.dVaddr,io.iVaddr)
  tlb.io.request.bits.access := Mux(chooseData,Mux(io.dIsStore,2.U,1.U),0.U)
  tlb.io.request.bits.privilege := Mux(chooseData,io.dataPrivilege,io.privilege)
  tlb.io.request.bits.satp := io.satp
  tlb.io.request.bits.sum := io.status(18)
  tlb.io.request.bits.mxr := io.status(19)
  tlb.io.request.bits.identity := 0.U
  tlb.io.response.ready := ownerValid && Mux(ownerData,io.dAccept,io.iAccept)
  when(tlb.io.request.fire) {
    ownerValid:=true.B
    ownerData:=chooseData
    preferData := !chooseData
  }
  when(tlb.io.response.fire || io.flush || io.fence || dataPreempt ||
    (ownerValid && !ownerData && io.instructionCancel)) { ownerValid:=false.B }

  val iResponse=ownerValid && !ownerData && tlb.io.response.valid
  val dResponse=ownerValid && ownerData && tlb.io.response.valid
  val ipa=Mux(iTranslate,tlb.io.response.bits.physicalAddress,Cat(0.U(2.W),io.iVaddr))
  val dpa=Mux(dTranslate,tlb.io.response.bits.physicalAddress,Cat(0.U(2.W),io.dVaddr))
  val iPageError=iTranslate && iResponse && tlb.io.response.bits.pageFault
  val iAccessError=(iTranslate && iResponse && tlb.io.response.bits.accessFault) || ipa(33,32).orR || !PhysicalMap.ram(ipa(31,0))
  val attributes = Module(new PhysicalMemoryAttributes)
  attributes.io.iPaddr := ipa(31, 0)
  attributes.io.iDirectPaddr := io.iVaddr
  attributes.io.dPaddr := dpa(31, 0)
  io.iReady := io.iReq && (iMisaligned || !iTranslate || iResponse) && !io.flush && !io.fence
  io.iPaddr := ipa(31,0)
  io.iMat := attributes.io.iMat
  io.iMisaligned := io.iReq && iMisaligned
  io.iFaults := Mux(iMisaligned,(1<<Excp.INST_ADDR_MISALIGNED).U,
    Mux(iPageError,(1<<Excp.INST_PAGE_FAULT).U,Mux(iAccessError,(1<<Excp.INST_ACCESS_FAULT).U,0.U)))
  io.iDirectOk := !iTranslate
  io.iDirectPaddr := io.iVaddr
  io.iDirectMat := attributes.io.iDirectMat
  io.iDirectExcp := iMisaligned || !PhysicalMap.ram(io.iVaddr)
  io.dReady := io.dReq && (!dTranslate || dResponse) && !io.flush && !io.fence
  io.dPaddr := dpa(31,0)
  io.dMat := attributes.io.dMat
  io.dPageFault := dTranslate && dResponse && tlb.io.response.bits.pageFault
  io.dAccessFault := !io.dPageFault && ((dTranslate && dResponse && tlb.io.response.bits.accessFault) ||
    dpa(33,32).orR || !(PhysicalMap.ram(dpa(31,0)) || PhysicalMap.device(dpa(31,0))))

  // The shared walker is the sole coherent PTE-read owner.
  io.pageRequest.valid := tlb.io.memoryRequest.valid
  io.pageRequest.bits := tlb.io.memoryRequest.bits
  tlb.io.memoryRequest.ready := io.pageRequest.ready
  tlb.io.memoryResponse.valid := io.pageResponse.valid
  tlb.io.memoryResponse.bits := io.pageResponse.bits
  io.pageResponse.ready := tlb.io.memoryResponse.ready

  if (!sys.props.get("e91c.synthesis").contains("true")) {
    when(io.iReady && !io.iFaults.orR) {
      assert(io.iMat === PhysicalMemoryAttributes.MatCacheable,
        "Executable physical regions must be cacheable in the integrated Core")
    }
    when(io.dReady) {
      assert(io.dMat === PhysicalMemoryAttributes.dataMat(io.dPaddr),
        "data MAT must match the translated physical address")
    }
  }
}
