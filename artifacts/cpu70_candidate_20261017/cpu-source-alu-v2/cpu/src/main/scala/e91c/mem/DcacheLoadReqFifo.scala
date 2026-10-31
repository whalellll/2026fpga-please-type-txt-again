// ============================================================
// e91c.mem.DcacheLoadReqFifo — cpu/dcache_load_req_fifo.v 的 Chisel 移植
// ------------------------------------------------------------
// LSU 与 DCache 之间的 2 项寄存式 load 请求边界：
// - s_ready 只依赖已寄存的占用数，cache 查询/状态反馈不会串进 LSU 流水使能；
// - 空时直通（bypass）保持零额外拍的命中路径；有 1 项积压时同拍 push+pop
//   可维持每拍接受一个 load。
// ============================================================
package e91c.mem

import chisel3._
import e91c.config.Params.ROB_W

class DcacheLoadReqFifo extends Module {
  val io = IO(new Bundle {
    val flush = Input(Bool())
    // LSU 侧（s）
    val sValid    = Input(Bool())
    val sVindex   = Input(UInt(7.W))
    val sPaddr    = Input(UInt(32.W))
    val sSize     = Input(UInt(3.W))
    val sLoadOp   = Input(UInt(4.W))     // 原始 s_load_op_i[7:4]
    val sUncached = Input(Bool())
    val sRobid    = Input(UInt(ROB_W.W))
    val sPairValid = Input(Bool())
    val sPairWord  = Input(UInt(3.W))
    val sPairPaddr = Input(UInt(32.W))
    val sReady    = Output(Bool())
    // DCache 侧（m）
    val mValid    = Output(Bool())
    val mVindex   = Output(UInt(7.W))
    val mPaddr    = Output(UInt(32.W))
    val mSize     = Output(UInt(3.W))
    val mLoadOp   = Output(UInt(4.W))
    val mUncached = Output(Bool())
    val mRobid    = Output(UInt(ROB_W.W))
    val mPairValid = Output(Bool())
    val mPairWord  = Output(UInt(3.W))
    val mPairPaddr = Output(UInt(32.W))
    val mReady    = Input(Bool())
  })

  val rdPtr  = RegInit(false.B)
  val wrPtr  = RegInit(false.B)
  val count  = RegInit(0.U(2.W))
  val vindex    = Reg(Vec(2, UInt(7.W)))
  val paddr     = Reg(Vec(2, UInt(32.W)))
  val size      = Reg(Vec(2, UInt(3.W)))
  val loadOp    = Reg(Vec(2, UInt(4.W)))
  val uncached  = Reg(Vec(2, Bool()))
  val robid     = Reg(Vec(2, UInt(ROB_W.W)))
  val pairValid = Reg(Vec(2, Bool()))
  val pairWord  = Reg(Vec(2, UInt(3.W)))
  val pairPaddr = Reg(Vec(2, UInt(32.W)))

  val empty = count === 0.U
  io.sReady := (count =/= 2.U) && !io.flush
  // 空时直通；cache ready 只决定是否本地捕获，绝不回馈 s_ready
  def mOut[T <: Data](s: T, q: Vec[T]): T = Mux(empty, s, q(rdPtr))
  io.mValid     := Mux(empty, io.sValid, true.B) && !io.flush
  io.mVindex    := mOut(io.sVindex, vindex)
  io.mPaddr     := mOut(io.sPaddr, paddr)
  io.mSize      := mOut(io.sSize, size)
  io.mLoadOp    := mOut(io.sLoadOp, loadOp)
  io.mUncached  := mOut(io.sUncached, uncached)
  io.mRobid     := mOut(io.sRobid, robid)
  io.mPairValid := mOut(io.sPairValid, pairValid)
  io.mPairWord  := mOut(io.sPairWord, pairWord)
  io.mPairPaddr := mOut(io.sPairPaddr, pairPaddr)

  val bypassAccept = empty && io.sValid && io.mReady && !io.flush
  val push = io.sValid && io.sReady && !bypassAccept
  val pop  = !empty && io.mReady && !io.flush

  when(reset.asBool || io.flush) {
    rdPtr := false.B; wrPtr := false.B; count := 0.U
  }.otherwise {
    when(push) {
      vindex(wrPtr)    := io.sVindex
      paddr(wrPtr)     := io.sPaddr
      size(wrPtr)      := io.sSize
      loadOp(wrPtr)    := io.sLoadOp
      uncached(wrPtr)  := io.sUncached
      robid(wrPtr)     := io.sRobid
      pairValid(wrPtr) := io.sPairValid
      pairWord(wrPtr)  := io.sPairWord
      pairPaddr(wrPtr) := io.sPairPaddr
      wrPtr := !wrPtr
    }
    when(pop) { rdPtr := !rdPtr }
    when(push && !pop) { count := count + 1.U }
      .elsewhen(!push && pop) { count := count - 1.U }
  }
}
