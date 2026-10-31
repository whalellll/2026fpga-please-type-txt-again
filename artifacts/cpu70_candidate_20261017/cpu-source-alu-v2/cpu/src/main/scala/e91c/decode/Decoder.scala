// ============================================================
// e91c.decode.Decoder — RV32IMA/Zicsr 译码器
// ------------------------------------------------------------
// 支持 RV32I/RV32M/RV32A/Zicsr/Zifencei/MRET/WFI；F/D 未实现。
// 移植保持的语义要点：
// - MULHSU 用两个高位乘标记位联合表示（MULH 选符号 A，MULH_UNSIGNED_B 选无符号 B）；
// - 不支持的 CSR 编号直接判非法（架构要求 illegal 而非静默读零）；
// - 只读 CSR 区（地址高两位=11）带写意图判非法；rs1=x0 的 CSRRS/CSRRC 退化为纯读；
// - JAL/JALR 的 imm 为指令长度（固定 4 字节），目标位移单独走 br_offs；
// - FENCE/FENCE.I 不进执行单元但进 ROB（is_nop 含 fence）；
// - futype ALU 位 = ~(load|store|csr|m)，即"其余一切"（含非法指令）。
// ============================================================
package e91c.decode

import chisel3._
import chisel3.util.{Cat, Fill, MuxCase}
import e91c.config._
import e91c.config.Params.{BR_TYPE_W, EXCP_NUM, FU_NUM, PRIV_NUM}
import AluOpG._
import BrOp._
import MemOp._
import Excp._

class Decoder extends Module {
  val io = IO(new Bundle {
    val inst = Input(UInt(32.W))
    val privilege = Input(UInt(2.W))
    val status = Input(UInt(32.W))
    val counterAccess = Input(UInt(3.W))
    val futype = Output(UInt(FU_NUM.W))
    val aluOp = Output(UInt(AluOpG.NUM.W))
    val brOp = Output(UInt(BrOp.NUM.W))
    val memOp = Output(UInt(MemOp.NUM.W))
    val csrOp = Output(UInt(3.W))
    val csrNum = Output(UInt(12.W))
    val src0Addr = Output(UInt(5.W))
    val src1Addr = Output(UInt(5.W))
    val useSrc0 = Output(Bool())
    val useSrc1 = Output(Bool())
    val rdAddr = Output(UInt(5.W))
    val rfWe = Output(Bool())
    val imm = Output(UInt(32.W))
    val useImm = Output(Bool())
    val brOffs = Output(UInt(32.W))
    val isBranch = Output(Bool())
    val brType = Output(UInt(BR_TYPE_W.W))
    val privVec = Output(UInt(PRIV_NUM.W))
    val isNop = Output(Bool())
    val isLoad = Output(Bool())
    val isStore = Output(Bool())
    val excp = Output(UInt(EXCP_NUM.W))
  })

  val inst = io.inst
  val opcode = inst(6, 0)
  val rd = inst(11, 7)
  val funct3 = inst(14, 12)
  val rs1 = inst(19, 15)
  val rs2 = inst(24, 20)
  val funct7 = inst(31, 25)

  val OPC_LOAD = "b0000011".U; val OPC_MISC_MEM = "b0001111".U
  val OPC_OP_IMM = "b0010011".U; val OPC_AUIPC = "b0010111".U
  val OPC_STORE = "b0100011".U; val OPC_OP = "b0110011".U
  val OPC_LUI = "b0110111".U; val OPC_BRANCH = "b1100011".U
  val OPC_JALR = "b1100111".U; val OPC_JAL = "b1101111".U
  val OPC_SYSTEM = "b1110011".U

  def op(i: Bool, f3: Int): Bool = i && (funct3 === f3.U)
  def opr(i: Bool, f3: Int, f7: Int): Bool = i && (funct3 === f3.U) && (funct7 === f7.U)
  val isOpImm = opcode === OPC_OP_IMM
  val isOp = opcode === OPC_OP
  // M-class serialization is selected directly from the 32-bit encoding.
  val isMOp = (io.inst(6, 0) === OPC_OP) && (io.inst(31, 25) === 1.U)

