// ============================================================
// e91c.backend.RsAlu — cpu/rs_alu.v 的 Chisel 移植（ALU 保留站，乱序发射）
// ------------------------------------------------------------
// E91 联合仲裁本体。端口/结构与原文件一一对应。
// 移植保持的结构决策：
// - 精确成对年龄矩阵 older[a][b]：仅在槽重分配时写行/列，发射不改矩阵；
// - 联合仲裁：fast 阻挡项 = (base∪fast) 中更老者；fast 赢家额外要求自身
//   非 base 候选（即并集赢家非 base 就绪），事后 N×N 比较整个消除；
//   fast2_valid 只做最终选择器，绝不进阻挡归约；
// - 6 路写回 + MDU 提前一拍令牌（s*_mdu_due）+ early（只置 ready）；
// - WB 捕获按 wb0>1>2>3(mdu_due)>4>5 优先级；已寄存 wb2/wb5 可同拍 admit，
//   其中 wb2 的 speculative-cancel 消费者仍保持先捕获再发射；
// - 满站同拍替换：age_alloc_grant 空槽优先否则发射槽；can_accept 寄存
//   预览（state_next_valid/turnover）；
// - 立即数紧凑存储（20 位）+ 发射拍重建符号/对齐。
// ============================================================
package e91c.backend

import chisel3._
import chisel3.util.{Cat, Fill, MuxCase, PriorityEncoder, log2Ceil}
import e91c.config.Params.{FTQ_W, ROB_W}
import e91c.config.{AluOpC, BrOp}

