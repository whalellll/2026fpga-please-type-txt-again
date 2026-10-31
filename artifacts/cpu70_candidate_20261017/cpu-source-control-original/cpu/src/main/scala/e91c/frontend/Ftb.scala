// ============================================================
// e91c.frontend.Ftb — cpu/ftb.v 的 Chisel 移植（取指目标缓冲）
// ------------------------------------------------------------
// 参数化路数 x 1024 组；查询 1 拍延迟；更新走「训练 FIFO(32) + U0 借读口 + U1 写回」，
// 查询永不被作废。条目 {valid, tag(20), btype(2), len(3), fall(32), target(32)}。
// 移植说明：
// - way 体用 Mem 实现"读旧值再写"的简单双口语义（与原模板
//   rdata<=mem[raddr]; if(we) mem[waddr]<=wdata 完全一致，且读=旧值）；
// - 原 initing 逐组清零逻辑在 RTL 里被复位恒 0 禁用（存储靠上电清零），
//   这里用初始化文件保留上电清零，initing 死逻辑照抄保留；
// - 命中路/无效路选择 = 最低下标优先（PriorityEncoder 语义与原降序循环一致）。
// ============================================================
package e91c.frontend

import chisel3._
import chisel3.util.experimental.loadMemoryFromFileInline
import chisel3.util.{Cat, Fill, PriorityEncoder, log2Ceil}
import e91c.config.Params.{BLK_LEN_W, BR_TYPE_W, FTB_NSET, FTB_NWAY, FTB_UPDATE_Q_DEPTH}
import e91c.config.Params.{FTB_INDEX_W}

class Ftb extends Module {
  val io = IO(new Bundle {
    val queryValid = Input(Bool())
    val queryPc    = Input(UInt(32.W))
    val hit        = Output(Bool())
    val respValid  = Output(Bool())
    val hitWay     = Output(UInt(2.W))
    val jumpTarget = Output(UInt(32.W))
    val fallThrough = Output(UInt(32.W))
    val brType     = Output(UInt(BR_TYPE_W.W))
    val wayHitOnehot = Output(UInt(FTB_NWAY.W))
    val wayJumpTarget = Output(UInt((FTB_NWAY * 32).W))
    val wayFallThrough = Output(UInt((FTB_NWAY * 32).W))
    val wayBrType = Output(UInt((FTB_NWAY * BR_TYPE_W).W))
    val updateValid = Input(Bool())
    val updateBlockPc = Input(UInt(30.W))     // [31:2] 字地址
    val updateJumpTarget = Input(UInt(32.W))
    val updateFallThrough = Input(UInt(3.W))  // 块内字偏移 [4:2]
    val updateBrType = Input(UInt(BR_TYPE_W.W))
  })

  val TAGW = 32 - 2 - FTB_INDEX_W
  val ENTRY_W = 1 + TAGW + BR_TYPE_W + BLK_LEN_W + 32 + 32
  val LEN_LSB = 64; val BTYPE_LSB = 67; val TAG_LSB = 69

  // ---- 更新流水 U0/U1 寄存器 ----
  val u0Valid = RegInit(false.B)
  val u0PcWord = RegInit(0.U(30.W))
  val u0Target = RegInit(0.U(32.W))
  val u0FtWordoff = RegInit(0.U(BLK_LEN_W.W))
  val u0Btype = RegInit(0.U(BR_TYPE_W.W))
  val u1Valid = RegInit(false.B)
  val u1PcWord = RegInit(0.U(30.W))
  val u1Target = RegInit(0.U(32.W))
  val u1Fall = RegInit(0.U(32.W))
  val u1Btype = RegInit(0.U(BR_TYPE_W.W))
  val u1Len = RegInit(0.U(BLK_LEN_W.W))

  // 注意：原端口 [31:2] 保留 PC 对齐位编号（bit i = pc[i]）。
  // 本移植把字地址存成 30 位压缩值，以下索引按 pc[11:2]=word(9,0) 换算。
  val u0Len = u0FtWordoff - u0PcWord(2, 0)          // 原 u0_pc_word[BLK_LEN_W+1:2]
  val u0FallWord = u0PcWord + u0Len

  val qIndex = io.queryPc(2 + FTB_INDEX_W - 1, 2)
  val u1Index = u1PcWord(FTB_INDEX_W - 1, 0)         // 原 u1_pc_word[2+:INDEX]

  // ---- 复位扫描（原实现中恒不触发，保留结构）----
  val initing = RegInit(false.B)
  val initSet = RegInit(0.U(FTB_INDEX_W.W))

