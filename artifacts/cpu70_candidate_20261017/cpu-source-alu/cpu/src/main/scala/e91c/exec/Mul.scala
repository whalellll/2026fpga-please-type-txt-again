// ============================================================
// e91c.exec.Mul — cpu/mul.v 的 Chisel 移植（RV32M 32x32 乘法器）
// ------------------------------------------------------------
// 四个并行16x16部分积配合高半部符号修正统一覆盖
// MUL/MULH/MULHSU/MULHU；结果仍在启动后一拍有效、吞吐为一。
// ============================================================
package e91c.exec

import chisel3._
import chisel3.util.Cat

class Mul extends Module {
  val io = IO(new Bundle {
    val valid    = Input(Bool())   // 启动（fu_mdu 保证 busy 期间不重复启动）
    val a        = Input(UInt(32.W))
    val b        = Input(UInt(32.W))
    val signedA  = Input(Bool())
    val signedB  = Input(Bool())
    val result   = Output(UInt(64.W))  // 64 位全乘积
    val done     = Output(Bool())      // 启动后下一拍有效
  })

  // Register four independent half-width products.  The critical input path
  // now crosses one 16x16 multiplier instead of a cascaded 32x32 APM chain;
  // reconstruction starts at these registers in the following cycle.
  val prod00Reg = Reg(UInt(32.W))
  val prod01Reg = Reg(UInt(32.W))
  val prod10Reg = Reg(UInt(32.W))
  val prod11Reg = Reg(UInt(32.W))
  val correctionReg = Reg(UInt(32.W))
  val validReg = RegInit(false.B)

  val correctionA = Mux(io.signedA && io.a(31), io.b, 0.U)
  val correctionB = Mux(io.signedB && io.b(31), io.a, 0.U)
  val correction = correctionA +& correctionB

  validReg := io.valid
  when(io.valid) {
    prod00Reg := io.a(15, 0) * io.b(15, 0)
    prod01Reg := io.a(15, 0) * io.b(31, 16)
    prod10Reg := io.a(31, 16) * io.b(15, 0)
    prod11Reg := io.a(31, 16) * io.b(31, 16)
    correctionReg := correction(31, 0)
  }

  val term00 = prod00Reg.pad(64)
  val term01 = Cat(0.U(16.W), prod01Reg, 0.U(16.W))
  val term10 = Cat(0.U(16.W), prod10Reg, 0.U(16.W))
  val term11 = Cat(prod11Reg, 0.U(32.W))
  val unsignedProduct = term00 + term01 + term10 + term11
  val correctedHigh = unsignedProduct(63, 32) - correctionReg
  io.result := correctedHigh ## unsignedProduct(31, 0)
  io.done   := validReg

  // 原实现带 (* use_dsp = "yes" ) 属性提示综合工具用 DSP 资源；
  // Chisel 6 无 addAttribute 自由函数，综合属性在生成 Verilog 后
  // 由脚本统一回注（33x33 乘法综合器默认也会选 DSP）。
}