  val instLui = opcode === OPC_LUI
  val instAuipc = opcode === OPC_AUIPC
  val instAddi = op(isOpImm, 0); val instSlti = op(isOpImm, 2)
  val instSltiu = op(isOpImm, 3); val instXori = op(isOpImm, 4)
  val instOri = op(isOpImm, 6); val instAndi = op(isOpImm, 7)
  val instSlli = opr(isOpImm, 1, 0); val instSrli = opr(isOpImm, 5, 0)
  val instSrai = opr(isOpImm, 5, 0x20)
  val instAdd = opr(isOp, 0, 0); val instSub = opr(isOp, 0, 0x20)
  val instSll = opr(isOp, 1, 0); val instSlt = opr(isOp, 2, 0)
  val instSltu = opr(isOp, 3, 0); val instXor = opr(isOp, 4, 0)
  val instSrl = opr(isOp, 5, 0); val instSra = opr(isOp, 5, 0x20)
  val instOr = opr(isOp, 6, 0); val instAnd = opr(isOp, 7, 0)
  val instMul = opr(isMOp, 0, 1); val instMulh = opr(isMOp, 1, 1)
  val instMulhsu = opr(isMOp, 2, 1); val instMulhu = opr(isMOp, 3, 1)
  val instDiv = opr(isMOp, 4, 1); val instDivu = opr(isMOp, 5, 1)
  val instRem = opr(isMOp, 6, 1); val instRemu = opr(isMOp, 7, 1)
  // The M extension defines all eight funct3 values, so class selection does
  // not need the late expanded-instruction funct3 decode.
  val instM = isMOp

  val isBr = opcode === OPC_BRANCH
  val instJal = opcode === OPC_JAL
  val instJalr = (opcode === OPC_JALR) && (funct3 === 0.U)
  val instBeq = op(isBr, 0); val instBne = op(isBr, 1)
  val instBlt = op(isBr, 4); val instBge = op(isBr, 5)
  val instBltu = op(isBr, 6); val instBgeu = op(isBr, 7)
  val instCondBranch = Seq(instBeq, instBne, instBlt, instBge, instBltu, instBgeu).reduce(_ || _)

  // Atomic opcodes require a full RV32 instruction encoding.
  val atomicEncoding = io.inst(6,0) === "h2f".U && io.inst(14,12) === 2.U
  val atomicFunct = io.inst(31,27)
  val atomicLr = atomicEncoding && atomicFunct === 2.U && io.inst(24,20) === 0.U
  val atomicSc = atomicEncoding && atomicFunct === 3.U
  val atomicAmo = atomicEncoding && Seq(0,1,4,8,12,16,20,24,28).map(_.U === atomicFunct).reduce(_ || _)
  val instAtomic = atomicLr || atomicSc || atomicAmo
  val isLoadOp = opcode === OPC_LOAD
  val isStoreOp = opcode === OPC_STORE
  val instLb = op(isLoadOp, 0); val instLh = op(isLoadOp, 1); val instLw = op(isLoadOp, 2)
  val instLbu = op(isLoadOp, 4); val instLhu = op(isLoadOp, 5)
  val instSb = op(isStoreOp, 0); val instSh = op(isStoreOp, 1); val instSw = op(isStoreOp, 2)
  val instLoad = Seq(instLb, instLh, instLw, instLbu, instLhu).reduce(_ || _)
  val instStore = Seq(instSb, instSh, instSw).reduce(_ || _)

  val isMisc = opcode === OPC_MISC_MEM
  val instFence = op(isMisc, 0)
  val instFenceI = op(isMisc, 1)

  val instEcall = inst === "h00000073".U
  val instEbreak = inst === "h00100073".U
  // Decode privileged instruction classes directly from the raw word.
  val instMret = io.inst === "h30200073".U && io.privilege === 3.U
  val instSret = e91c.config.Params.ENABLE_SUPERVISOR.B && io.inst === "h10200073".U && io.privilege =/= 0.U && (io.privilege === 3.U || !io.status(22))
  val instSfence = e91c.config.Params.ENABLE_SUPERVISOR.B && (io.inst & "hfe007fff".U) === "h12000073".U &&
    io.privilege =/= 0.U && (io.privilege === 3.U || !io.status(20))
  val instWfi = io.inst === "h10500073".U && io.privilege =/= 0.U && (io.privilege === 3.U || !io.status(21))