  // ---- 参数化训练 FIFO；深度 1 时指针固定为零 ----
  val QPTR_W = math.max(1, log2Ceil(FTB_UPDATE_Q_DEPTH))
  val QCNT_W = log2Ceil(FTB_UPDATE_Q_DEPTH + 1)
  val uqPcWord = Reg(Vec(FTB_UPDATE_Q_DEPTH, UInt(30.W)))
  val uqTarget = Reg(Vec(FTB_UPDATE_Q_DEPTH, UInt(32.W)))
  val uqFtWordoff = Reg(Vec(FTB_UPDATE_Q_DEPTH, UInt(BLK_LEN_W.W)))
  val uqBtype = Reg(Vec(FTB_UPDATE_Q_DEPTH, UInt(BR_TYPE_W.W)))
  val uqRptr = RegInit(0.U(QPTR_W.W))
  val uqWptr = RegInit(0.U(QPTR_W.W))
  val uqCount = RegInit(0.U(QCNT_W.W))

  val qEmpty = uqCount === 0.U
  val qFull = uqCount === FTB_UPDATE_Q_DEPTH.U
  val serviceUpdate = !initing && !io.queryValid && !qEmpty
  val updateAccept = !initing && io.updateValid
  val uqTailPtr = if (FTB_UPDATE_Q_DEPTH == 1) 0.U(QPTR_W.W) else uqWptr - 1.U
  val updateMatchesTail = !qEmpty && (uqPcWord(uqTailPtr) === io.updateBlockPc)
  val updateTailIsDequeue = serviceUpdate && (uqCount === 1.U)
  val updateMergeTail = updateAccept && updateMatchesTail && !updateTailIsDequeue
  val updateEnqueue = updateAccept && !updateMergeTail && (!qFull || serviceUpdate)
  val updateDequeue = serviceUpdate
  val uqCountNext = Mux(updateEnqueue && !updateDequeue, uqCount + 1.U,
                    Mux(!updateEnqueue && updateDequeue, uqCount - 1.U, uqCount))

  val serviceIndex = uqPcWord(uqRptr)(FTB_INDEX_W - 1, 0)  // 同上按字地址换算
  val rdIndex = Mux(serviceUpdate, serviceIndex, qIndex)

  // ---- 参数化多路存储：Mem（异步读）+ 显式输出寄存器 ----
  // 寄存器在时钟沿采样写之前的旧值 → 精确复刻原模板
  // "rdata<=mem[raddr]; if(we) mem[waddr]<=wdata" 的读旧值（read-first）语义。
  val wayMem = Seq.fill(FTB_NWAY)(Mem(FTB_NSET, UInt(ENTRY_W.W)))
  wayMem.foreach(mem => loadMemoryFromFileInline(mem, "scripts/meminit/zero_1024.hex"))
  val FTB_WAY_W = math.max(1, log2Ceil(FTB_NWAY))
  val victimRr = RegInit(0.U(FTB_WAY_W.W))

  val wrIndex = Mux(initing, initSet, u1Index)
  // 条目拼接：tag = pc[31:(2+INDEX)]；u1PcWord 为 30 位字地址，对应字位 (29, INDEX)
  val u1Tag = u1PcWord(29, FTB_INDEX_W)
  val entryNext = Cat(true.B, u1Tag, u1Btype, u1Len, u1Fall, u1Target)

  val uHitVec = WireDefault(VecInit(Seq.fill(FTB_NWAY)(false.B)))
  val uInvVec = WireDefault(VecInit(Seq.fill(FTB_NWAY)(false.B)))
  val wayRdata = Seq.fill(FTB_NWAY)(Reg(UInt(ENTRY_W.W)))
  for (g <- 0 until FTB_NWAY) {
    wayRdata(g) := wayMem(g).read(rdIndex)   // 沿上采样 = 旧值（read-first）
    uHitVec(g) := wayRdata(g)(ENTRY_W - 1) && (wayRdata(g)(ENTRY_W - 2, TAG_LSB) === u1Tag)
    uInvVec(g) := !wayRdata(g)(ENTRY_W - 1)
  }
  val uFound = uHitVec.asUInt.orR
  val uWay = PriorityEncoder(uHitVec.asUInt)
  val uInvFound = uInvVec.asUInt.orR
  val uInvWay = PriorityEncoder(uInvVec.asUInt)
  val wrWay = Mux(uFound, uWay, Mux(uInvFound, uInvWay, victimRr))

  for (g <- 0 until FTB_NWAY) {
    when(Mux(initing, true.B, u1Valid && (wrWay === g.U))) {
      wayMem(g).write(wrIndex, Mux(initing, 0.U(ENTRY_W.W), entryNext))
    }
  }

