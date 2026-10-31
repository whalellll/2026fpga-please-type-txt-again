// ============================================================
// e91c.frontend.FallbackBtb — cpu/fallback_btb.v 的 Chisel 移植
// ------------------------------------------------------------
// P0 后备 BTB：32 组 x 2 路完整分支描述符。
// 移植保持的关键语义：
// - 路0 优先命中；分配顺序：命中路 > 无效路0 > 无效路1 > replace_way；
// - early 预译码更新：条件分支以弱不跳（01）分配且从不训练计数器，
//   只有 UNCOND/CALL 标记 static_direct；提交更新按已解结果训练；
// - 换类型重写时 static_direct 与计数器整体重置；
// - length==0 或 >FETCH_WIDTH 的训练记录一律拒绝（防零长取指环）。
// ============================================================
package e91c.frontend

import chisel3._
import chisel3.util.{Cat, MuxCase}
import e91c.config.Params.{BLK_LEN_W, BR_TYPE_W, FETCH_WIDTH}
import e91c.config.BrType.{CALL, COND, UNCOND}

class FallbackBtb(val sets: Int = 32, val hashIndex: Boolean = false, val alignment: Int = 2) extends Module {
  val io = IO(new Bundle {
    val queryValid = Input(Bool())
    val queryPc    = Input(UInt(32.W))
    val hit        = Output(Bool())
    val taken      = Output(Bool())
    val target     = Output(UInt(32.W))
    val length     = Output(UInt(BLK_LEN_W.W))
    val brType     = Output(UInt(BR_TYPE_W.W))
    val strongTaken  = Output(Bool())
    val staticDirect = Output(Bool())

    val updValid   = Input(Bool())
    val updBlockPc = Input(UInt(32.W))
    val updTaken   = Input(Bool())
    val updTarget  = Input(UInt(32.W))
    val updLength  = Input(UInt(BLK_LEN_W.W))
    val updBrType  = Input(UInt(BR_TYPE_W.W))
    val updEarly   = Input(Bool())
  })

  require(sets >= 2 && (sets & (sets - 1)) == 0)
  val ENTRY_COUNT = sets
  val INDEX_W = chisel3.util.log2Ceil(sets)
  val TAG_W = 32 - INDEX_W - alignment
  val TARGET_LSB = 0
  val TAG_LSB = TARGET_LSB + 32
  val LENGTH_LSB = TAG_LSB + TAG_W
  val BTYPE_LSB = LENGTH_LSB + BLK_LEN_W
  val DIRECTION_LSB = BTYPE_LSB + BR_TYPE_W
  val STATIC_BIT = DIRECTION_LSB + 2
  val ENTRY_W = STATIC_BIT + 1

  val valid0      = RegInit(VecInit(Seq.fill(ENTRY_COUNT)(false.B)))
  val valid1      = RegInit(VecInit(Seq.fill(ENTRY_COUNT)(false.B)))
  val replaceWay  = RegInit(VecInit(Seq.fill(ENTRY_COUNT)(false.B)))
  val entryMem    = Seq.fill(2)(Mem(ENTRY_COUNT, UInt(ENTRY_W.W)))

  val qIndex = io.queryPc(INDEX_W + alignment - 1, alignment) ^
    (if (hashIndex) io.queryPc(2 * INDEX_W + alignment - 1, INDEX_W + alignment) else 0.U(INDEX_W.W))
  val qTag   = io.queryPc(31, INDEX_W + alignment)
  val qEntry0 = entryMem(0)(qIndex)
  val qEntry1 = entryMem(1)(qIndex)

  val storedHit0 = valid0(qIndex) && (qEntry0(TAG_LSB + TAG_W - 1, TAG_LSB) === qTag)
  val storedHit1 = valid1(qIndex) && (qEntry1(TAG_LSB + TAG_W - 1, TAG_LSB) === qTag)
  val queryWay1 = !storedHit0 && storedHit1
  val queryEntry = Mux(queryWay1, qEntry1, qEntry0)
  val queryDir = queryEntry(DIRECTION_LSB + 1, DIRECTION_LSB)

