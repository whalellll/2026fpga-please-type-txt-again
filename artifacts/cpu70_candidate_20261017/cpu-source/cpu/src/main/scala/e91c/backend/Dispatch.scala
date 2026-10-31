// ============================================================
// e91c.backend.Dispatch — cpu/dispatch.v 的 Chisel 移植（分发级，纯组合）
// ------------------------------------------------------------
// 读 ROB 补操作数 + 按 FU 类型路由进 5 个保留站。
// 移植保持的语义：
// - ROB 补数：已锁存优先，否则按生产者 tag 读 ROB（ready|rrdy，val 三选）；
//   key_val 走去掉 ALU2 分支的读口（RS_MEM 用并行加法器补回）；
// - ALU 路由：双 ALU 双站可收 → 槽0→alu0/槽1→alu1 固定程序序；
//   三 ALU → 槽2 专走 alu2（triple）；单 ALU 按占用数选站（<= 偏 alu0）；
// - MEM 双口：口 0 恒载最老 MEM；口 1 仅 MEM/MEM 对；
// - MDU 单口；zimm 在此窄缝注入 src0（use_imm → ready=1/val=imm）；
// - fire 保序（槽1 不得越过未发槽0）；dispatch_ready=全部 valid 槽本拍
//   都 fire（同拍 vacate+refill）。
// ============================================================
package e91c.backend

import chisel3._
import chisel3.util.Cat
import e91c.config.Params.{FTQ_W, FU_NUM, ROB_W, RS_ALU_OCC_W}
import e91c.config.{AluOpG, FuType, MemOp}

