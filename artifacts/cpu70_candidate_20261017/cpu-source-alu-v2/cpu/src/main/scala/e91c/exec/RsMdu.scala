// ============================================================
// e91c.exec.RsMdu — cpu/rs_mdu.v 的 Chisel 移植（乘除/CSR 保留站，FIFO 顺序发射）
// ------------------------------------------------------------
// 2 项队列，队头双源就绪且 MDU 空闲即发射。CSR 顺序发射防状态倒置。
// 移植要点：
// - 写回捕获（edge-capture）后下一拍才消费，切断了乘法器输入锥的
//   写回/load 组合路径；
// - 队头发射拍同项不再捕获（`valid[i] && !(issue_fire && i==head)`）；
// - push操作数由Dispatch/ROB当前写回旁路最终化，本模块不重复birth-capture mux；
//   例外：wb(2) 为 LSU raw 视图（早一拍），push 拍撞上时在入站沿直接捕获（135）。
// ============================================================
package e91c.exec

import chisel3._
import chisel3.util.{MuxCase, PriorityEncoder}
import e91c.config.Params.{ROB_W, RS_MDU_SIZE}

class RsMdu extends Module {
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val pushValid = Input(Bool())
    val pushRobid = Input(UInt(ROB_W.W))
    val pushAluOpMdu = Input(UInt(7.W))     // [18:12]
    val pushCsrOp = Input(UInt(3.W))
    val pushCsrNum = Input(UInt(12.W))
    val pushSrc0Ready = Input(Bool())
    val pushSrc0Val = Input(UInt(32.W))
    val pushSrc0Robid = Input(UInt(ROB_W.W))
    val pushSrc1Ready = Input(Bool())
    val pushSrc1Val = Input(UInt(32.W))
    val pushSrc1Robid = Input(UInt(ROB_W.W))
    val canAccept = Output(Bool())
    val occupancy = Output(UInt(2.W))
    val wbValid = Input(Vec(5, Bool()))
    val wbRobid = Input(Vec(5, UInt(ROB_W.W)))
    val wbData = Input(Vec(5, UInt(32.W)))
    val issueValid = Output(Bool())
    val issueRobid = Output(UInt(ROB_W.W))
    val issueAluOpMdu = Output(UInt(7.W))
    val issueCsrOp = Output(UInt(3.W))
    val issueCsrNum = Output(UInt(12.W))
    val issueSrc0 = Output(UInt(32.W))
    val issueSrc1 = Output(UInt(32.W))
    val mduReady = Input(Bool())
  })

  val valid = Seq.fill(RS_MDU_SIZE)(RegInit(false.B))
  val robid = Seq.fill(RS_MDU_SIZE)(Reg(UInt(ROB_W.W)))
  val aluOp = Seq.fill(RS_MDU_SIZE)(Reg(UInt(7.W)))
  val csrOp = Seq.fill(RS_MDU_SIZE)(Reg(UInt(3.W)))
  val csrNum = Seq.fill(RS_MDU_SIZE)(Reg(UInt(12.W)))
  val s0ValValid = Seq.fill(RS_MDU_SIZE)(Reg(Bool()))
  val s0Val = Seq.fill(RS_MDU_SIZE)(Reg(UInt(32.W)))
  val s0Robid = Seq.fill(RS_MDU_SIZE)(Reg(UInt(ROB_W.W)))
  val s1ValValid = Seq.fill(RS_MDU_SIZE)(Reg(Bool()))
  val s1Val = Seq.fill(RS_MDU_SIZE)(Reg(UInt(32.W)))
  val s1Robid = Seq.fill(RS_MDU_SIZE)(Reg(UInt(ROB_W.W)))
  val head = RegInit(false.B)
  val tail = RegInit(false.B)
  val count = RegInit(0.U(2.W))

  // 硬件索引用的 Vec 包装（读）
  val validV = VecInit(valid)
  val robidV = VecInit(robid)
  val aluOpV = VecInit(aluOp)
  val csrOpV = VecInit(csrOp)
  val csrNumV = VecInit(csrNum)
  val s0ValValidV = VecInit(s0ValValid)
  val s0ValV = VecInit(s0Val)
  val s1ValValidV = VecInit(s1ValValid)
  val s1ValV = VecInit(s1Val)

  // 写回捕获网络（每项两源 × 6 总线）
  def wbMatch(t: UInt): Bool =
    (0 until 5).map(i => io.wbValid(i) && (io.wbRobid(i) === t)).reduce(_ || _)
  def wbDat(t: UInt): UInt = {
    val matches = (0 until 5).map(i => io.wbValid(i) && io.wbRobid(i) === t)
    val mask = VecInit(matches).asUInt
    val index = Mux(mask.orR, PriorityEncoder(mask), 0.U)
    val data = io.wbData(index)
    if (!sys.props.get("e91c.synthesis").contains("true")) {
      val reference = MuxCase(0.U, (0 until 5).map(i => matches(i) -> io.wbData(i)))
      val checkArmed = RegNext(true.B, false.B)
      when(checkArmed && mask.orR) { assert(data === reference, "MDU WB priority mismatch") }
    }
    data // all consumers are match-hit guarded
  }

  val s0Wbhit = Wire(Vec(RS_MDU_SIZE, Bool()))
  val s1Wbhit = Wire(Vec(RS_MDU_SIZE, Bool()))
  val s0Wbdat = Wire(Vec(RS_MDU_SIZE, UInt(32.W)))
  val s1Wbdat = Wire(Vec(RS_MDU_SIZE, UInt(32.W)))
  for (g <- 0 until RS_MDU_SIZE) {
    s0Wbhit(g) := !s0ValValid(g) && wbMatch(s0Robid(g))
    s1Wbhit(g) := !s1ValValid(g) && wbMatch(s1Robid(g))
    s0Wbdat(g) := wbDat(s0Robid(g))
    s1Wbdat(g) := wbDat(s1Robid(g))
  }

  io.occupancy := count
  val canAccept = count =/= RS_MDU_SIZE.U
  io.canAccept := canAccept
  val headIdx = Mux(head, 1.U, 0.U)
  val headReady = (count =/= 0.U) && validV(headIdx) &&
                  s0ValValidV(headIdx) && s1ValValidV(headIdx)
  io.issueValid := headReady && io.mduReady
  val issueFire = io.issueValid

  io.issueRobid := robidV(headIdx)
  io.issueAluOpMdu := aluOpV(headIdx)
  io.issueCsrOp := csrOpV(headIdx)
  io.issueCsrNum := csrNumV(headIdx)
  io.issueSrc0 := s0ValV(headIdx)
  io.issueSrc1 := s1ValV(headIdx)

  when(reset.asBool || io.flush) {
    head := false.B; tail := false.B; count := 0.U
    for (i <- 0 until RS_MDU_SIZE) valid(i) := false.B
  }.otherwise {
    // 写回捕获（发射拍队头除外）
    for (i <- 0 until RS_MDU_SIZE) {
      val isHeadIssuing = issueFire && ((i == 1).B === head)
      when(valid(i) && !isHeadIssuing) {
        when(s0Wbhit(i)) { s0ValValid(i) := true.B; s0Val(i) := s0Wbdat(i) }
        when(s1Wbhit(i)) { s1ValValid(i) := true.B; s1Val(i) := s1Wbdat(i) }
      }
    }
    for (i <- 0 until RS_MDU_SIZE) when(issueFire && (headIdx === i.U)) {
      valid(i) := false.B
    }
    when(issueFire) { head := !head }
      val pushFire = io.pushValid && canAccept
      // 135 修复：push 拍若未就绪源恰有总线广播（特别是 wb(2) 的 LSU raw 视图
      // 比 ROB/Dispatch 早一拍、Dispatch 无法同拍终化），必须在入站沿直接捕获，
      // 否则该单拍广播错过即成永久等待（死锁窗口，RS 加深实验的调度下实测触发）。
      // 捕获值只写寄存器 D 入，不进发射选择组合锥，edge-capture 契约不变。
      val pushS0WbHit = !io.pushSrc0Ready && wbMatch(io.pushSrc0Robid)
      val pushS1WbHit = !io.pushSrc1Ready && wbMatch(io.pushSrc1Robid)
      for (i <- 0 until RS_MDU_SIZE) when(pushFire && (Mux(tail, 1.U, 0.U) === i.U)) {
        valid(i) := true.B
        robid(i) := io.pushRobid
        aluOp(i) := io.pushAluOpMdu
        csrOp(i) := io.pushCsrOp
        csrNum(i) := io.pushCsrNum
        s0ValValid(i) := io.pushSrc0Ready || pushS0WbHit
        s0Val(i) := Mux(io.pushSrc0Ready, io.pushSrc0Val,
          Mux(pushS0WbHit, wbDat(io.pushSrc0Robid), 0.U))
        s0Robid(i) := io.pushSrc0Robid
        s1ValValid(i) := io.pushSrc1Ready || pushS1WbHit
        s1Val(i) := Mux(io.pushSrc1Ready, io.pushSrc1Val,
          Mux(pushS1WbHit, wbDat(io.pushSrc1Robid), 0.U))
        s1Robid(i) := io.pushSrc1Robid
      }
      when(pushFire) { tail := !tail }
      when(pushFire && !issueFire) { count := count + 1.U }
        .elsewhen(!pushFire && issueFire) { count := count - 1.U }

      if (!sys.props.get("e91c.synthesis").contains("true")) {
        // 仅要求 ROB 同拍可见的总线（alu0/alu1/mdu/mem2，与 u_rob 写口同源）
        // 在 push 前由 Dispatch 终化；wb(2) 为 LSU raw 视图（早一拍），其
        // push 拍匹配已由上面的入站沿捕获消费，不再构成断言违例。
        def wbMatchVisible(t: UInt): Bool =
          (0 until 5).filter(_ != 2).map(i =>
            io.wbValid(i) && (io.wbRobid(i) === t)).reduce(_ || _)
        when(pushFire && !io.pushSrc0Ready) {
          assert(!wbMatchVisible(io.pushSrc0Robid),
            "Dispatch must expose a same-cycle ROB-visible source-0 writeback before MDU push")
        }
        when(pushFire && !io.pushSrc1Ready) {
          assert(!wbMatchVisible(io.pushSrc1Robid),
            "Dispatch must expose a same-cycle ROB-visible source-1 writeback before MDU push")
        }
      }
  }
}

