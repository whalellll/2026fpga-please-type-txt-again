// ============================================================
// e91c.frontend.Ubtb — cpu/ubtb.v 的 Chisel 移植（bank 选择 uBTB）
// ------------------------------------------------------------
// 移植保持的结构决策：
// - 双 bank x UBTB_SIZE 项全相联；PC 哈希先选 bank 再比 tag，
//   P0 只做单 bank 的 UBTB_SIZE 个比较器；
// - 20 位部分 tag（PC[21:2]），别名由 P1/提交修复；
// - 仅 taken 回跳分支与 RET 在提交时填充；early 预译码更新保留
//   强制接纳行为；已有条目对 taken/not-taken 都训练 2 位计数器；
// - 每 bank 独立轮转替换指针；同 bank 多命中时最低下标优先
//   （PriorityEncoder 语义与原 always 循环一致）。
// ============================================================
package e91c.frontend

import chisel3._
import chisel3.util.{PriorityEncoder, log2Ceil}
import e91c.config.Params.{BLK_LEN_W, BR_TYPE_W, UBTB_SIZE}
import e91c.config.BrType.{COND, RET}

class Ubtb extends Module {
  val io = IO(new Bundle {
    // 组合 P0 查询
    val queryValid = Input(Bool())
    val queryPc    = Input(UInt(32.W))
    val hit        = Output(Bool())
    val retHit     = Output(Bool())
    val taken      = Output(Bool())
    val target     = Output(UInt(32.W))
    val length     = Output(UInt(BLK_LEN_W.W))
    val brType     = Output(UInt(BR_TYPE_W.W))
    // 提交/预译码更新
    val updValid   = Input(Bool())
    val updBlockPc = Input(UInt(32.W))
    val updTag     = Input(UInt(20.W))
    val updBank    = Input(Bool())
    val updTaken   = Input(Bool())
    val updTarget  = Input(UInt(32.W))
    val updLength  = Input(UInt(BLK_LEN_W.W))
    val updBrType  = Input(UInt(BR_TYPE_W.W))
    val updEarly   = Input(Bool())
  })

  val IDX_W = log2Ceil(UBTB_SIZE)

  // 双 bank 存储（bank 用 Scala Int 索引组织，硬件按 one-hot/Vec 选）
  val valid   = Seq.fill(2)(RegInit(VecInit(Seq.fill(UBTB_SIZE)(false.B))))
  val ctr     = Seq.fill(2)(Reg(Vec(UBTB_SIZE, UInt(2.W))))
  val tag     = Seq.fill(2)(Reg(Vec(UBTB_SIZE, UInt(20.W))))
  val targetR = Seq.fill(2)(Mem(UBTB_SIZE, UInt(32.W)))
  val lengthR = Seq.fill(2)(Mem(UBTB_SIZE, UInt(BLK_LEN_W.W)))
  val btypeR  = Seq.fill(2)(Mem(UBTB_SIZE, UInt(BR_TYPE_W.W)))
  val isRet   = Seq.fill(2)(Reg(Vec(UBTB_SIZE, Bool())))
  val replPtr = Seq.fill(2)(RegInit(0.U(IDX_W.W)))

  // 硬件 bank 索引用的 Vec 包装（Scala Seq 不能用硬件信号索引；必须在查询段之前定义）
  val validV   = VecInit(valid)
  val tagV     = VecInit(tag)
  val isRetV   = VecInit(isRet)
  val ctrV     = VecInit(ctr)
  val replPtrV = VecInit(replPtr)

  // ---- 查询：先选 bank，再单 bank 比较 ----
  val qBank = io.queryPc(2) ^ io.queryPc(6) ^ io.queryPc(10) ^
              io.queryPc(14) ^ io.queryPc(18) ^ io.queryPc(22)
  val qTag = io.queryPc(21, 2)
  val qHitBank = Wire(Vec(2, Vec(UBTB_SIZE, Bool())))
  for (b <- 0 until 2; i <- 0 until UBTB_SIZE) {
    qHitBank(b)(i) := valid(b)(i) && (tag(b)(i) === qTag)
  }
  val qHit = qHitBank(qBank)                    // 硬件选 bank
  // 最低命中下标；miss 时强制 0（原 Verilog 循环保持初值 0，
  // target/length/brtype 在 miss 拍仍按 idx0 读出属 don't-care 但黄金会记录）
  val qIdx = Mux(qHit.asUInt.orR, PriorityEncoder(qHit.asUInt), 0.U)