class Dispatch extends Module {
  val io = IO(new Bundle {
    // 三槽输入（rename 流水寄存器）
    val disValid = Input(Vec(2, Bool()))
    val disRobid = Input(Vec(2, UInt(ROB_W.W)))
    val disPc = Input(Vec(2, UInt(32.W)))
    val disFutype = Input(Vec(2, UInt(FU_NUM.W)))
    val disAluOp = Input(Vec(2, UInt(AluOpG.NUM.W)))   // 全局 22 位
    val disBrOp = Input(Vec(2, UInt(8.W)))
    val disMemOp = Input(Vec(2, UInt(MemOp.NUM.W)))
    val disCsrOp = Input(Vec(2, UInt(3.W)))
    val disCsrNum = Input(Vec(2, UInt(12.W)))
    val disSrc0Ready = Input(Vec(2, Bool()))
    val disSrc0Val = Input(Vec(2, UInt(32.W)))
    val disSrc0Robid = Input(Vec(2, UInt(ROB_W.W)))
    val disSrc1Ready = Input(Vec(2, Bool()))
    val disSrc1Val = Input(Vec(2, UInt(32.W)))
    val disSrc1Robid = Input(Vec(2, UInt(ROB_W.W)))
    val disImm = Input(Vec(2, UInt(32.W)))
    val disUseImm = Input(Vec(2, Bool()))
    val disBrOffs = Input(Vec(2, UInt(32.W)))
    val disPredTaken = Input(Vec(2, Bool()))
    val disFtqId = Input(Vec(2, UInt(FTQ_W.W)))
    // ROB 6 读口
    val robRaddr = Output(Vec(4, UInt(ROB_W.W)))
    val robRrdy = Input(Vec(4, Bool()))
    val robRdata = Input(Vec(4, UInt(32.W)))
    val robRdataNoAlu = Input(Vec(2, UInt(32.W)))     // 口 0/2/4 的去 ALU2 版
    // RS 反压
    val rsAluCanAccept = Input(Vec(2, Bool()))
    val rsAluOccupancy = Input(Vec(2, UInt(RS_ALU_OCC_W.W)))
    val rsMemCanAccept = Input(Bool())
    val rsMemCanAcceptTwo = Input(Bool())
    val rsMduCanAccept = Input(Bool())
    // 输出
    val dispatchReady = Output(Bool())
    val disFire = Output(Vec(2, Bool()))
    val rsAluPushValid = Output(Vec(2, Bool()))
    val rsAluPushRobid = Output(Vec(2, UInt(ROB_W.W)))
    val rsAluPushPc = Output(Vec(2, UInt(32.W)))
    val rsAluPushAluOp = Output(Vec(2, UInt(15.W)))   // 紧凑 15 位
    val rsAluPushBrOp = Output(Vec(2, UInt(8.W)))
    val rsAluPushSrc0Ready = Output(Vec(2, Bool()))
    val rsAluPushSrc0Val = Output(Vec(2, UInt(32.W)))
    val rsAluPushSrc0Robid = Output(Vec(2, UInt(ROB_W.W)))
    val rsAluPushSrc1Ready = Output(Vec(2, Bool()))
    val rsAluPushSrc1Val = Output(Vec(2, UInt(32.W)))
    val rsAluPushSrc1Robid = Output(Vec(2, UInt(ROB_W.W)))
    val rsAluPushImm = Output(Vec(2, UInt(32.W)))
    val rsAluPushUseImm = Output(Vec(2, Bool()))
    val rsAluPushBrOffs = Output(Vec(2, UInt(32.W)))
    val rsAluPushPredTaken = Output(Vec(2, Bool()))
    val rsAluPushFtqId = Output(Vec(2, UInt(FTQ_W.W)))
    // rs_mem 双口
    val rsMemPushValid = Output(Vec(2, Bool()))
    val rsMemPushRobid = Output(Vec(2, UInt(ROB_W.W)))
    val rsMemPushMemOp = Output(Vec(2, UInt(MemOp.NUM.W)))
    val rsMemPushSrc0Ready = Output(Vec(2, Bool()))
    val rsMemPushSrc0Val = Output(Vec(2, UInt(32.W)))
    val rsMemPushSrc0Robid = Output(Vec(2, UInt(ROB_W.W)))
    val rsMemPushSrc0KeyVal = Output(Vec(2, UInt(32.W)))
    val rsMemPushSrc0RobWait = Output(Vec(2, Bool()))
    val rsMemPushSrc1Ready = Output(Vec(2, Bool()))
    val rsMemPushSrc1Val = Output(Vec(2, UInt(32.W)))
    val rsMemPushSrc1Robid = Output(Vec(2, UInt(ROB_W.W)))
    val rsMemPushImm = Output(Vec(2, UInt(32.W)))
    // rs_mdu
    val rsMduPushValid = Output(Bool())
    val rsMduPushRobid = Output(UInt(ROB_W.W))
    val rsMduPushAluOpMdu = Output(UInt(7.W))          // [18:12]
    val rsMduPushCsrOp = Output(UInt(3.W))
    val rsMduPushCsrNum = Output(UInt(12.W))
    val rsMduPushSrc0Ready = Output(Bool())
    val rsMduPushSrc0Val = Output(UInt(32.W))
    val rsMduPushSrc0Robid = Output(UInt(ROB_W.W))
    val rsMduPushSrc1Ready = Output(Bool())
    val rsMduPushSrc1Val = Output(UInt(32.W))
    val rsMduPushSrc1Robid = Output(UInt(ROB_W.W))
  })

  // ---- ROB 读口 ----
  io.robRaddr(0) := io.disSrc0Robid(0)
  io.robRaddr(1) := io.disSrc1Robid(0)
  io.robRaddr(2) := io.disSrc0Robid(1)
  io.robRaddr(3) := io.disSrc1Robid(1)