class RsAlu(val RS_DEPTH: Int = e91c.config.Params.RS_ALU_SIZE) extends Module {
  private val OCC_W = log2Ceil(RS_DEPTH + 1)
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val pushValid = Input(Bool())
    val pushRobid = Input(UInt(ROB_W.W))
    val pushPc = Input(UInt(32.W))
    val pushAluOp = Input(UInt(AluOpC.WIDTH.W))
    val pushBrOp = Input(UInt(BrOp.NUM.W))
    val pushSrc0Ready = Input(Bool())
    val pushSrc0Val = Input(UInt(32.W))
    val pushSrc0Robid = Input(UInt(ROB_W.W))
    val pushSrc1Ready = Input(Bool())
    val pushSrc1Val = Input(UInt(32.W))
    val pushSrc1Robid = Input(UInt(ROB_W.W))
    val pushImm = Input(UInt(32.W))
    val pushUseImm = Input(Bool())
    val pushBrOffs = Input(UInt(32.W))
    val pushPredTaken = Input(Bool())
    val pushFtqId = Input(UInt(FTQ_W.W))
    val canAccept = Output(Bool())
    val occupancy = Output(UInt(OCC_W.W))
    // 6 路写回
    val wbValid = Input(Vec(5, Bool()))
    val wbRobid = Input(Vec(5, UInt(ROB_W.W)))
    val wbData = Input(Vec(5, UInt(32.W)))
    val fast2Valid = Input(Bool())
    val fast2Robid = Input(UInt(ROB_W.W))
    val fast2Data = Input(UInt(32.W))
    val pre3Valid = Input(Bool())
    val pre3Robid = Input(UInt(ROB_W.W))
    val earlyValid = Input(Vec(3, Bool()))
    val earlyRobid = Input(Vec(3, UInt(ROB_W.W)))
    val issueValid = Output(Bool())
    val issueRobid = Output(UInt(ROB_W.W))
    val issuePc = Output(UInt(32.W))
    val issueAluOp = Output(UInt(AluOpC.WIDTH.W))
    val issueBrOp = Output(UInt(BrOp.NUM.W))
    val issueSrc0 = Output(UInt(32.W))
    val issueSrc1 = Output(UInt(32.W))
    val issueImm = Output(UInt(32.W))
    val issueUseImm = Output(Bool())
    val issueBrOffs = Output(UInt(32.W))
    val issuePredTaken = Output(Bool())
    val issueFtqId = Output(UInt(FTQ_W.W))
    val speculativeSelect = Output(Bool())
    val speculativeCancel = Output(Bool())
  })

  val IDXW = log2Ceil(RS_DEPTH)
  val descriptor = Mem(RS_DEPTH, new Bundle {
    val pc = UInt(31.W)
    val alu = UInt(AluOpC.WIDTH.W)
    val br = UInt(BrOp.NUM.W)
    val aux = UInt(20.W)
    val use = Bool()
    val pred = Bool()
    val ftq = UInt(FTQ_W.W)
  })

  // ---- 每项寄存器 ----
  val valid = Seq.fill(RS_DEPTH)(RegInit(false.B))
  val robid = Seq.fill(RS_DEPTH)(Reg(UInt(ROB_W.W)))
  val s0Ready = Seq.fill(RS_DEPTH)(Reg(Bool()))
  val s0ValValid = Seq.fill(RS_DEPTH)(Reg(Bool()))
  val s0Val = Seq.fill(RS_DEPTH)(Reg(UInt(32.W)))
  val s0Robid = Seq.fill(RS_DEPTH)(Reg(UInt(ROB_W.W)))
  val s1Ready = Seq.fill(RS_DEPTH)(Reg(Bool()))
  val s1ValValid = Seq.fill(RS_DEPTH)(Reg(Bool()))
  val s1Val = Seq.fill(RS_DEPTH)(Reg(UInt(32.W)))
  val s1Robid = Seq.fill(RS_DEPTH)(Reg(UInt(ROB_W.W)))
  val s0MduDue = Seq.fill(RS_DEPTH)(RegInit(false.B))
  val s1MduDue = Seq.fill(RS_DEPTH)(RegInit(false.B))
  val s0AluDue = Seq.fill(RS_DEPTH)(RegInit(0.U(2.W)))
  val s1AluDue = Seq.fill(RS_DEPTH)(RegInit(0.U(2.W)))
  val older = Seq.fill(RS_DEPTH)(Seq.fill(RS_DEPTH)(RegInit(false.B)))
  val turnoverReady = Seq.fill(RS_DEPTH)(RegInit(false.B))
  // Preserve capture-then-issue after a cancelled speculative load. Ordinary
  // consumers may still admit the already-registered wb2 value directly.
  val replayPending = Seq.fill(RS_DEPTH)(RegInit(false.B))

  // ---- push 紧凑立即数 ----
  val pushIsBranch = io.pushBrOp.orR
  val pushIsJalr = io.pushBrOp(BrOp.JALR)
  val pushIsJal = io.pushBrOp(BrOp.JAL)
  val pushIsUImm = io.pushAluOp(AluOpC.LUI) || io.pushAluOp(14)
  val pushCompactAux = MuxCase(io.pushImm(11, 0), Seq(
    pushIsJal -> io.pushBrOffs(20, 1),
    pushIsJalr -> Cat(0.U(8.W), io.pushBrOffs(11, 0)),
    pushIsBranch -> Cat(0.U(8.W), io.pushBrOffs(12, 1)),
    pushIsUImm -> io.pushImm(31, 12)
  ))

  // ---- 唤醒/捕获组合网络（每项每源）----
  def wbMatchGrp(tag: UInt): Seq[Bool] = (0 until 5).map(i =>
    io.wbValid(i) && (io.wbRobid(i) === tag))
  // 槽内捕获数据复用器：wb3 项带 mdu_due 门控（原版 s0_wbdat 语义）；
  // push 侧复用器 wb3 为裸匹配（消费项尚未见过 MDU pre-token）
  def selectWriteback(matches: Seq[Bool]): UInt = {
    val mask = VecInit(matches).asUInt
    val selectedIndex = Mux(mask.orR, PriorityEncoder(mask), 0.U)
    val result = io.wbData(selectedIndex) // consumed only under matching WB-hit enable
    if (!sys.props.get("e91c.synthesis").contains("true")) {
      val reference = MuxCase(0.U, (0 until 5).map(i => matches(i) -> io.wbData(i)))
      val checkArmed = RegNext(true.B, false.B)
      when(checkArmed && mask.orR) { assert(result === reference, "ALU writeback priority mismatch") }
    }
    result
  }
  def wbdatGrp(tag: UInt, dueAlu: UInt, due3: Bool): UInt = selectWriteback(Seq(
    io.wbValid(0) && dueAlu(0),
    io.wbValid(1) && dueAlu(1),
    io.wbValid(2) && (io.wbRobid(2) === tag),
    io.wbValid(3) && due3,
    io.wbValid(4) && (io.wbRobid(4) === tag)
  ))

  val s0WbMatch = Wire(Vec(RS_DEPTH, Bool())); val s1WbMatch = Wire(Vec(RS_DEPTH, Bool()))
  val s0Wbhit = Wire(Vec(RS_DEPTH, Bool())); val s1Wbhit = Wire(Vec(RS_DEPTH, Bool()))
  val s0AdmitWbhit = Wire(Vec(RS_DEPTH, Bool())); val s1AdmitWbhit = Wire(Vec(RS_DEPTH, Bool()))
  val s0Earlyhit = Wire(Vec(RS_DEPTH, Bool())); val s1Earlyhit = Wire(Vec(RS_DEPTH, Bool()))
  val s0Fasttag = Wire(Vec(RS_DEPTH, Bool())); val s1Fasttag = Wire(Vec(RS_DEPTH, Bool()))
  val s0MduPrehit = Wire(Vec(RS_DEPTH, Bool())); val s1MduPrehit = Wire(Vec(RS_DEPTH, Bool()))
  val s0AluPre = Wire(Vec(RS_DEPTH, UInt(2.W)))
  val s1AluPre = Wire(Vec(RS_DEPTH, UInt(2.W)))
  val s0MduIssueDirect = Wire(Vec(RS_DEPTH, Bool())); val s1MduIssueDirect = Wire(Vec(RS_DEPTH, Bool()))
  val s0Wbdat = Wire(Vec(RS_DEPTH, UInt(32.W))); val s1Wbdat = Wire(Vec(RS_DEPTH, UInt(32.W)))

  for (g <- 0 until RS_DEPTH) {
    val m0 = Seq(io.wbValid(0) && s0AluDue(g)(0), io.wbValid(1) && s0AluDue(g)(1)) ++ wbMatchGrp(s0Robid(g)).drop(2)
    val m1 = Seq(io.wbValid(0) && s1AluDue(g)(0), io.wbValid(1) && s1AluDue(g)(1)) ++ wbMatchGrp(s1Robid(g)).drop(2)
    // wb3 项 = wb3_valid && due，无 tag 比较（MDU 单在飞，due 令牌按序对应）
    s0WbMatch(g) := m0(0) || m0(1) || m0(2) || (io.wbValid(3) && s0MduDue(g)) || m0(4)
    s1WbMatch(g) := m1(0) || m1(1) || m1(2) || (io.wbValid(3) && s1MduDue(g)) || m1(4)
    s0Wbhit(g) := !s0ValValid(g) && s0WbMatch(g)
    s1Wbhit(g) := !s1ValValid(g) && s1WbMatch(g)
    s0AluPre(g) := VecInit((0 until 2).map(k =>
      !s0ValValid(g) && io.earlyValid(k) && io.earlyRobid(k) === s0Robid(g))).asUInt
    s1AluPre(g) := VecInit((0 until 2).map(k =>
      !s1ValValid(g) && io.earlyValid(k) && io.earlyRobid(k) === s1Robid(g))).asUInt
    val aluWbValid = Cat(io.wbValid(1), io.wbValid(0))
    val s0AluDueHit = (s0AluDue(g) & aluWbValid).orR
    val s1AluDueHit = (s1AluDue(g) & aluWbValid).orR
    // wb2/wb5 are already registered. wb2 may issue directly unless this entry
    // is recovering from a cancelled speculative selection; wb5 is always safe.
    val a0 = s0AluDueHit || (m0(2) && !replayPending(g)) ||
      (io.wbValid(3) && s0MduDue(g)) || m0(4)
    val a1 = s1AluDueHit || (m1(2) && !replayPending(g)) ||
      (io.wbValid(3) && s1MduDue(g)) || m1(4)
    s0AdmitWbhit(g) := !s0ValValid(g) && a0
    s1AdmitWbhit(g) := !s1ValValid(g) && a1
    s0MduPrehit(g) := !s0ValValid(g) && io.pre3Valid && (io.pre3Robid === s0Robid(g))
    s1MduPrehit(g) := !s1ValValid(g) && io.pre3Valid && (io.pre3Robid === s1Robid(g))
    s0Earlyhit(g) := !s0Ready(g) && !s0Wbhit(g) &&
      ((io.earlyValid(0) && (io.earlyRobid(0) === s0Robid(g))) ||
       (io.earlyValid(1) && (io.earlyRobid(1) === s0Robid(g))) ||
       (io.earlyValid(2) && (io.earlyRobid(2) === s0Robid(g))) || s0MduPrehit(g))
    s1Earlyhit(g) := !s1Ready(g) && !s1Wbhit(g) &&
      ((io.earlyValid(0) && (io.earlyRobid(0) === s1Robid(g))) ||
       (io.earlyValid(1) && (io.earlyRobid(1) === s1Robid(g))) ||
       (io.earlyValid(2) && (io.earlyRobid(2) === s1Robid(g))) || s1MduPrehit(g))
    s0Fasttag(g) := !s0ValValid(g) && (io.fast2Robid === s0Robid(g))
    s1Fasttag(g) := !s1ValValid(g) && (io.fast2Robid === s1Robid(g))
    s0MduIssueDirect(g) := !s0ValValid(g) && io.wbValid(3) && s0MduDue(g) &&
      !m0(0) && !m0(1) && !m0(2)
    s1MduIssueDirect(g) := !s1ValValid(g) && io.wbValid(3) && s1MduDue(g) &&
      !m1(0) && !m1(1) && !m1(2)
    s0Wbdat(g) := wbdatGrp(s0Robid(g), s0AluDue(g), s0MduDue(g))
    s1Wbdat(g) := wbdatGrp(s1Robid(g), s1AluDue(g), s1MduDue(g))
  }

  // ---- 联合仲裁 ----
  val baseCandidate = Wire(Vec(RS_DEPTH, Bool()))
  val fastCandidate = Wire(Vec(RS_DEPTH, Bool()))
  val baseBlocker = Wire(Vec(RS_DEPTH, Vec(RS_DEPTH, Bool())))
  val fastBlocker = Wire(Vec(RS_DEPTH, Vec(RS_DEPTH, Bool())))
  val baseIssueGrant = Wire(Vec(RS_DEPTH, Bool()))
  val fastIssueGrant = Wire(Vec(RS_DEPTH, Bool()))
  for (g <- 0 until RS_DEPTH) {
    baseCandidate(g) := valid(g) &&
      ((s0Ready(g) && s0ValValid(g)) || s0AdmitWbhit(g)) &&
      ((s1Ready(g) && s1ValValid(g)) || s1AdmitWbhit(g))
    fastCandidate(g) := valid(g) &&
      (((s0Ready(g) && s0ValValid(g)) || s0AdmitWbhit(g)) || s0Fasttag(g)) &&
      (((s1Ready(g) && s1ValValid(g)) || s1AdmitWbhit(g)) || s1Fasttag(g)) &&
      (s0Fasttag(g) || s1Fasttag(g))
    for (b <- 0 until RS_DEPTH) {
      baseBlocker(g)(b) := baseCandidate(b) && older(b)(g)
      // E91：并集阻挡——fast 候选同时受普通与快速候选中的更老条目阻挡
      fastBlocker(g)(b) := (baseCandidate(b) || fastCandidate(b)) && older(b)(g)
    }
    baseIssueGrant(g) := baseCandidate(g) && !baseBlocker(g).asUInt.orR
    fastIssueGrant(g) := fastCandidate(g) && !baseCandidate(g) && !fastBlocker(g).asUInt.orR
  }
  val baseIssueValid = baseIssueGrant.asUInt.orR
  val fastIssueValid = fastIssueGrant.asUInt.orR
  val issueUsesFast = io.fast2Valid && fastIssueValid
  // Select a load consumer one cycle before the predicted cache hit. A
  // speculative grant never frees its entry until BOTH operands are validated.
  // A miss, fault or cancelled response therefore replays locally in the RS,
  // without broadcasting poisoned results or flushing independent instructions.
  val predicted = RegInit(VecInit(Seq.fill(RS_DEPTH)(false.B)))
  val predictedOwner = Reg(Vec(RS_DEPTH, UInt(ROB_W.W)))
  val predictCandidate = Wire(Vec(RS_DEPTH, Bool()))
  val validatedPrediction = Wire(Vec(RS_DEPTH, Bool()))
  for (g <- 0 until RS_DEPTH) {
    val p0 = !s0ValValid(g) && io.earlyValid(2) && io.earlyRobid(2) === s0Robid(g)
    val p1 = !s1ValValid(g) && io.earlyValid(2) && io.earlyRobid(2) === s1Robid(g)
    predictCandidate(g) := valid(g) && (p0 || p1) &&
      (s0ValValid(g) || s0Wbhit(g) || p0) && (s1ValValid(g) || s1Wbhit(g) || p1)
    validatedPrediction(g) := predicted(g) && valid(g) && predictedOwner(g) === robid(g) &&
      (s0ValValid(g) || s0Wbhit(g) || (io.fast2Valid && s0Fasttag(g))) &&
      (s1ValValid(g) || s1Wbhit(g) || (io.fast2Valid && s1Fasttag(g)))
  }
  val usePrediction = validatedPrediction.asUInt.orR
  val issueGrant = Wire(Vec(RS_DEPTH, Bool()))
  for (g <- 0 until RS_DEPTH) {
    issueGrant(g) := !io.flush && Mux(usePrediction, validatedPrediction(g),
      Mux(issueUsesFast, fastIssueGrant(g), baseIssueGrant(g)))
    val oldestPrediction = predictCandidate(g) && !(0 until RS_DEPTH).map(b =>
      predictCandidate(b) && older(b)(g)).reduce(_ || _)
    predicted(g) := !io.flush && oldestPrediction && !issueGrant(g)
    when(oldestPrediction) { predictedOwner(g) := robid(g) }
  }
  io.speculativeSelect := predicted.asUInt.orR && !io.flush
  io.speculativeCancel := io.speculativeSelect && !usePrediction
  io.issueValid := issueGrant.asUInt.orR

  // ---- 年龄矩阵分配授权（空槽最低下标优先；满站用发射槽）----
  val ageEmptyGrant = Wire(Vec(RS_DEPTH, Bool()))
  for (g <- 0 until RS_DEPTH) {
    ageEmptyGrant(g) := !valid(g) &&
      (if (g == 0) true.B else ((0 until g).map(k => valid(k)).reduce(_ && _)))
  }
  val ageHasEmpty = ageEmptyGrant.asUInt.orR
  val ageAllocGrant = Wire(Vec(RS_DEPTH, Bool()))
  for (g <- 0 until RS_DEPTH) {
    ageAllocGrant(g) := Mux(ageHasEmpty, ageEmptyGrant(g), issueGrant(g))
  }

  // ---- push 早期令牌 ----
  // Formal writeback data has already passed through the ROB dispatch view;
  // only data-less ALU early and MDU pre-wakeup tokens remain local here.
  val pushS0MduPre = !io.pushSrc0Ready &&
    io.pre3Valid && (io.pre3Robid === io.pushSrc0Robid)
  val pushS1MduPre = !io.pushSrc1Ready &&
    io.pre3Valid && (io.pre3Robid === io.pushSrc1Robid)
  val pushS0Early = !io.pushSrc0Ready &&
    ((io.earlyValid(0) && (io.earlyRobid(0) === io.pushSrc0Robid)) ||
     (io.earlyValid(1) && (io.earlyRobid(1) === io.pushSrc0Robid)) || pushS0MduPre)
  val pushS1Early = !io.pushSrc1Ready &&
    ((io.earlyValid(0) && (io.earlyRobid(0) === io.pushSrc1Robid)) ||
     (io.earlyValid(1) && (io.earlyRobid(1) === io.pushSrc1Robid)) || pushS1MduPre)

  // ---- occupancy / can_accept（寄存预览）----
  val validBits = VecInit(valid.map(_.asUInt)).asUInt
  val occCount = Wire(UInt(OCC_W.W))
  var acc = 0.U(OCC_W.W)
  for (i <- 0 until RS_DEPTH) { acc = acc + valid(i).asUInt }
  occCount := acc
  io.occupancy := occCount

  val pushFire = io.pushValid && io.canAccept
  val pushTurnoverReady = io.pushSrc0Ready && io.pushSrc1Ready

  // 空槽最低下标；满站用发射槽
  val issueGrantU = issueGrant.asUInt
  val issueIdx = Mux(issueGrantU.orR, PriorityEncoder(issueGrantU), 0.U)
  val freeIdx = Mux(ageHasEmpty, PriorityEncoder(ageEmptyGrant.asUInt), issueIdx)

  val stateNextValid = Wire(Vec(RS_DEPTH, Bool()))
  val stateNextTurnover = Wire(Vec(RS_DEPTH, Bool()))
  for (g <- 0 until RS_DEPTH) {
    val slotIsIssue = issueGrant(g)
    val slotIsPush = pushFire && (freeIdx === g.U)
    val slotTurnoverAfterWb =
      (((s0Ready(g) && s0ValValid(g)) || s0Wbhit(g)) &&
       ((s1Ready(g) && s1ValValid(g)) || s1Wbhit(g)))
    stateNextValid(g) := Mux(slotIsPush, true.B, Mux(slotIsIssue, false.B, valid(g)))
    stateNextTurnover(g) := Mux(slotIsPush, pushTurnoverReady,
                           Mux(slotIsIssue, false.B,
                           Mux(valid(g), slotTurnoverAfterWb, false.B)))
  }
  val canAcceptNext = !stateNextValid.asUInt.andR ||
    (stateNextValid.asUInt & stateNextTurnover.asUInt).orR
  val canAcceptQ = RegInit(true.B)
  canAcceptQ := Mux(reset.asBool || io.flush, true.B, canAcceptNext)
  io.canAccept := canAcceptQ

  // ---- 发射载荷 ----
  val s0IssueData = Wire(Vec(RS_DEPTH, UInt(32.W)))
  val s1IssueData = Wire(Vec(RS_DEPTH, UInt(32.W)))
  for (g <- 0 until RS_DEPTH) {
    s0IssueData(g) := Mux(s0MduIssueDirect(g), io.wbData(3),
                      Mux(s0Wbhit(g), s0Wbdat(g), s0Val(g)))
    s1IssueData(g) := Mux(s1MduIssueDirect(g), io.wbData(3),
                      Mux(s1Wbhit(g), s1Wbdat(g), s1Val(g)))
  }
  // base / fast 两赢家先各自解析，fast2_valid 只做最终窄选择
  def pickByGrant(grant: Vec[Bool], data: Vec[UInt]): UInt = {
    val selectedIndex = Mux(grant.asUInt.orR, PriorityEncoder(grant.asUInt), 0.U(IDXW.W))
    val selected = data(selectedIndex)
    if (!sys.props.get("e91c.synthesis").contains("true")) {
      val reference = MuxCase(data(0), (0 until RS_DEPTH).map(i => grant(i) -> data(i)))
      val checkArmed = RegNext(true.B, false.B)
      when(checkArmed) { assert(selected === reference, "ALU RS indexed selection mismatch") }
    }
    selected
  }
  val baseS0 = pickByGrant(baseIssueGrant, s0IssueData)
  val baseS1 = pickByGrant(baseIssueGrant, s1IssueData)
  val fastS0 = pickByGrant(fastIssueGrant, s0IssueData)
  val fastS1 = pickByGrant(fastIssueGrant, s1IssueData)
  val s0FastMatch = fastIssueGrant.asUInt & VecInit((0 until RS_DEPTH).map(g =>
    (s0Fasttag(g) && !s0Wbhit(g)).asUInt)).asUInt
  val s1FastMatch = fastIssueGrant.asUInt & VecInit((0 until RS_DEPTH).map(g =>
    (s1Fasttag(g) && !s1Wbhit(g)).asUInt)).asUInt
  val fastS0Result = Mux(s0FastMatch.orR, io.fast2Data, fastS0)
  val fastS1Result = Mux(s1FastMatch.orR, io.fast2Data, fastS1)
  val selectedS0 = pickByGrant(issueGrant, s0IssueData)
  val selectedS1 = pickByGrant(issueGrant, s1IssueData)
  val selectedFast0 = (issueGrant.asUInt & s0Fasttag.asUInt).orR && io.fast2Valid
  val selectedFast1 = (issueGrant.asUInt & s1Fasttag.asUInt).orR && io.fast2Valid
  io.issueSrc0 := Mux(selectedFast0, io.fast2Data, selectedS0)
  io.issueSrc1 := Mux(selectedFast1, io.fast2Data, selectedS1)

  val descriptorIndex = Mux(issueGrant.asUInt.orR, PriorityEncoder(issueGrant.asUInt), 0.U(IDXW.W))
  val descriptorRead = descriptor(descriptorIndex)
  val descriptorWrite = Wire(chiselTypeOf(descriptorRead))
  descriptorWrite.pc := io.pushPc(31, 1)
  descriptorWrite.alu := io.pushAluOp
  descriptorWrite.br := io.pushBrOp
  descriptorWrite.aux := pushCompactAux
  descriptorWrite.use := io.pushUseImm
  descriptorWrite.pred := io.pushPredTaken
  descriptorWrite.ftq := io.pushFtqId
  when(!reset.asBool && !io.flush && pushFire) { descriptor.write(freeIdx, descriptorWrite) }
  if (!sys.props.get("e91c.synthesis").contains("true")) {
    val oldDescriptor = Reg(Vec(RS_DEPTH, chiselTypeOf(descriptorRead)))
    when(!reset.asBool && !io.flush && pushFire) { oldDescriptor(freeIdx) := descriptorWrite }
    when(io.issueValid) {
      assert(descriptorRead.asUInt === oldDescriptor(descriptorIndex).asUInt, "ALU descriptor Mem mismatch")
    }
  }
  io.issueRobid := pickByGrant(issueGrant, VecInit(robid))
  io.issuePc := Cat(descriptorRead.pc, 0.U(1.W))
  io.issueAluOp := descriptorRead.alu
  io.issueBrOp := descriptorRead.br
  val issueIsBranch = io.issueBrOp.orR
  val issueIsJalr = io.issueBrOp(BrOp.JALR)
  val issueIsJal = io.issueBrOp(BrOp.JAL)
  val issueIsUImm = io.issueAluOp(AluOpC.LUI) || io.issueAluOp(14)
  val auxSel = descriptorRead.aux
  // 无效发射拍观测槽 0（与原 always 循环初值语义一致）
  val useImmSel = descriptorRead.use
  val issueAluImmExpanded = Mux(issueIsUImm,
    Cat(auxSel, 0.U(12.W)), Cat(Fill(20, auxSel(11)), auxSel(11, 0)))
  val issueBrOffsExpanded = Mux(issueIsJal, Cat(Fill(11, auxSel(19)), auxSel, 0.U(1.W)),
                           Mux(issueIsJalr, Cat(Fill(20, auxSel(11)), auxSel(11, 0)),
                               Cat(Fill(19, auxSel(11)), auxSel(11, 0), 0.U(1.W))))
  io.issueImm := Mux(issueIsBranch, 4.U, issueAluImmExpanded)
  io.issueUseImm := useImmSel
  io.issueBrOffs := Mux(issueIsBranch, issueBrOffsExpanded, 0.U)
  io.issuePredTaken := descriptorRead.pred
  io.issueFtqId := descriptorRead.ftq

  // ---- 主时序 ----
  when(reset.asBool || io.flush) {
    for (i <- 0 until RS_DEPTH) {
      valid(i) := false.B; turnoverReady(i) := false.B
      s0MduDue(i) := false.B; s1MduDue(i) := false.B
      s0AluDue(i) := 0.U; s1AluDue(i) := 0.U
      replayPending(i) := false.B
      for (j <- 0 until RS_DEPTH) older(i)(j) := false.B
    }
  }.otherwise {
    for (i <- 0 until RS_DEPTH) {
      when(issueGrant(i)) {
        valid(i) := false.B; turnoverReady(i) := false.B
        s0MduDue(i) := false.B; s1MduDue(i) := false.B
        s0AluDue(i) := 0.U; s1AluDue(i) := 0.U
        replayPending(i) := false.B
      }
      when(predicted(i) && !validatedPrediction(i)) { replayPending(i) := true.B }
      when(valid(i) && !issueGrant(i)) {
        s0AluDue(i) := s0AluPre(i)
        s1AluDue(i) := s1AluPre(i)
        turnoverReady(i) :=
          ((s0Ready(i) && s0ValValid(i)) || s0Wbhit(i)) &&
          ((s1Ready(i) && s1ValValid(i)) || s1Wbhit(i))
        when(s0MduPrehit(i)) { s0MduDue(i) := true.B }
          .elsewhen(io.wbValid(3) && s0MduDue(i)) { s0MduDue(i) := false.B }
        when(s1MduPrehit(i)) { s1MduDue(i) := true.B }
          .elsewhen(io.wbValid(3) && s1MduDue(i)) { s1MduDue(i) := false.B }
        when(s0Wbhit(i)) {
          s0Ready(i) := true.B; s0ValValid(i) := true.B; s0Val(i) := s0Wbdat(i)
        }.elsewhen(s0Earlyhit(i)) { s0Ready(i) := true.B }
        when(s1Wbhit(i)) {
          s1Ready(i) := true.B; s1ValValid(i) := true.B; s1Val(i) := s1Wbdat(i)
        }.elsewhen(s1Earlyhit(i)) { s1Ready(i) := true.B }
      }
    }
    when(pushFire) {
      for (i <- 0 until RS_DEPTH) when(freeIdx === i.U) {
        valid(i) := true.B
        robid(i) := io.pushRobid
        s0Ready(i) := io.pushSrc0Ready || pushS0Early
        s0ValValid(i) := io.pushSrc0Ready
        s0Val(i) := Mux(io.pushSrc0Ready, io.pushSrc0Val, 0.U)
        s0Robid(i) := io.pushSrc0Robid
        s0MduDue(i) := pushS0MduPre
        s0AluDue(i) := VecInit((0 until 2).map(k =>
          !io.pushSrc0Ready && io.earlyValid(k) &&
          io.earlyRobid(k) === io.pushSrc0Robid)).asUInt
        s1Ready(i) := io.pushSrc1Ready || pushS1Early
        s1ValValid(i) := io.pushSrc1Ready
        s1Val(i) := Mux(io.pushSrc1Ready, io.pushSrc1Val, 0.U)
        s1Robid(i) := io.pushSrc1Robid
        s1MduDue(i) := pushS1MduPre
        s1AluDue(i) := VecInit((0 until 2).map(k =>
          !io.pushSrc1Ready && io.earlyValid(k) &&
          io.earlyRobid(k) === io.pushSrc1Robid)).asUInt
        replayPending(i) := false.B
        turnoverReady(i) := pushTurnoverReady
      }
      // 年龄矩阵行/列固定更新
      for (i <- 0 until RS_DEPTH; j <- 0 until RS_DEPTH) {
        when(ageAllocGrant(i)) { older(i)(j) := false.B }
          .elsewhen(ageAllocGrant(j)) { older(i)(j) := valid(i) }
      }
    }
    if (!sys.props.get("e91c.synthesis").contains("true")) {
      when(pushFire && !io.pushSrc0Ready) {
        assert(!wbMatchGrp(io.pushSrc0Robid).reduce(_ || _),
          "Dispatch must expose a same-cycle source-0 writeback before ALU push")
      }
      when(pushFire && !io.pushSrc1Ready) {
        assert(!wbMatchGrp(io.pushSrc1Robid).reduce(_ || _),
          "Dispatch must expose a same-cycle source-1 writeback before ALU push")
      }
    }
  }
}