  // Zicsr：仅本实现支持的 CSR 编号合法；只读区带写意图判非法
  // CSR encodings are always 32-bit. Decode them from the input before the
  // other instruction-class decoding to keep the CSR recognition path short.
  val csrFunct = (io.inst(6, 0) === OPC_SYSTEM) &&
    Seq(1, 2, 3, 5, 6, 7).map(f => io.inst(14, 12) === f.U).reduce(_ || _)
  val rvCsrNum = io.inst(31, 20)
  val csrSupported = e91c.backend.CsrAddressMap.addresses.map(n => rvCsrNum === n.U).reduce(_ || _)
  val csrPrivilegeOk = io.privilege >= rvCsrNum(9,8) &&
    !(rvCsrNum === "h180".U && io.privilege === 1.U && io.status(20))
  val isCounter = rvCsrNum(11,8) === "hc".U && rvCsrNum(6,2) === 0.U && rvCsrNum(1,0) =/= 3.U
  val counterOk = !isCounter || io.counterAccess(rvCsrNum(1,0))
  val csrIsImm = io.inst(14)
  val csrIsRw = csrFunct && (io.inst(13, 12) === 1.U)
  val csrIsRs = csrFunct && (io.inst(13, 12) === 2.U)
  val csrIsRc = csrFunct && (io.inst(13, 12) === 3.U)
  val csrSrcZero = io.inst(19, 15) === 0.U
  val csrWrites = csrIsRw || ((csrIsRs || csrIsRc) && !csrSrcZero)
  val csrReadOnly = rvCsrNum(11, 10) === 3.U
  val instCsr = csrFunct && csrSupported && csrPrivilegeOk && counterOk && !(csrWrites && csrReadOnly)
  val instCsrRw = instCsr && csrIsRw
  val instCsrRs = instCsr && csrIsRs && !csrSrcZero
  val instCsrRc = instCsr && csrIsRc && !csrSrcZero
  val instCsrRead = instCsr && (csrIsRs || csrIsRc) && csrSrcZero

  val instAluImm = Seq(instAddi, instSlti, instSltiu, instXori,
                       instOri, instAndi, instSlli, instSrli, instSrai).reduce(_ || _)
  val instAluReg = Seq(instAdd, instSub, instSll, instSlt, instSltu,
                       instXor, instSrl, instSra, instOr, instAnd).reduce(_ || _)
  val instKnown = Seq(instLui, instAuipc, instAluImm, instAluReg, instJal, instJalr,
                      instCondBranch, instLoad, instStore, instFence, instFenceI,
                      instEcall, instEbreak, instCsr, instMret, instSret, instSfence, instWfi, instM, instAtomic).reduce(_ || _)

  // 立即数：JAL/JALR 的 imm=4（链写回），目标位移单独走 brOffs
  val immI = Cat(Fill(20, inst(31)), inst(31, 20))
  val immS = Cat(Fill(20, inst(31)), inst(31, 25), inst(11, 7))
  val immB = Cat(Fill(19, inst(31)), inst(31), inst(7), inst(30, 25), inst(11, 8), 0.U(1.W))
  val immU = Cat(inst(31, 12), 0.U(12.W))
  val immJ = Cat(Fill(11, inst(31)), inst(31), inst(19, 12), inst(20), inst(30, 21), 0.U(1.W))
  val immShamt = Cat(0.U(27.W), inst(24, 20))
  val immCsr = Cat(0.U(27.W), rs1)

  io.imm := MuxCase(0.U, Seq(
    (instJal || instJalr) -> 4.U,
    (instLui || instAuipc) -> immU,
    (instCsr && csrIsImm) -> immCsr,
    (instSlli || instSrli || instSrai) -> immShamt,
    instStore -> immS,
    (instAluImm || instLoad) -> immI
  ))
  io.brOffs := MuxCase(0.U, Seq(
    instJal -> immJ,
    instJalr -> immI,
    instCondBranch -> immB
  ))

  io.src0Addr := rs1
  io.src1Addr := rs2
  io.useSrc0 := Seq(instAluImm, instAluReg, instJalr, instCondBranch,
                    instLoad, instStore, instM, instAtomic,
                    instCsr && !csrIsImm && !csrSrcZero).reduce(_ || _)
  io.useSrc1 := Seq(instAluReg, instCondBranch, instStore, instM, instAtomic && !atomicLr).reduce(_ || _)
  io.rdAddr := rd
  val writesRd = Seq(instLui, instAuipc, instAluImm, instAluReg,
                     instJal, instJalr, instLoad, instCsr, instM, instAtomic).reduce(_ || _)
  io.rfWe := writesRd && (rd =/= 0.U)
  io.useImm := Seq(instLui, instAuipc, instAluImm, instJal, instJalr,
                   instLoad, instStore, instCsr && csrIsImm).reduce(_ || _)