  io.hit     := io.queryValid && (storedHit0 || storedHit1)
  io.target  := queryEntry(TARGET_LSB + 31, TARGET_LSB)
  io.length  := queryEntry(LENGTH_LSB + BLK_LEN_W - 1, LENGTH_LSB)
  io.brType  := queryEntry(BTYPE_LSB + BR_TYPE_W - 1, BTYPE_LSB)
  io.strongTaken := io.hit && (io.brType === COND.U) && (queryDir === 3.U)
  io.staticDirect := io.hit && queryEntry(STATIC_BIT)
  io.taken  := io.hit && ((io.brType =/= COND.U) || queryDir(1))

  // ---- 更新 ----
  val updIndex = io.updBlockPc(INDEX_W + alignment - 1, alignment) ^
    (if (hashIndex) io.updBlockPc(2 * INDEX_W + alignment - 1, INDEX_W + alignment) else 0.U(INDEX_W.W))
  val updTag   = io.updBlockPc(31, INDEX_W + alignment)

  val updateLengthValid =
    (io.updLength =/= 0.U) && (io.updLength <= FETCH_WIDTH.U)
  val doUpdate = io.updValid && updateLengthValid
  val updEntry0 = entryMem(0)(updIndex)
  val updEntry1 = entryMem(1)(updIndex)

  val updHit0 = valid0(updIndex) && (updEntry0(TAG_LSB + TAG_W - 1, TAG_LSB) === updTag)
  val updHit1 = valid1(updIndex) && (updEntry1(TAG_LSB + TAG_W - 1, TAG_LSB) === updTag)
  val updEntryHit = updHit0 || updHit1
  // 路选择：hit1 > hit0 > 无效路0 > 无效路1 > replace_way
  val waySel = MuxCase(replaceWay(updIndex), Seq(
    updHit1                       -> true.B,
    updHit0                       -> false.B,
    !valid0(updIndex)             -> false.B,
    !valid1(updIndex)             -> true.B
  ))
  val updEntry = Mux(waySel, updEntry1, updEntry0)
  val updSameType = updEntryHit &&
    (updEntry(BTYPE_LSB + BR_TYPE_W - 1, BTYPE_LSB) === io.updBrType)
  // IFU 预译码只把立即数 JAL 分类为 UNCOND/CALL
  val updMarksStatic = io.updEarly &&
    ((io.updBrType === UNCOND.U) || (io.updBrType === CALL.U))

  when(reset.asBool) {
    for (i <- 0 until ENTRY_COUNT) { valid0(i) := false.B; valid1(i) := false.B; replaceWay(i) := false.B }
  }.elsewhen(doUpdate) {
    replaceWay(updIndex) := !waySel
    for (w <- 0 until 2) {
      when(waySel === (w == 1).B) {
        val v = if (w == 0) valid0 else valid1
        val curEntry = if (w == 0) updEntry0 else updEntry1
        val curDir = curEntry(DIRECTION_LSB + 1, DIRECTION_LSB)
        val curStatic = curEntry(STATIC_BIT)
        val trainedDir = Mux(io.updTaken,
          Mux(curDir === 3.U, 3.U(2.W), curDir + 1.U),
          Mux(curDir === 0.U, 0.U(2.W), curDir - 1.U))
        val nextDir = Mux(io.updBrType =/= COND.U, 3.U(2.W),
          Mux(!updSameType,
            Mux(io.updEarly, 1.U(2.W), Mux(io.updTaken, 2.U(2.W), 1.U(2.W))),
            Mux(!io.updEarly, trainedDir, curDir)))
        val nextStatic = Mux(!updSameType, updMarksStatic, curStatic || updMarksStatic)
        val entryNext = Cat(nextStatic, nextDir, io.updBrType, io.updLength, updTag, io.updTarget)
        v(updIndex) := true.B
        entryMem(w).write(updIndex, entryNext)
      }
    }
  }
}