  // ---- 第一步：补操作数 ----
  def srcReady(i: Int, p: Int): Bool = io.disSrc0Ready(i) || io.robRrdy(p)
  val s0Ready = Wire(Vec(2, Bool())); val s1Ready = Wire(Vec(2, Bool()))
  val s0Val = Wire(Vec(2, UInt(32.W))); val s1Val = Wire(Vec(2, UInt(32.W)))
  val s0KeyVal = Wire(Vec(2, UInt(32.W)))
  for (i <- 0 until 2) {
    val p0 = i * 2; val p1 = i * 2 + 1
    s0Ready(i) := io.disSrc0Ready(i) || io.robRrdy(p0)
    s1Ready(i) := io.disSrc1Ready(i) || io.robRrdy(p1)
    s0Val(i) := Mux(io.disSrc0Ready(i), io.disSrc0Val(i),
                Mux(io.robRrdy(p0), io.robRdata(p0), 0.U))
    s1Val(i) := Mux(io.disSrc1Ready(i), io.disSrc1Val(i),
                Mux(io.robRrdy(p1), io.robRdata(p1), 0.U))
    s0KeyVal(i) := Mux(io.disSrc0Ready(i), io.disSrc0Val(i),
                   Mux(io.robRrdy(p0), io.robRdataNoAlu(i), 0.U))
  }

  // ---- 第二步：路由 ----
  val isAlu = Wire(Vec(2, Bool())); val isMem = Wire(Vec(2, Bool())); val isMdu = Wire(Vec(2, Bool()))
  for (i <- 0 until 2) {
    isAlu(i) := io.disValid(i) && io.disFutype(i)(FuType.ALU)
    isMem(i) := io.disValid(i) && io.disFutype(i)(FuType.MEM)
    isMdu(i) := io.disValid(i) && io.disFutype(i)(FuType.MDU)
  }
  val twoAlu = isAlu(0) && isAlu(1)
  val dualAluOk = twoAlu && io.rsAluCanAccept(0) && io.rsAluCanAccept(1)
  val singleAluToAlu0 = io.rsAluCanAccept(0) &&
    (!io.rsAluCanAccept(1) || io.rsAluOccupancy(0) <= io.rsAluOccupancy(1))
  val slotToAlu0 = Wire(Vec(2, Bool()))
  val slotToAlu1 = Wire(Vec(2, Bool()))
  slotToAlu0(0) := isAlu(0) && (dualAluOk || singleAluToAlu0)
  slotToAlu1(0) := isAlu(0) && !dualAluOk && !singleAluToAlu0
  slotToAlu0(1) := isAlu(1) && !dualAluOk && singleAluToAlu0
  slotToAlu1(1) := isAlu(1) && (dualAluOk || !singleAluToAlu0)
  val willTakeMem = isMem
  val rsOk = Wire(Vec(2, Bool()))
  rsOk(0) := Mux(isAlu(0), Mux(slotToAlu0(0), io.rsAluCanAccept(0), io.rsAluCanAccept(1)),
    Mux(isMem(0), io.rsMemCanAccept, Mux(isMdu(0), io.rsMduCanAccept, false.B)))
  rsOk(1) := Mux(isAlu(1),
    Mux(slotToAlu0(1), io.rsAluCanAccept(0) && !slotToAlu0(0), io.rsAluCanAccept(1) && !slotToAlu1(0)),
    Mux(isMem(1), Mux(isMem(0), io.rsMemCanAcceptTwo, io.rsMemCanAccept),
      Mux(isMdu(1), io.rsMduCanAccept && !isMdu(0), false.B)))
  io.disFire(0) := io.disValid(0) && rsOk(0)
  io.disFire(1) := io.disValid(1) && rsOk(1) && (!io.disValid(0) || io.disFire(0))
  io.dispatchReady := (!io.disValid(0) || io.disFire(0)) && (!io.disValid(1) || io.disFire(1))

  // ---- 第四步：push 拼装 ----
  // 源选择：from_slot2 > from_slot1 > slot0（年轻者后到但覆盖优先）
  val alu0From1 = slotToAlu0(1) && io.disFire(1)
  val alu1From1 = slotToAlu1(1) && io.disFire(1)

  def aluCompact(i: Int): UInt =
    Cat(io.disAluOp(i)(21, 19), io.disAluOp(i)(11, 0))