  // one-hot 操作码（Chisel 不能对 UInt 位切片赋值，用 Vec[Bool] 再聚合）
  val aluOpV = WireDefault(VecInit(Seq.fill(AluOpG.NUM)(false.B)))
  aluOpV(ADD) := Seq(instAdd, instAddi, instLoad, instStore, instJal, instJalr).reduce(_ || _)
  aluOpV(SUB) := instSub
  aluOpV(SLT) := instSlt || instSlti
  aluOpV(SLTU) := instSltu || instSltiu
  aluOpV(AND) := instAnd || instAndi
  aluOpV(OR) := instOr || instOri
  aluOpV(XOR) := instXor || instXori
  aluOpV(SLL) := instSll || instSlli
  aluOpV(SRL) := instSrl || instSrli
  aluOpV(SRA) := instSra || instSrai
  aluOpV(LUI) := instLui
  aluOpV(MUL) := instMul
  aluOpV(MULH) := instMulh || instMulhsu
  aluOpV(MULH_UNSIGNED_B) := instMulhu || instMulhsu
  aluOpV(DIV) := instDiv
  aluOpV(DIVU) := instDivu
  aluOpV(REM) := instRem
  aluOpV(REMU) := instRemu
  aluOpV(PCADD) := instAuipc
  io.aluOp := aluOpV.asUInt

  val brOpV = WireDefault(VecInit(Seq.fill(BrOp.NUM)(false.B)))
  brOpV(BEQ) := instBeq; brOpV(BNE) := instBne; brOpV(JALR) := instJalr
  brOpV(JAL) := instJal; brOpV(BLT) := instBlt; brOpV(BGE) := instBge
  brOpV(BLTU) := instBltu; brOpV(BGEU) := instBgeu
  io.brOp := brOpV.asUInt

  val memOpV = WireDefault(VecInit(Seq.fill(MemOp.NUM)(false.B)))
  memOpV(ST_W) := instSw || atomicSc || atomicAmo; memOpV(LD_W) := instLw || atomicLr; memOpV(ST_B) := instSb
  memOpV(ST_H) := instSh; memOpV(LD_B) := instLb; memOpV(LD_H) := instLh
  memOpV(LD_BU) := instLbu; memOpV(LD_HU) := instLhu
  memOpV(ATOMIC) := instAtomic
  for (bit <- 0 until 5) { memOpV(9+bit) := instAtomic && atomicFunct(bit) }
  io.memOp := memOpV.asUInt

  io.csrOp := MuxCase(CsrOp.NONE.U(3.W), Seq(
    instCsrRead -> CsrOp.READ.U(3.W),
    instCsrRw -> CsrOp.WRITE.U(3.W),
    instCsrRs -> CsrOp.SET.U(3.W),
    instCsrRc -> CsrOp.CLEAR.U(3.W)
  ))
  io.isBranch := instJal || instJalr || instCondBranch
  val jalCall = instJal && ((rd === 1.U) || (rd === 5.U))
  val jalrCall = instJalr && ((rd === 1.U) || (rd === 5.U))
  val jalrRet = instJalr && (rd === 0.U) && ((rs1 === 1.U) || (rs1 === 5.U))
  io.brType := MuxCase(BrType.COND.U, Seq(
    jalrRet -> BrType.RET.U,
    (jalCall || jalrCall) -> BrType.CALL.U,
    (instJal || instJalr) -> BrType.UNCOND.U
  ))
  io.isLoad := instLoad || atomicLr
  io.isStore := instStore || atomicSc || atomicAmo
  io.isNop := (inst === "h00000013".U) || instFence || instFenceI

  val futypeV = WireDefault(VecInit(Seq.fill(FU_NUM)(false.B)))
  // Reserve the CSR issue class from its encoding. Validity remains in
  // instCsr/excp, but rename need not wait for the CSR address/privilege checks.
  futypeV(FuType.ALU) := !(instLoad || instStore || csrFunct || instM || instAtomic)
  futypeV(FuType.MEM) := instLoad || instStore || instAtomic
  futypeV(FuType.MDU) := csrFunct || instM
  io.futype := futypeV.asUInt

  val priv = WireDefault(VecInit(Seq.fill(PRIV_NUM)(false.B)))
  priv(PrivType.CSR_WR) := csrFunct && csrWrites
  priv(PrivType.MRET) := instMret || instSret
  priv(PrivType.CSR_SERIAL) := (csrFunct && !csrWrites) || instSfence
  priv(PrivType.FENCE_I) := instFenceI
  priv(PrivType.WFI) := instWfi
  priv(PrivType.FENCE) := instFence || instSfence
  io.privVec := priv.asUInt

  io.csrNum := Mux(instCsr || instMret || instSret || instSfence, rvCsrNum, 0.U)

  val excp = WireDefault(VecInit(Seq.fill(EXCP_NUM)(false.B)))
  excp(ILLEGAL_INST) := !instKnown
  excp(ECALL_M) := instEcall
  excp(BREAKPOINT) := instEbreak
  io.excp := excp.asUInt
}