  // ---- 查询结果（晚 1 拍）----
  val qValidR = RegInit(false.B)
  val qPcR = Reg(UInt(32.W))
  qValidR := io.queryValid && !initing
  qPcR := io.queryPc

  val qTagR = qPcR(31, 2 + FTB_INDEX_W)
  val qHitVec = WireDefault(VecInit(Seq.fill(FTB_NWAY)(false.B)))
  for (g <- 0 until FTB_NWAY) {
    qHitVec(g) := qValidR && wayRdata(g)(ENTRY_W - 1) &&
                  (wayRdata(g)(ENTRY_W - 2, TAG_LSB) === qTagR)
  }
  val qWay = Mux(qHitVec.asUInt.orR, PriorityEncoder(qHitVec.asUInt), 0.U)
  val wayRdataV = VecInit(wayRdata)   // 硬件动态选路
  val sel = wayRdataV(qWay)

  io.hit := qHitVec.asUInt.orR
  io.respValid := qValidR
  io.hitWay := qWay
  io.jumpTarget := sel(31, 0)
  io.fallThrough := sel(63, 32)
  io.brType := sel(BTYPE_LSB + BR_TYPE_W - 1, BTYPE_LSB)

  // 独热化命中：只保留最低命中路（与 qWay 优先级一致）
  val onehot = WireDefault(VecInit(Seq.fill(FTB_NWAY)(false.B)))
  for (g <- 0 until FTB_NWAY) {
    val lowerMask = if (g == 0) false.B else qHitVec.slice(0, g).foldLeft(false.B)(_ || _)
    onehot(g) := qHitVec(g) && !lowerMask
  }
  io.wayHitOnehot := onehot.asUInt
  val wjt = WireDefault(VecInit(Seq.fill(FTB_NWAY)(0.U(32.W))))
  val wft = WireDefault(VecInit(Seq.fill(FTB_NWAY)(0.U(32.W))))
  val wbt = WireDefault(VecInit(Seq.fill(FTB_NWAY)(0.U(BR_TYPE_W.W))))
  for (g <- 0 until FTB_NWAY) {
    wjt(g) := wayRdata(g)(31, 0)
    wft(g) := wayRdata(g)(63, 32)
    wbt(g) := wayRdata(g)(BTYPE_LSB + BR_TYPE_W - 1, BTYPE_LSB)
  }
  io.wayJumpTarget := wjt.asUInt
  io.wayFallThrough := wft.asUInt
  io.wayBrType := wbt.asUInt

  // ---- 主时序 ----
  when(reset.asBool) {
    u0Valid := false.B; u1Valid := false.B
    victimRr := 0.U; initing := false.B; initSet := 0.U
    uqRptr := 0.U; uqWptr := 0.U; uqCount := 0.U
  }.elsewhen(initing) {
    u0Valid := false.B; u1Valid := false.B
    initSet := initSet + 1.U
    when(initSet === Fill(FTB_INDEX_W, 1.B)) { initing := false.B }
  }.otherwise {
    when(updateMergeTail) {
      uqPcWord(uqTailPtr) := io.updateBlockPc
      uqTarget(uqTailPtr) := io.updateJumpTarget
      uqFtWordoff(uqTailPtr) := io.updateFallThrough
      uqBtype(uqTailPtr) := io.updateBrType
    }.elsewhen(updateEnqueue) {
      uqPcWord(uqWptr) := io.updateBlockPc
      uqTarget(uqWptr) := io.updateJumpTarget
      uqFtWordoff(uqWptr) := io.updateFallThrough
      uqBtype(uqWptr) := io.updateBrType
      if (FTB_UPDATE_Q_DEPTH > 1) { uqWptr := uqWptr + 1.U }
    }
    when(updateDequeue) {
      if (FTB_UPDATE_Q_DEPTH > 1) { uqRptr := uqRptr + 1.U }
    }
    uqCount := uqCountNext

    u0Valid := updateDequeue
    when(updateDequeue) {
      u0PcWord := uqPcWord(uqRptr)
      u0Target := uqTarget(uqRptr)
      u0FtWordoff := uqFtWordoff(uqRptr)
      u0Btype := uqBtype(uqRptr)
    }
    u1Valid := u0Valid
    when(u0Valid) {
      u1PcWord := u0PcWord
      u1Target := u0Target
      u1Fall := Cat(u0FallWord, 0.U(2.W))
      u1Btype := u0Btype
      u1Len := u0Len
    }
    when(u1Valid && !uFound && !uInvFound) { victimRr := victimRr + 1.U }
  }
}
