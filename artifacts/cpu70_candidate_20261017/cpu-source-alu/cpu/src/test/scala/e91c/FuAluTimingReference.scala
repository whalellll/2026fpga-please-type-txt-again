// ============================================================
// e91c.exec.FuAlu — cpu/fu_alu.v 的 Chisel 移植（ALU 执行单元，单周期含分支）
// ------------------------------------------------------------
// 发射组合进入、内部锁存一拍执行；内部例化 Alu 组合核。
// 移植要点：
// - imm/src1 在发射沿分别锁存，执行拍选择，截断发射仲裁到执行寄存器的长路径；
// - 链接值复用：wb_data = is_link ? pc+4 : alu_result（不为链接另建加法器）；
// - JALR 目标按规范清 bit0；条件分支借用 ALU 共享进位链的比较标志；
// - early_wakeup 受 ALU_EARLY_WAKEUP_ENABLE 宏门控（当前为 false）。
// ============================================================
package e91c

import e91c.exec.Alu

import chisel3._
import chisel3.util.Cat
import e91c.config.Params.{FTQ_W, ROB_W}
import e91c.config.{AluOpC, BrOp, Params}

class OriginalFuAluTimingReference extends Module {
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val issueValid = Input(Bool())
    val issueRobid = Input(UInt(ROB_W.W))
    val issuePc = Input(UInt(32.W))
    val issueAluOp = Input(UInt(AluOpC.WIDTH.W))
    val issueBrOp = Input(UInt(BrOp.NUM.W))
    val issueSrc0 = Input(UInt(32.W))
    val issueSrc1 = Input(UInt(32.W))
    val issueImm = Input(UInt(32.W))
    val issueUseImm = Input(Bool())
    val issueBrOffs = Input(UInt(32.W))
    val issuePredTaken = Input(Bool())
    val issueFtqId = Input(UInt(FTQ_W.W))
    val wbValid = Output(Bool())
    val wbRobid = Output(UInt(ROB_W.W))
    val wbData = Output(UInt(32.W))
    val wbBrTaken = Output(Bool())
    val wbBrTarget = Output(UInt(32.W))
    val wbPc = Output(UInt(32.W))
    val wbIsCond = Output(Bool())
    val wbPredTaken = Output(Bool())
    val wbFtqId = Output(UInt(FTQ_W.W))
    val earlyWakeupValid = Output(Bool())
    val earlyWakeupRobid = Output(UInt(ROB_W.W))
  })

  val exValid = RegInit(false.B)
  val exRobid = Reg(UInt(ROB_W.W))
  val exPc = Reg(UInt(32.W))
  val exAluOp = Reg(UInt(AluOpC.WIDTH.W))
  val exBrOp = Reg(UInt(BrOp.NUM.W))
  val exSrc0 = Reg(UInt(32.W))
  val exSrc1 = Reg(UInt(32.W))
  val exImm = Reg(UInt(32.W))
  val exUseImm = Reg(Bool())
  val exBrOffs = Reg(UInt(32.W))
  val exIsLink = Reg(Bool())
  val exPredTaken = Reg(Bool())
  val exFtqId = Reg(UInt(FTQ_W.W))

  when(reset.asBool || io.flush) {
    exValid := false.B
  }.otherwise {
    exValid := io.issueValid
    when(io.issueValid) {
      exRobid := io.issueRobid
      exPc := io.issuePc
      exAluOp := io.issueAluOp
      exBrOp := io.issueBrOp
      exSrc0 := io.issueSrc0
      exSrc1 := io.issueSrc1
      exImm := io.issueImm
      exUseImm := io.issueUseImm
      exBrOffs := io.issueBrOffs
      exIsLink := io.issueBrOp(BrOp.JAL) || io.issueBrOp(BrOp.JALR)
      exPredTaken := io.issuePredTaken
      exFtqId := io.issueFtqId
    }
  }

  val brCompare = io.issueBrOp(BrOp.BEQ) || io.issueBrOp(BrOp.BNE) ||
                  io.issueBrOp(BrOp.BLT) || io.issueBrOp(BrOp.BGE) ||
                  io.issueBrOp(BrOp.BLTU) || io.issueBrOp(BrOp.BGEU)
  // 用 ex 态（非发射拍）驱动 ALU
  val brCompareEx = exBrOp(BrOp.BEQ) || exBrOp(BrOp.BNE) ||
                    exBrOp(BrOp.BLT) || exBrOp(BrOp.BGE) ||
                    exBrOp(BrOp.BLTU) || exBrOp(BrOp.BGEU)

  val uAlu = Module(new Alu)
  uAlu.io.aluOp := exAluOp
  uAlu.io.aluSrc1 := exSrc0
  uAlu.io.aluSrc2 := Mux(exUseImm, exImm, exSrc1)
  uAlu.io.exePc := exPc
  uAlu.io.cmpEnable := brCompareEx
  val aluResult = uAlu.io.result
  val brEq = uAlu.io.cmpEq
  val brLts = uAlu.io.cmpLts
  val brLtu = uAlu.io.cmpLtu

  val wbData = Mux(exIsLink, exPc + 4.U, aluResult)
  io.wbValid := exValid
  io.wbRobid := exRobid
  io.wbData := wbData

  val isBranch = exBrOp.orR
  val brTaken =
    (exBrOp(BrOp.BEQ) && brEq) || (exBrOp(BrOp.BNE) && !brEq) ||
    (exBrOp(BrOp.BLT) && brLts) || (exBrOp(BrOp.BGE) && !brLts) ||
    (exBrOp(BrOp.BLTU) && brLtu) || (exBrOp(BrOp.BGEU) && !brLtu) ||
    exBrOp(BrOp.JAL) || exBrOp(BrOp.JALR)

  val jalrTargetSum = exSrc0 + exBrOffs
  val jalrTarget = Cat(jalrTargetSum(31, 1), 0.U(1.W))
  val brTarget = Mux(exBrOp(BrOp.JALR), jalrTarget, exPc + exBrOffs)

  io.wbBrTaken := exValid && brTaken
  io.wbBrTarget := Mux(exValid && isBranch, brTarget, 0.U)
  io.wbPc := exPc
  io.wbIsCond := exValid && brCompareEx
  io.wbPredTaken := exPredTaken
  io.wbFtqId := exFtqId

  io.earlyWakeupValid := Params.ALU_EARLY_WAKEUP_ENABLE.B &&
                         io.issueValid && !io.flush && !reset.asBool
  io.earlyWakeupRobid := io.issueRobid
}
