// ============================================================
// e91c.rename.Rat — cpu/rat.v 的 Chisel 移植（寄存器别名表）
// ------------------------------------------------------------
// 队列式重命名核心映射表：每 GPR 一位 busy + 对应 ROB 编号。
// 移植保持的关键语义：
// - 6 个组合读口，r0 的 busy 恒 0（防御性，写 r0 的 wen 不会来）；
// - 同拍"写口与读口同地址"的 RAW 旁路不在本模块做（rename 在表外
//   比较地址换标签），本模块只提供上一拍结束后的映射视图；
// - 占用写 3 口（wen2 最年轻优先），提交释放 4 口：释放必须
//   (rd, robid) 全匹配才清 busy——只比地址会把"老指令提交"误清
//   "新指令的占用"（队列式重命名最经典的 bug）；
// - 同拍占用与释放同地址：占用优先；flush 时 busy 全清（num 不清）。
// ============================================================
package e91c.rename

import chisel3._
import chisel3.util.MuxCase
import e91c.config.Params.ROB_W

class Rat extends Module {
  val io = IO(new Bundle {
    val flush = Input(Bool())

    // ---- 重命名查询口 x6（组合读）----
    val raddr = Input(Vec(4, UInt(5.W)))
    val rbusy = Output(Vec(4, Bool()))
    val rnum  = Output(Vec(4, UInt(ROB_W.W)))

    // ---- 重命名占用写口 x3（wnum2 最年轻，优先）----
    val wen   = Input(Vec(2, Bool()))
    val waddr = Input(Vec(2, UInt(5.W)))
    val wnum  = Input(Vec(2, UInt(ROB_W.W)))

    // ---- 提交释放口 x4（(addr, num) 全匹配才清）----
    val cmtEn   = Input(Vec(2, Bool()))
    val cmtAddr = Input(Vec(2, UInt(5.W)))
    val cmtNum  = Input(Vec(2, UInt(ROB_W.W)))
  })

  val busy = RegInit(VecInit(Seq.fill(32)(false.B)))
  val num  = RegInit(VecInit(Seq.fill(32)(0.U(ROB_W.W))))

  // 组合读：r0 恒不 busy；num 照常给出（不可观察）
  for (r <- 0 until 4) {
    io.rbusy(r) := Mux(io.raddr(r) === 0.U, false.B, busy(io.raddr(r)))
    io.rnum(r)  := num(io.raddr(r))
  }

  busy(0) := false.B  // 防御性：busy[0] 永远不置 1

  when(reset.asBool || io.flush) {
    for (i <- 0 until 32) {
      busy(i) := false.B
      num(i)  := 0.U
    }
  }.otherwise {
    for (i <- 1 until 32) {
      val allocHit = io.wen.zip(io.waddr)
        .map { case (en, a) => en && (a === i.U) }.reduce(_ || _)
      // 年轻者优先：wen2 > wen1 > wen0
      val allocNum = MuxCase(0.U, Seq(
        (io.wen(1) && io.waddr(1) === i.U) -> io.wnum(1),
        (io.wen(0) && io.waddr(0) === i.U) -> io.wnum(0)
      ))
      // 释放：地址与编号都匹配（cmt0~3 任一）
      val releaseHit = io.cmtEn.zip(io.cmtAddr).zip(io.cmtNum)
        .map { case ((en, a), n) => en && (a === i.U) && (n === num(i)) }.reduce(_ || _)

      when(allocHit) {
        busy(i) := true.B
        num(i)  := allocNum
      }.elsewhen(releaseHit) {
        busy(i) := false.B
      }
    }
  }
}