  io.hit    := qHit.asUInt.orR
  io.target := VecInit(targetR.map(m => m(qIdx)))(qBank)
  io.length := VecInit(lengthR.map(m => m(qIdx)))(qBank)
  io.brType := VecInit(btypeR.map(m => m(qIdx)))(qBank)
  io.retHit := VecInit((0 until UBTB_SIZE).map(i => qHitBank(qBank)(i) && isRetV(qBank)(i))).asUInt.orR
  io.taken  := io.hit && ((io.brType =/= COND.U) || ctrV(qBank)(qIdx)(1))

  // ---- 更新 ----
  val doFill = io.updValid && (io.updEarly ||
               (io.updTaken && ((io.updTarget < io.updBlockPc) ||
                (io.updBrType === RET.U))))

  val uHitVec   = Wire(Vec(UBTB_SIZE, Bool()))
  val uInvalid  = Wire(Vec(UBTB_SIZE, Bool()))
  for (i <- 0 until UBTB_SIZE) {
    uHitVec(i)  := validV(io.updBank)(i) && (tagV(io.updBank)(i) === io.updTag)
    uInvalid(i) := !validV(io.updBank)(i)
  }
  val uFound   = uHitVec.asUInt.orR
  val uIdx     = PriorityEncoder(uHitVec.asUInt)
  val invFound = uInvalid.asUInt.orR
  val invIdx   = PriorityEncoder(uInvalid.asUInt)

  val uBankInt = io.updBank.asUInt               // 0/1 硬件 bank 索引
  val fillIdx  = Mux(uFound, uIdx,
                 Mux(invFound, invIdx, replPtrV(io.updBank)))
  // 已有条目对每个已解出的方向都训练（含不入库的 not-taken）
  val doUpdate = doFill || (io.updValid && uFound)

  when(reset.asBool) {
    for (b <- 0 until 2) {
      for (i <- 0 until UBTB_SIZE) valid(b)(i) := false.B
      replPtr(b) := 0.U
    }
  }.elsewhen(doUpdate) {
    for (b <- 0 until 2) {
      when(uBankInt === b.U) {                   // 只有被选中的 bank 更新
        valid(b)(fillIdx)  := true.B
        tag(b)(fillIdx)    := io.updTag
        targetR(b)(fillIdx) := io.updTarget
        lengthR(b)(fillIdx) := io.updLength
        btypeR(b)(fillIdx)  := io.updBrType
        isRet(b)(fillIdx)   := io.updBrType === RET.U
        val cur = ctr(b)(fillIdx)
        when(!uFound) {
          ctr(b)(fillIdx) := Mux(io.updBrType =/= COND.U, 3.U(2.W),
                             Mux(io.updTaken, 2.U(2.W), 1.U(2.W)))
        }.elsewhen(io.updBrType =/= COND.U) {
          ctr(b)(fillIdx) := 3.U(2.W)
        }.elsewhen(io.updTaken && (cur =/= 3.U)) {
          ctr(b)(fillIdx) := cur + 1.U
        }.elsewhen(!io.updTaken && (cur =/= 0.U)) {
          ctr(b)(fillIdx) := cur - 1.U
        }
        when(!uFound && !invFound) {
          replPtr(b) := replPtr(b) + 1.U
        }
      }
    }
  }
  if (!sys.props.get("e91c.synthesis").contains("true")) {
    val oldTarget = Seq.fill(2)(Reg(Vec(UBTB_SIZE, UInt(32.W))))
    val oldLength = Seq.fill(2)(Reg(Vec(UBTB_SIZE, UInt(BLK_LEN_W.W))))
    val oldType = Seq.fill(2)(Reg(Vec(UBTB_SIZE, UInt(BR_TYPE_W.W))))
    when(!reset.asBool && doUpdate) {
      for (b <- 0 until 2) when(uBankInt === b.U) {
        oldTarget(b)(fillIdx) := io.updTarget
        oldLength(b)(fillIdx) := io.updLength
        oldType(b)(fillIdx) := io.updBrType
      }
    }
    when(io.hit) {
      assert(io.target === VecInit(oldTarget)(qBank)(qIdx), "uBTB target storage mismatch")
      assert(io.length === VecInit(oldLength)(qBank)(qIdx), "uBTB length storage mismatch")
      assert(io.brType === VecInit(oldType)(qBank)(qIdx), "uBTB type storage mismatch")
    }
  }
}