  io.rsAluPushValid(0) := (slotToAlu0(0) && io.disFire(0)) || alu0From1
  io.rsAluPushRobid(0) := Mux(alu0From1, io.disRobid(1), io.disRobid(0))
  io.rsAluPushPc(0) := Mux(alu0From1, io.disPc(1), io.disPc(0))
  io.rsAluPushAluOp(0) := Mux(alu0From1, aluCompact(1), aluCompact(0))
  io.rsAluPushBrOp(0) := Mux(alu0From1, io.disBrOp(1), io.disBrOp(0))
  io.rsAluPushSrc0Ready(0) := Mux(alu0From1, s0Ready(1), s0Ready(0))
  io.rsAluPushSrc0Val(0) := Mux(alu0From1, s0Val(1), s0Val(0))
  io.rsAluPushSrc0Robid(0) := Mux(alu0From1, io.disSrc0Robid(1), io.disSrc0Robid(0))
  io.rsAluPushSrc1Ready(0) := Mux(alu0From1, s1Ready(1), s1Ready(0))
  io.rsAluPushSrc1Val(0) := Mux(alu0From1, s1Val(1), s1Val(0))
  io.rsAluPushSrc1Robid(0) := Mux(alu0From1, io.disSrc1Robid(1), io.disSrc1Robid(0))
  io.rsAluPushImm(0) := Mux(alu0From1, io.disImm(1), io.disImm(0))
  io.rsAluPushUseImm(0) := Mux(alu0From1, io.disUseImm(1), io.disUseImm(0))
  io.rsAluPushBrOffs(0) := Mux(alu0From1, io.disBrOffs(1), io.disBrOffs(0))
  io.rsAluPushPredTaken(0) := Mux(alu0From1, io.disPredTaken(1), io.disPredTaken(0))
  io.rsAluPushFtqId(0) := Mux(alu0From1, io.disFtqId(1), io.disFtqId(0))

  io.rsAluPushValid(1) := (slotToAlu1(0) && io.disFire(0)) || alu1From1
  io.rsAluPushRobid(1) := Mux(alu1From1, io.disRobid(1), io.disRobid(0))
  io.rsAluPushPc(1) := Mux(alu1From1, io.disPc(1), io.disPc(0))
  io.rsAluPushAluOp(1) := Mux(alu1From1, aluCompact(1), aluCompact(0))
  io.rsAluPushBrOp(1) := Mux(alu1From1, io.disBrOp(1), io.disBrOp(0))
  io.rsAluPushSrc0Ready(1) := Mux(alu1From1, s0Ready(1), s0Ready(0))
  io.rsAluPushSrc0Val(1) := Mux(alu1From1, s0Val(1), s0Val(0))
  io.rsAluPushSrc0Robid(1) := Mux(alu1From1, io.disSrc0Robid(1), io.disSrc0Robid(0))
  io.rsAluPushSrc1Ready(1) := Mux(alu1From1, s1Ready(1), s1Ready(0))
  io.rsAluPushSrc1Val(1) := Mux(alu1From1, s1Val(1), s1Val(0))
  io.rsAluPushSrc1Robid(1) := Mux(alu1From1, io.disSrc1Robid(1), io.disSrc1Robid(0))
  io.rsAluPushImm(1) := Mux(alu1From1, io.disImm(1), io.disImm(0))
  io.rsAluPushUseImm(1) := Mux(alu1From1, io.disUseImm(1), io.disUseImm(0))
  io.rsAluPushBrOffs(1) := Mux(alu1From1, io.disBrOffs(1), io.disBrOffs(0))
  io.rsAluPushPredTaken(1) := Mux(alu1From1, io.disPredTaken(1), io.disPredTaken(0))
  io.rsAluPushFtqId(1) := Mux(alu1From1, io.disFtqId(1), io.disFtqId(0))

