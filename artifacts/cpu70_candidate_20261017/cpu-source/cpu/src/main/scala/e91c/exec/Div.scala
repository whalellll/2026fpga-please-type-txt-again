// ============================================================
// e91c.exec.Div — cpu/div.v 的 Chisel 移植（RV32M 迭代除法器）
// ------------------------------------------------------------
// 移植保持的结构决策：
// - prep 级先锁存原始操作数，再用共享取负通路依次计算两个绝对值；
// - 固定 32 步 radix-2 restoring 迭代，避免 CLZ、可变移位和动态商位选择；
// - 商和余数的符号修正复用同一条取负通路，避免复制 32 位加法器；
// - flush 只作废控制位（busy/done/prepState），数据寄存器保持——
//   被作废运算的数据不可观察，避免高扇出冲刷信号进 32 位通路。
// ============================================================
package e91c.exec

import chisel3._
import chisel3.util.Cat

class Div extends Module {
  val io = IO(new Bundle {
    val flush    = Input(Bool())   // 冲刷打断（作废当前迭代）
    val valid    = Input(Bool())   // 启动
    val dividend = Input(UInt(32.W))
    val divisor  = Input(UInt(32.W))
    val isSigned = Input(Bool())
    val quotient  = Output(UInt(32.W))
    val remainder = Output(UInt(32.W))
    val done      = Output(Bool()) // 结果有效一拍
  })

  // ---- 控制状态 ----
  val busyReg = RegInit(false.B)
  val doneReg = RegInit(false.B)
  val quotientReg  = RegInit(0.U(32.W))
  val remainderReg = RegInit(0.U(32.W))

  // ---- 迭代数据通路 ----
  val remReg      = RegInit(0.U(33.W))
  val quotReg     = RegInit(0.U(32.W))
  val divisorMagReg = RegInit(0.U(32.W))
  val iterLeftReg = RegInit(0.U(6.W))
  val quotNegReg  = RegInit(false.B)
  val remNegReg   = RegInit(false.B)

  // ---- prep/finalize 状态：共享 32 位取负通路 ----
  val prepIdle = 0.U(2.W)
  val prepDividend = 1.U(2.W)
  val prepDivisor = 2.U(2.W)
  val finishRemainder = 3.U(2.W)
  val prepStateReg = RegInit(prepIdle)
  val dividendReg = RegInit(0.U(32.W))
  val divisorReg  = RegInit(0.U(32.W))
  val isSignedReg = RegInit(false.B)

  val acceptNew  = io.valid && !busyReg && prepStateReg === prepIdle
  val divZero    = divisorReg === 0.U
  val divOverflow = isSignedReg &&
                    dividendReg === 0x80000000L.U &&
                    divisorReg  === 0xffffffffL.U
  val quotNegW = isSignedReg && (dividendReg(31) ^ divisorReg(31))
  val remNegW  = isSignedReg && dividendReg(31)

  val iterShiftedRem = Cat(remReg(31, 0), quotReg(31))
  val divisorWide = Cat(0.U(1.W), divisorMagReg)
  val iterGe = iterShiftedRem >= divisorWide
  val iterRem = Mux(iterGe, iterShiftedRem - divisorWide, iterShiftedRem)
  val iterQuot = Cat(quotReg(30, 0), iterGe)

  // 四个互斥阶段共享一条 32 位二进制补码取负通路。
  val sharedNegateInput = Mux(prepStateReg === prepDividend, dividendReg,
    Mux(prepStateReg === prepDivisor, divisorReg,
      Mux(busyReg && iterLeftReg === 1.U, iterQuot, remReg(31, 0))))
  val sharedNegateResult = (~sharedNegateInput).asUInt + 1.U
  val dividendMagnitude = Mux(isSignedReg && dividendReg(31), sharedNegateResult, dividendReg)
  val divisorMagnitude = Mux(isSignedReg && divisorReg(31), sharedNegateResult, divisorReg)

  // ---- 时序主块：reset > flush > 正常 ----
  when(reset.asBool) {
    busyReg := false.B;  doneReg := false.B;  prepStateReg := prepIdle
    quotientReg := 0.U;  remainderReg := 0.U
    remReg := 0.U;  quotReg := 0.U;  divisorMagReg := 0.U
    iterLeftReg := 0.U;  quotNegReg := false.B;  remNegReg := false.B
    dividendReg := 0.U;  divisorReg := 0.U;  isSignedReg := false.B
  }.elsewhen(io.flush) {
    // 只作废控制位，数据通路寄存器保持（下次启动整体覆写）
    busyReg := false.B;  doneReg := false.B;  prepStateReg := prepIdle
  }.otherwise {
    doneReg := false.B

    // prep 级入口：锁存新操作数（旁路 mux 浅终点）
    when(acceptNew) {
      prepStateReg := prepDividend
      dividendReg := io.dividend
      divisorReg  := io.divisor
      isSignedReg := io.isSigned
    }

    when(prepStateReg === prepDividend) {
      quotReg := dividendMagnitude
      quotNegReg := quotNegW
      remNegReg := remNegW
      prepStateReg := prepDivisor
    }.elsewhen(prepStateReg === prepDivisor) {
      prepStateReg := prepIdle
      when(divZero) {
        quotientReg  := "hffffffff".U
        remainderReg := dividendReg
        doneReg      := true.B
      }.elsewhen(divOverflow) {
        quotientReg  := "h80000000".U
        remainderReg := 0.U
        doneReg      := true.B
      }.elsewhen(quotReg < divisorMagnitude) {
        quotientReg  := 0.U
        remainderReg := dividendReg
        doneReg      := true.B
      }.otherwise {
        busyReg      := true.B
        remReg       := 0.U
        divisorMagReg := divisorMagnitude
        iterLeftReg  := 32.U
      }
    }.elsewhen(busyReg) {
      when(iterLeftReg === 1.U) {
        busyReg      := false.B
        quotientReg  := Mux(quotNegReg, sharedNegateResult, iterQuot)
        remReg       := iterRem
        prepStateReg := finishRemainder
      }.otherwise {
        remReg       := iterRem
        quotReg      := iterQuot
        iterLeftReg  := iterLeftReg - 1.U
      }
    }.elsewhen(prepStateReg === finishRemainder) {
      remainderReg := Mux(remNegReg, sharedNegateResult, remReg(31, 0))
      prepStateReg := prepIdle
      doneReg := true.B
    }
  }

  io.quotient  := quotientReg
  io.remainder := remainderReg
  io.done      := doneReg
}
