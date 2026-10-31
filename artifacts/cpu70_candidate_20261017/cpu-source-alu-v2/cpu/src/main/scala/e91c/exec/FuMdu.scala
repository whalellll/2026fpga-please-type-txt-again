// ============================================================
// e91c.exec.FuMdu — cpu/fu_mdu.v 的 Chisel 移植（乘除与 CSR 执行单元）
// ------------------------------------------------------------
// 非流水单条处理；乘法走自带寄存器的 Mul（接受后控制器保持 IDLE，
// 下拍可再收乘法）；除法走迭代 Div；CSR 快速读改写。
// 移植要点：
// - mul_flush_wait 3 拍冷却：flush 打断在途乘法时等待乘法器数据
//   捕获结束再重新开放，防止陈旧 done 误写回；
// - wb 多路选择优先 mul_done（mul 有独立元数据管线）；
// - pre_wb 比 wb 早一拍的完成令牌（除法在 S_BUSY 拍 div_done）。
// ============================================================
package e91c.exec

import chisel3._
import chisel3.util.{is, switch}
import e91c.config.Params.ROB_W
import e91c.config.{AluOpG, CsrOp}

class FuMdu extends Module {
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val issueValid = Input(Bool())
    val issueRobid = Input(UInt(ROB_W.W))
    val issueAluOpMdu = Input(UInt(7.W))      // 全局 alu_op 的乘除 7 位 [18:12]
    val issueCsrOp = Input(UInt(3.W))          // CSR_OP_NUM=3
    val issueCsrNum = Input(UInt(12.W))
    val issueSrc0 = Input(UInt(32.W))
    val issueSrc1 = Input(UInt(32.W))
    val mduReady = Output(Bool())
    val csrRaddr = Output(UInt(12.W))
    val csrRdata = Input(UInt(32.W))
    val wbValid = Output(Bool())
    val preWbValid = Output(Bool())
    val preWbRobid = Output(UInt(ROB_W.W))
    val wbRobid = Output(UInt(ROB_W.W))
    val wbData = Output(UInt(32.W))
    val wbData2 = Output(UInt(32.W))
  })

  val sIdle = 0.U(2.W); val sBusy = 1.U(2.W); val sWb = 2.U(2.W)
  val state = RegInit(sIdle)
  val rRobid = Reg(UInt(ROB_W.W))
  val rMulLow = Reg(Bool())
  val rResultIsQuotient = Reg(Bool())
  val rCsrNum = Reg(UInt(12.W))
  val rData = Reg(UInt(32.W))
  val rData2 = Reg(UInt(32.W))
  val rIsMul = RegInit(false.B)
  val mulFlushWait = RegInit(0.U(2.W))
  val mulRobidR = RegInit(0.U(ROB_W.W))
  val mulLowR = RegInit(false.B)
  val mulValidR = RegInit(false.B)

  // issueAluOpMdu 位序：[18:12] → MUL,MULH,MULHUB,DIV,DIVU,REM,REMU
  val opMul = io.issueAluOpMdu(AluOpG.MUL - AluOpG.MUL)
  val opMulh = io.issueAluOpMdu(AluOpG.MULH - AluOpG.MUL)
  val opMulhub = io.issueAluOpMdu(AluOpG.MULH_UNSIGNED_B - AluOpG.MUL)
  val opDiv = io.issueAluOpMdu(AluOpG.DIV - AluOpG.MUL)
  val opDivu = io.issueAluOpMdu(AluOpG.DIVU - AluOpG.MUL)
  val opRem = io.issueAluOpMdu(AluOpG.REM - AluOpG.MUL)
  val opRemu = io.issueAluOpMdu(AluOpG.REMU - AluOpG.MUL)

  val issueIsMul = opMul || opMulh || opMulhub
  val issueIsDiv = opDiv || opDivu || opRem || opRemu
  val issueIsCsr = io.issueCsrOp.orR

  val accept = (state === sIdle) && (mulFlushWait === 0.U) && io.issueValid
  io.mduReady := (state === sIdle) && (mulFlushWait === 0.U)

  val mulStart = accept && issueIsMul
  val uMul = Module(new Mul)
  uMul.io.valid := mulStart
  uMul.io.a := io.issueSrc0
  uMul.io.b := io.issueSrc1
  uMul.io.signedA := opMul || opMulh
  uMul.io.signedB := opMul || (opMulh && !opMulhub)
  val mulResult = uMul.io.result
  val mulDone = uMul.io.done

  val divStart = accept && issueIsDiv
  val uDiv = Module(new Div)
  uDiv.io.flush := io.flush
  uDiv.io.valid := divStart
  uDiv.io.dividend := io.issueSrc0
  uDiv.io.divisor := io.issueSrc1
  uDiv.io.isSigned := opDiv || opRem
  val divQuotient = uDiv.io.quotient
  val divRemainder = uDiv.io.remainder
  val divDone = uDiv.io.done

  io.csrRaddr := Mux(state === sIdle, io.issueCsrNum, rCsrNum)

  val csrOld = io.csrRdata
  val fastData = Mux(issueIsCsr, csrOld, 0.U)
  val rvCsrRw = io.issueCsrOp === CsrOp.WRITE.U(3.W)
  val rvCsrRs = io.issueCsrOp === CsrOp.SET.U(3.W)
  val rvCsrRc = io.issueCsrOp === CsrOp.CLEAR.U(3.W)
  val fastData2 = Mux(rvCsrRw, io.issueSrc0,
                  Mux(rvCsrRs, csrOld | io.issueSrc0,
                  Mux(rvCsrRc, csrOld & ~io.issueSrc0, 0.U)))

  when(reset.asBool) {
    state := sIdle; mulFlushWait := 0.U; rIsMul := false.B
    rResultIsQuotient := false.B
    mulRobidR := 0.U; mulLowR := false.B; mulValidR := false.B
  }.elsewhen(io.flush) {
    state := sIdle; rIsMul := false.B; mulValidR := false.B
    when((state === sBusy) && rIsMul) { mulFlushWait := 3.U }
  }.otherwise {
    when(mulFlushWait =/= 0.U) { mulFlushWait := mulFlushWait - 1.U }

    when(mulStart) {
      mulRobidR := io.issueRobid
      mulLowR := opMul
      mulValidR := true.B
    }.elsewhen(mulDone) {
      mulValidR := false.B
    }

    switch(state) {
      is(sIdle) {
        when(accept) {
          rRobid := io.issueRobid
          rMulLow := opMul
          rCsrNum := io.issueCsrNum
          rIsMul := issueIsMul
          rResultIsQuotient := opDiv || opDivu
          when(issueIsMul) {
            rIsMul := false.B     // 乘法有独立管线，控制器保持空闲
            state := sIdle
          }.elsewhen(issueIsDiv) {
            state := sBusy
          }.otherwise {
            rData := fastData
            rData2 := fastData2
            state := sWb
          }
        }
      }
      is(sBusy) {
        when(mulDone && rIsMul) {
          rData := Mux(rMulLow, mulResult(31, 0), mulResult(63, 32))
          rData2 := 0.U
          state := sWb
        }.elsewhen(divDone && !rIsMul) {
          rData := Mux(rResultIsQuotient, divQuotient, divRemainder)
          rData2 := 0.U
          state := sWb
        }
      }
      is(sWb) {
        state := sIdle
        rIsMul := false.B
      }
    }
  }

  io.wbValid := (mulDone && mulValidR) || (state === sWb)
  io.wbRobid := Mux(mulDone, mulRobidR, rRobid)
  io.wbData := Mux(mulDone,
    Mux(mulLowR, mulResult(31, 0), mulResult(63, 32)), rData)
  io.wbData2 := Mux(mulDone, 0.U, rData2)

  val preWbDiv = (state === sBusy) && divDone && !rIsMul
  val preWbAcceptOneCycle = accept && !issueIsDiv
  io.preWbValid := (preWbAcceptOneCycle || preWbDiv) && !io.flush
  io.preWbRobid := Mux(preWbDiv, rRobid, io.issueRobid)
}