  // rs_mem 口 0：恒载最老 MEM
  val memFrom1 = isMem(1) && io.disFire(1)
  val memSingleFrom1 = memFrom1 && !willTakeMem(0)
  io.rsMemPushValid(0) := (isMem(0) && io.disFire(0)) ||
    (isMem(1) && io.disFire(1) && !willTakeMem(0))
  io.rsMemPushRobid(0) := Mux(memSingleFrom1, io.disRobid(1), io.disRobid(0))
  io.rsMemPushMemOp(0) := Mux(memSingleFrom1, io.disMemOp(1), io.disMemOp(0))
  io.rsMemPushSrc0Ready(0) := Mux(memSingleFrom1, s0Ready(1), s0Ready(0))
  io.rsMemPushSrc0Val(0) := Mux(memSingleFrom1, s0Val(1), s0Val(0))
  io.rsMemPushSrc0Robid(0) := Mux(memSingleFrom1, io.disSrc0Robid(1), io.disSrc0Robid(0))
  io.rsMemPushSrc0KeyVal(0) := Mux(memSingleFrom1, s0KeyVal(1), s0KeyVal(0))
  io.rsMemPushSrc0RobWait(0) := Mux(memSingleFrom1, !io.disSrc0Ready(1), !io.disSrc0Ready(0))
  io.rsMemPushSrc1Ready(0) := Mux(memSingleFrom1, s1Ready(1), s1Ready(0))
  io.rsMemPushSrc1Val(0) := Mux(memSingleFrom1, s1Val(1), s1Val(0))
  io.rsMemPushSrc1Robid(0) := Mux(memSingleFrom1, io.disSrc1Robid(1), io.disSrc1Robid(0))
  io.rsMemPushImm(0) := Mux(memSingleFrom1, io.disImm(1), io.disImm(0))

  // rs_mem 口 1：仅 MEM/MEM 对
  io.rsMemPushValid(1) := (isMem(1) && io.disFire(1) && willTakeMem(0))
  io.rsMemPushRobid(1) := io.disRobid(1)
  io.rsMemPushMemOp(1) := io.disMemOp(1)
  io.rsMemPushSrc0Ready(1) := s0Ready(1)
  io.rsMemPushSrc0Val(1) := s0Val(1)
  io.rsMemPushSrc0Robid(1) := io.disSrc0Robid(1)
  io.rsMemPushSrc0KeyVal(1) := s0KeyVal(1)
  io.rsMemPushSrc0RobWait(1) := !io.disSrc0Ready(1)
  io.rsMemPushSrc1Ready(1) := s1Ready(1)
  io.rsMemPushSrc1Val(1) := s1Val(1)
  io.rsMemPushSrc1Robid(1) := io.disSrc1Robid(1)
  io.rsMemPushImm(1) := io.disImm(1)

  // rs_mdu：zimm 注入 src0
  val mduFrom1 = isMdu(1) && io.disFire(1)
  io.rsMduPushValid := (isMdu(0) && io.disFire(0)) || mduFrom1
  io.rsMduPushRobid := Mux(mduFrom1, io.disRobid(1), io.disRobid(0))
  io.rsMduPushAluOpMdu := Mux(mduFrom1, io.disAluOp(1)(18, 12), io.disAluOp(0)(18, 12))
  io.rsMduPushCsrOp := Mux(mduFrom1, io.disCsrOp(1), io.disCsrOp(0))
  io.rsMduPushCsrNum := Mux(mduFrom1, io.disCsrNum(1), io.disCsrNum(0))
  val mduUsesImm = Mux(mduFrom1, io.disUseImm(1), io.disUseImm(0))
  val mduImm = Mux(mduFrom1, io.disImm(1), io.disImm(0))
  io.rsMduPushSrc0Ready := mduUsesImm ||
    Mux(mduFrom1, s0Ready(1), s0Ready(0))
  io.rsMduPushSrc0Val := Mux(mduUsesImm, mduImm,
    Mux(mduFrom1, s0Val(1), s0Val(0)))
  io.rsMduPushSrc0Robid := Mux(mduFrom1, io.disSrc0Robid(1), io.disSrc0Robid(0))
  io.rsMduPushSrc1Ready := Mux(mduFrom1, s1Ready(1), s1Ready(0))
  io.rsMduPushSrc1Val := Mux(mduFrom1, s1Val(1), s1Val(0))
  io.rsMduPushSrc1Robid := Mux(mduFrom1, io.disSrc1Robid(1), io.disSrc1Robid(0))
}
