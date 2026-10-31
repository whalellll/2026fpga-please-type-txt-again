// ============================================================
// e91c.frontend.FallbackBtb — cpu/fallback_btb.v 的 Chisel 移植
// ------------------------------------------------------------
// P0 后备 BTB：仅在 uBTB miss 时查询，32 组 x 2 路完整分支描述符。
// 移植保持的关键语义：
// - 路0 优先命中；分配顺序：命中路 > 无效路0 > 无效路1 > replace_way；
// - early 预译码更新：条件分支以弱不跳（01）分配且从不训练计数器，
//   只有 UNCOND/CALL 标记 static_direct；提交更新按已解结果训练；
// - 换类型重写时 static_direct 与计数器整体重置；
// - length==0 或 >FETCH_WIDTH 的训练记录一律拒绝（防零长取指环）。
// ============================================================
package e91c.frontend

import chisel3._
import chisel3.util.MuxCase
import e91c.config.Params.{BLK_LEN_W, BR_TYPE_W, FETCH_WIDTH}
import e91c.config.BrType.{CALL, COND, UNCOND}

class FallbackBtbReference extends Module {
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

  val ENTRY_COUNT = 32
  val INDEX_W = 5
  val TAG_W = 32 - INDEX_W - 2

  val valid0      = RegInit(VecInit(Seq.fill(ENTRY_COUNT)(false.B)))
  val valid1      = RegInit(VecInit(Seq.fill(ENTRY_COUNT)(false.B)))
  val replaceWay  = RegInit(VecInit(Seq.fill(ENTRY_COUNT)(false.B)))
  val tagMem      = Seq.fill(2)(Reg(Vec(ENTRY_COUNT, UInt(TAG_W.W))))
  val targetMem   = Seq.fill(2)(Reg(Vec(ENTRY_COUNT, UInt(32.W))))
  val lengthMem   = Seq.fill(2)(Reg(Vec(ENTRY_COUNT, UInt(BLK_LEN_W.W))))
  val btypeMem    = Seq.fill(2)(Reg(Vec(ENTRY_COUNT, UInt(BR_TYPE_W.W))))
  val directionMem= Seq.fill(2)(Reg(Vec(ENTRY_COUNT, UInt(2.W))))
  val staticDirectMem = Seq.fill(2)(Reg(Vec(ENTRY_COUNT, Bool())))

  val qIndex = io.queryPc(INDEX_W + 1, 2)
  val qTag   = io.queryPc(31, INDEX_W + 2)

  val storedHit0 = valid0(qIndex) && (tagMem(0)(qIndex) === qTag)
  val storedHit1 = valid1(qIndex) && (tagMem(1)(qIndex) === qTag)
  val queryWay1 = !storedHit0 && storedHit1
  val queryDir = Mux(queryWay1, directionMem(1)(qIndex), directionMem(0)(qIndex))

  io.hit     := io.queryValid && (storedHit0 || storedHit1)
  io.target  := Mux(queryWay1, targetMem(1)(qIndex), targetMem(0)(qIndex))
  io.length  := Mux(queryWay1, lengthMem(1)(qIndex), lengthMem(0)(qIndex))
  io.brType  := Mux(queryWay1, btypeMem(1)(qIndex), btypeMem(0)(qIndex))
  io.strongTaken := io.hit && (io.brType === COND.U) && (queryDir === 3.U)
  io.staticDirect := io.hit &&
    Mux(queryWay1, staticDirectMem(1)(qIndex), staticDirectMem(0)(qIndex))
  io.taken  := io.hit && ((io.brType =/= COND.U) || queryDir(1))

  // ---- 更新 ----
  val updIndex = io.updBlockPc(INDEX_W + 1, 2)
  val updTag   = io.updBlockPc(31, INDEX_W + 2)

  val updateLengthValid =
    (io.updLength =/= 0.U) && (io.updLength <= FETCH_WIDTH.U)
  val doUpdate = io.updValid && updateLengthValid

  val updHit0 = valid0(updIndex) && (tagMem(0)(updIndex) === updTag)
  val updHit1 = valid1(updIndex) && (tagMem(1)(updIndex) === updTag)
  val updEntryHit = updHit0 || updHit1
  // 路选择：hit1 > hit0 > 无效路0 > 无效路1 > replace_way
  val waySel = MuxCase(replaceWay(updIndex), Seq(
    updHit1                       -> true.B,
    updHit0                       -> false.B,
    !valid0(updIndex)             -> false.B,
    !valid1(updIndex)             -> true.B
  ))
  val updSameType = updEntryHit &&
    (Mux(waySel, btypeMem(1)(updIndex), btypeMem(0)(updIndex)) === io.updBrType)
  // IFU 预译码只把立即数 JAL 分类为 UNCOND/CALL
  val updMarksStatic = io.updEarly &&
    ((io.updBrType === UNCOND.U) || (io.updBrType === CALL.U))

  when(reset.asBool) {
    for (i <- 0 until ENTRY_COUNT) { valid0(i) := false.B; valid1(i) := false.B; replaceWay(i) := false.B }
  }.elsewhen(doUpdate) {
    replaceWay(updIndex) := !waySel
    for (w <- 0 until 2) {
      when(waySel === (w == 1).B) {
        val v    = if (w == 0) valid0 else valid1
        val tg   = tagMem(w); val ta = targetMem(w); val ln = lengthMem(w)
        val bt   = btypeMem(w); val dr = directionMem(w); val sd = staticDirectMem(w)
        v(updIndex)      := true.B
        tg(updIndex)     := updTag
        ta(updIndex)     := io.updTarget
        ln(updIndex)     := io.updLength
        bt(updIndex)     := io.updBrType
        when(!updSameType) {
          sd(updIndex) := updMarksStatic
        }.elsewhen(updMarksStatic) {
          sd(updIndex) := true.B
        }
        val cur = dr(updIndex)
        when(io.updBrType =/= COND.U) {
          dr(updIndex) := 3.U(2.W)
        }.elsewhen(!updSameType) {
          // 换类型重写：early 弱不跳，提交 taken 强/弱
          dr(updIndex) := Mux(io.updEarly, 1.U(2.W), Mux(io.updTaken, 2.U(2.W), 1.U(2.W)))
        }.elsewhen(!io.updEarly) {
          // 已有条目只被提交结果训练
          dr(updIndex) := Mux(io.updTaken,
            Mux(cur === 3.U, 3.U(2.W), cur + 1.U),
            Mux(cur === 0.U, 0.U(2.W), cur - 1.U))
        }
      }
    }
  }
}
