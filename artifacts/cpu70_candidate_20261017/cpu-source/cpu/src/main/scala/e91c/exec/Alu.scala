// ============================================================
// e91c.exec.Alu — cpu/alu.v 的 Chisel 移植（纯组合整数运算核）
// ------------------------------------------------------------
// 移植保持的结构决策：
// - add/sub/slt/sltu/PCADD/cmp 共享一条 32 位进位链，比较标志直接
//   从该进位链导出，fu_alu 不再建第二套比较器；
// - SLL/SRL/SRA 共享一个右移桶：左移 = 位反转恒等式
//   reverse(reverse(x) >> n)，33 位符号位让同一条算术右移
//   在符号=0 时退化为 SRL；
// - 加法类结果直接从加法器取，绕开非算术类的宽 one-hot OR，
//   给访存地址路径专用的 mux 分支。
// ============================================================
package e91c.exec

import chisel3._
import chisel3.util.{Cat, Fill, Reverse}
import e91c.config.AluOpC

// 用 Module 而非 RawModule：chiseltest 需要隐式时钟；本模块不使用 clk/reset，
// 生成的 Verilog 中它们仅作为未用的端口存在，不影响组合等价性。
class Alu extends Module {
  val io = IO(new Bundle {
    // 紧凑位序：{PCADD, ORN, ANDN, LUI..ADD}
    val aluOp     = Input(UInt(AluOpC.WIDTH.W))
    val aluSrc1   = Input(UInt(32.W))
    val aluSrc2   = Input(UInt(32.W))
    val exePc     = Input(UInt(32.W))
    val cmpEnable = Input(Bool())
    val result    = Output(UInt(32.W))
    val cmpEq     = Output(Bool())
    val cmpLts    = Output(Bool())
    val cmpLtu    = Output(Bool())
  })

  val opAdd   = io.aluOp(AluOpC.ADD)
  val opSub   = io.aluOp(AluOpC.SUB)
  val opSlt   = io.aluOp(AluOpC.SLT)
  val opSltu  = io.aluOp(AluOpC.SLTU)
  val opAnd   = io.aluOp(AluOpC.AND)
  val opNor   = io.aluOp(AluOpC.NOR)
  val opOr    = io.aluOp(AluOpC.OR)
  val opXor   = io.aluOp(AluOpC.XOR)
  val opSll   = io.aluOp(AluOpC.SLL)
  val opSrl   = io.aluOp(AluOpC.SRL)
  val opSra   = io.aluOp(AluOpC.SRA)
  val opLui   = io.aluOp(AluOpC.LUI)
  val opAndn  = io.aluOp(AluOpC.ANDN)
  val opOrn   = io.aluOp(AluOpC.ORN)
  val opPcadd = io.aluOp(AluOpC.PCADD)

  // ---- 共享进位链 ----
  val adderSub = opSub || opSlt || opSltu || io.cmpEnable
  val adderA   = Mux(opPcadd, io.exePc, io.aluSrc1)
  val adderB   = Mux(adderSub, ~io.aluSrc2, io.aluSrc2)
  val adderCin = adderSub
  val adderFull   = adderA +& adderB + adderCin   // 33 位
  val adderResult = adderFull(31, 0)
  val adderCout   = adderFull(32)

  // 条件分支借同一条进位链做减法，导出 zero/有符号/无符号比较
  io.cmpEq  := !adderResult.orR
  io.cmpLts := (io.aluSrc1(31) && !io.aluSrc2(31)) ||
               ((io.aluSrc1(31) === io.aluSrc2(31)) && adderResult(31))
  io.cmpLtu := !adderCout

  // ---- 各操作结果 ----
  val addSubResult = adderResult
  val sltResult    = Cat(0.U(31.W), io.cmpLts.asUInt)
  val sltuResult   = Cat(0.U(31.W), io.cmpLtu.asUInt)
  val andResult    = io.aluSrc1 & io.aluSrc2
  val orResult     = io.aluSrc1 | io.aluSrc2
  val norResult    = ~orResult
  val xorResult    = io.aluSrc1 ^ io.aluSrc2
  val luiResult    = io.aluSrc2
  val andnResult   = io.aluSrc1 & ~io.aluSrc2
  val ornResult    = io.aluSrc1 | ~io.aluSrc2

  // ---- 移位：一条右移桶覆盖 SLL/SRL/SRA ----
  val shiftSrc = Mux(opSll, Reverse(io.aluSrc1), io.aluSrc1)
  // 附加符号位：SRA 且 src1[31] 时为 1，否则为 0（SLL 时 opSra=0 天然安全）
  val shiftExt = (opSra && io.aluSrc1(31)) ## shiftSrc   // 33 位
  val shiftExtResult = shiftExt.asSInt >> io.aluSrc2(4, 0) // 算术右移
  val shiftRightResult = shiftExtResult.asUInt(31, 0)
  val shiftResult = Mux(opSll, Reverse(shiftRightResult), shiftRightResult)

  // ---- 结果选择：算术路径专用分支 + 非算术 one-hot OR ----
  val opAddResult = opAdd || opSub || opPcadd
  val nonAddResult =
    (Fill(32, opSlt)              & sltResult) |
    (Fill(32, opSltu)             & sltuResult) |
    (Fill(32, opAnd)              & andResult) |
    (Fill(32, opNor)              & norResult) |
    (Fill(32, opOr)               & orResult) |
    (Fill(32, opXor)              & xorResult) |
    (Fill(32, opLui)              & luiResult) |
    (Fill(32, opAndn)             & andnResult) |
    (Fill(32, opOrn)              & ornResult) |
    (Fill(32, opSll || opSrl || opSra) & shiftResult)

  io.result := Mux(opAddResult, addSubResult, nonAddResult)
}
