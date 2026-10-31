// ============================================================
// e91c.frontend.InstBuffer — cpu/inst_buffer.v 的 Chisel 移植
// ------------------------------------------------------------
// 参数化指令缓冲：4 bank；入 4/拍、出 3/拍。
// 移植保持的关键语义：
// - one-hot 占用计数（count_oh）+ 移位更新表；can_push 只依赖寄存状态
//   （= |count_oh[12:0]，预留 4 条空间保守反压）；
// - FWFT 空队直通已常量关断（ib_empty_fwft_en=0），结构照抄保留；
// - 写转向按 tail[1:0] 旋转 bank，跨行写 tail_row_plus1；写数据/使能
//   只依赖 IFU，不经过 rename ready 反馈；
// - 读地址预寄存（bank*_raddr_q + head_bank_q 旋转），出队数据与 valid
//   同拍出自 head 组合读；空环不回卷 head/tail。
// ============================================================
package e91c.frontend

import chisel3._
import chisel3.util.{Cat, MuxLookup}
import e91c.config.Params.{EXCP_NUM, FTQ_W, IB_SIZE, IB_W}

class InstBuffer extends Module {
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val pushValid = Input(Vec(4, Bool()))
    val pushPc = Input(Vec(4, UInt(32.W)))
    val pushInst = Input(Vec(4, UInt(32.W)))
    val pushPredTaken = Input(Vec(4, Bool()))
    val pushIsLast = Input(Vec(4, Bool()))
    val pushFtqId = Input(Vec(4, UInt(FTQ_W.W)))
    val pushExcp = Input(Vec(4, UInt(EXCP_NUM.W)))
    val canPush = Output(Bool())
    val popValid = Output(Vec(2, Bool()))
    val popPc = Output(Vec(2, UInt(32.W)))
    val popInst = Output(Vec(2, UInt(32.W)))
    val popPredTaken = Output(Vec(2, Bool()))
    val popIsLast = Output(Vec(2, Bool()))
    val popFtqId = Output(Vec(2, UInt(FTQ_W.W)))
    val popExcp = Output(Vec(2, UInt(EXCP_NUM.W)))
    val popReady = Input(Vec(2, Bool()))
  })

  val ENTRY_W = EXCP_NUM + FTQ_W + 1 + 1 + 32 + 32   // 76
  val BANK_DEPTH = IB_SIZE / 4

  val bank = Seq.fill(4)(Mem(BANK_DEPTH, UInt(ENTRY_W.W)))
  val head = RegInit(0.U(IB_W.W))
  val tail = RegInit(0.U(IB_W.W))
  val count = RegInit(0.U(chisel3.util.log2Ceil(IB_SIZE + 1).W))
  val headBankQ = RegInit(0.U(2.W))
  val bankRaddrQ = Seq.fill(4)(RegInit(0.U((IB_W - 2).W)))

  def entry(i: Int): UInt = Cat(io.pushExcp(i), io.pushFtqId(i), io.pushIsLast(i),
    io.pushPredTaken(i), io.pushInst(i), io.pushPc(i))

  val pushN = io.pushValid.map(_.asUInt).reduce(_ +& _)   // 0..4（3 位）  val ibEmptyFwftEn = false.B
  val storedPop0ValidC = count =/= 0.U
  val storedPop1ValidC = count >= 2.U
  val canPush = count <= (IB_SIZE - 4).U
  io.canPush := canPush
  val ibEmptyFwftEn = false.B
  val ftActive = ibEmptyFwftEn && count === 0.U && io.pushValid(0) && canPush && !io.flush
  val pop0ValidC = Mux(ftActive, pushN >= 1.U, storedPop0ValidC)
  val pop1ValidC = Mux(ftActive, pushN >= 2.U, storedPop1ValidC)
  val pop0Fire = io.popReady(0) && pop0ValidC
  val pop1Fire = pop0Fire && io.popReady(1) && pop1ValidC
  val popN = Seq(pop0Fire, pop1Fire).map(_.asUInt).reduce(_ +& _)
  val ftConsumeCount = Seq(ftActive && pop0Fire, ftActive && pop1Fire)
    .map(_.asUInt).reduce(_ +& _)
  val storedPopCount = Mux(ftActive, 0.U(2.W), popN(1, 0))   // 恒 2 位（查表键对齐）
  val residualPushCount = Mux(ftActive, pushN - ftConsumeCount, pushN)
  val acceptedPushN = Mux(canPush, residualPushCount, 0.U(3.W))

  // Stored occupancy changes only by accepted pushes and prefix pops.
  val occupancyDelta = acceptedPushN.zext - storedPopCount.zext
  val countNext = Mux(ftActive, residualPushCount, (count.zext + occupancyDelta).asUInt)

  val tailRow = tail(IB_W - 1, 2)
  val tailRowPlus1 = tailRow + 1.U
  val headAdvance = Mux(ftActive, ftConsumeCount(1, 0), storedPopCount)
  val headNext = head + headAdvance
  val headNextRow = headNext(IB_W - 1, 2)
  val headNextRowPlus1 = headNextRow + 1.U

  // 组合读（地址为上一沿预寄存）
  val bankRdata = bank.zip(bankRaddrQ).map { case (m, a) => m.read(a) }
  // 出队条目（地址为预寄存镜像；FWFT 关断时恒走存储路径）
  val pop0EntryC = Mux(ftActive, entry(0), MuxLookup(headBankQ, bankRdata(0))(Seq(
    1.U -> bankRdata(1), 2.U -> bankRdata(2), 3.U -> bankRdata(3))))
  val pop1EntryC = Mux(ftActive, entry(1), MuxLookup(headBankQ, bankRdata(1))(Seq(
    1.U -> bankRdata(2), 2.U -> bankRdata(3), 3.U -> bankRdata(0))))
  for (k <- 0 until 2) {
    val e = Seq(pop0EntryC, pop1EntryC)(k)
    io.popExcp(k) := e(ENTRY_W - 1, ENTRY_W - EXCP_NUM)          // [75:70]
    io.popFtqId(k) := e(ENTRY_W - EXCP_NUM - 1, 66)               // [69:66]
    io.popIsLast(k) := e(65)
    io.popPredTaken(k) := e(64)
    io.popInst(k) := e(63, 32)
    io.popPc(k) := e(31, 0)
    io.popValid(k) := Seq(pop0ValidC, pop1ValidC)(k)
  }

  // ---- 写转向 + 指针/读地址镜像 ----
  when(reset.asBool || io.flush) {
    head := 0.U; tail := 0.U; count := 0.U
    headBankQ := 0.U
    for (b <- 0 until 4) bankRaddrQ(b) := 0.U
  }.otherwise {
    when(canPush) {
      // Each bank receives at most one of the four input slots. Explicitly
      // route that slot before the memory to infer one physical write port.
      for (b <- 0 until 4) {
        val inputIndex = (b.U(2.W) - tail(1, 0))(1, 0)
        val inputPosition = tail(1, 0) +& inputIndex
        val writeValid = io.pushValid(inputIndex)
        val writeRow = Mux(inputPosition(2), tailRowPlus1, tailRow)
        val writeEntry = VecInit((0 until 4).map(i => entry(i)))(inputIndex)
        if (!sys.props.get("e91c.synthesis").contains("true")) {
          for (i <- 0 until 4) {
            val oldPosition = tail(1, 0) +& i.U
            when(io.pushValid(i) && oldPosition(1, 0) === b.U) {
              assert(writeValid && writeEntry === entry(i), "IB rotated input mismatch")
              assert(writeRow === Mux(oldPosition(2), tailRowPlus1, tailRow), "IB rotated row mismatch")
            }
          }
        }
        when(writeValid) { bank(b).write(writeRow, writeEntry) }
      }
    }
    head := headNext
    headBankQ := headNext(1, 0)
    bankRaddrQ(0) := Mux(headNext(1, 0) >= 2.U, headNextRowPlus1, headNextRow)
    bankRaddrQ(1) := Mux(headNext(1, 0) === 3.U, headNextRowPlus1, headNextRow)
    bankRaddrQ(2) := headNextRow
    bankRaddrQ(3) := headNextRow
    when(ftActive || canPush) { tail := tail + pushN(3, 0) }
    count := countNext
  }
}



