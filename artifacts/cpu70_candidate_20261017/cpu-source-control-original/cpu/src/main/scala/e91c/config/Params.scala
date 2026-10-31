// SPDX-License-Identifier: MulanPSL-2.0 或与父本一致
// ============================================================
// e91c.config.Params — cpu/mycpu.h 的 Chisel 化全量参数库
// ------------------------------------------------------------
// 数值与编码逐项对照 mycpu.h；命名保持 snake→camel 的机械映射，
// 迁移期间以"能 diff 回原文件"为第一原则，不做任何语义重构。
// ============================================================
package e91c.config

object Params {
  // Default preserves the V3.5 machine-mode profile. A separate synthesis
  // candidate can enable M/S/U and Sv32 without changing that baseline.
  val ENABLE_SUPERVISOR = sys.props.get("e91c.supervisor").map(_.toBoolean).getOrElse(false)
  // ---- 流水线宽度 ----
  val FETCH_WIDTH = 4      // 取指宽度（基本块最大指令数）
  val BLK_LEN_W   = 3      // 基本块长度位宽（可表示 0~4）

  // ---- 队列深度与派生位宽 ----
  val ROB_SIZE     = 32    // ROB 总项数（奇偶双体 = 16 对 x 2 路）
  val ROB_W        = 5     // ROB 编号位宽 = {奇偶位, 对指针}
  val ROB_PAIR_W   = 4
  val ROB_GUARD    = 1     // head/tail 之间始终保留一对空项
  val PRF_ENTRIES  = 48    // 32 committed mappings + 16 speculative destinations

  // V3.5 candidate: four entries per ALU station reduce dispatch backpressure.
  // The integrated board and routed timing gates remain separate from short RTL screening.
  val RS_ALU_SIZE  = sys.props.get("e91c.aluEntries").map(_.toInt).getOrElse(4)
  val RS_ALU_IDX_W = chisel3.util.log2Ceil(RS_ALU_SIZE)
  val RS_ALU_OCC_W = chisel3.util.log2Ceil(RS_ALU_SIZE + 1)
  val RS_MEM_SIZE  = sys.props.get("e91c.memEntries").map(_.toInt).getOrElse(2)
                          // 单独加深 -0.35%（瓶颈转移到 ALU RS），联合加深 WNS -0.345，回退 2
  val RS_MEM_IDX_W = chisel3.util.log2Ceil(RS_MEM_SIZE)
  val RS_MEM_OCC_W = 3
  val RS_MDU_SIZE  = 2     // 乘除保留站项数（FIFO 顺序发射）

  val SB_SIZE = 2          // 已提交 store 缓冲项数
  val SB_W    = 1

  val FTQ_SIZE = 16        // 取指目标队列项数
  val FTQ_W    = 4
  val IB_SIZE  = 16         // 指令缓冲项数（入<=4/拍，出<=2/拍）
  val IB_W     = 4

  // ---- Cache 几何 ----
  val CACHE_LINE_BYTES = 32
  val CACHE_LINE_BITS  = 256
  val CACHE_LINE_W     = 5

  val ICACHE_NWAY = 2
  val DCACHE_NWAY = 2
  val DC_MSHR_DEPTH   = 1
  val LSU_TOKEN_DEPTH = 4
  val LSU_MISS_DEPTH  = 2 * DC_MSHR_DEPTH

  // ---- 行为开关（与 mycpu.h 宏注释一一对应）----
  val LSU_DC_HIT_BYPASS        = true  // 命中当拍算出 WB 数据
  val LSU_WB_PIPE              = true  // 常规 LSU 写回打一拍
  val RS_ALU_MEM_WB_TURNOVER   = true  // 满 ALU RS 同拍替换
  val LSU_ROB_EARLY_COMPLETE   = true  // ROB 吃 raw 总线
  val ALU_EARLY_WAKEUP_ENABLE  = true  // ALU 发射标签提前送达 RS，缩短次拍写回仲裁路径
  val IFU_FTQ_DIRECT           = true  // PMA 直达时允许同拍 FTQ 请求 ICache
  val STQ_DEPTH                = 16
  val MEM_ISSUE_SCAN_N         = 1
  val TLB_ENTRIES              = 1

  // Each L1 I$/D$: 128 sets x 32 B x 2 ways = 8 KiB (VIPT index+offset=12).
  val L1_NSET    = 128
  val L1_INDEX_W = 7
  val L1_TAG_W   = 20
  // L2: 16KB 1路
  val L2_NWAY    = 1
  val L2_NSET    = 512
  val L2_INDEX_W = 9
  val L2_TAG_W   = 18

  // ---- 分支预测器 ----
  val UBTB_SIZE          = 8    // uBTB 每 bank 项数
  // A 64-set hashed P0 BTB reduces destructive index conflicts without adding a stage.
  val FALLBACK_SETS = sys.props.get("e91c.fallbackSets").map(_.toInt).getOrElse(64)
  val FALLBACK_HASH = sys.props.get("e91c.fallbackHash").map(_.toBoolean).getOrElse(true)
  val FTB_NWAY           = 2
  val FTB_NSET           = 1024
  val FTB_INDEX_W        = 10
  val FTB_UPDATE_Q_DEPTH = 1
  val TAGE_UPDATE_Q_DEPTH = 1
  val TAGE_BASE_DEPTH = 4096
  val TAGE_TAG_DEPTH  = 1024
  val TAGE_TAG_W      = 6
  val TAGE_HIST_LEN   = Seq(4, 10, 24, 64) // Current predictor history lengths.
  val GHR_LEN         = 64
  val RAS_DEPTH       = sys.props.get("e91c.rasDepth").map(_.toInt).getOrElse(2)
  val RAS_W           = chisel3.util.log2Ceil(RAS_DEPTH)
  val BPU_META_W      = 64

  // ---- 编码常量（宽度）----
  val BR_TYPE_W   = 2
  val FU_NUM      = 3
  val FLUSH_TYPE_W = 3
  val PRIV_NUM    = 6
  val EXCP_NUM    = 10
}

/** 分支类型（FTB 条目 / 预译码 / ROB 训练用） */
object BrType {
  val COND   = 0
  val UNCOND = 1
  val CALL   = 2
  val RET    = 3
}

/** FU 类型（决定指令进哪个保留站） */
object FuType {
  val ALU = 0  // 单周期算逻/分支（三个 ALU，乱序发射）
  val MEM = 1  // 访存（LSU：AGU+DC 两级流水，顺序发射）
  val MDU = 2  // 乘除与 CSR 等多周期操作（顺序发射）
}

/** 冲刷类型（commit -> ctrl） */
object FlushType {
  val NONE    = 0
  val MISPRED = 1  // 分支误预测（提交级发现）
  val EXCP    = 2  // 异常或中断
  val MRET    = 3
  val REFETCH = 4  // 串行指令提交后重新取指
}

/** 特权/提交特殊处理类标记（ROB 静态字段，独热；单提交+FLUSH_REFETCH） */
object PrivType {
  val CSR_WR     = 0
  val MRET       = 1
  val CSR_SERIAL = 2
  val FENCE_I    = 3
  val WFI        = 4
  val FENCE      = 5  // 等 SB 排空
}

/** 统一异常向量（ROB 异常字段，独热） */
object Excp {
  val INST_ADDR_MISALIGNED    = 0
  val ILLEGAL_INST            = 1
  val ECALL_M                 = 2
  val BREAKPOINT              = 3
  val LOAD_STORE_MISALIGNED   = 4
  val LOAD_STORE_ACCESS_FAULT = 5
  /** IFU/PMA 取指阶段异常位掩码（与译码 ILLEGAL 去重用） */
  val INST_ACCESS_FAULT = 6
  val INST_PAGE_FAULT = 7
  val LOAD_PAGE_FAULT = 8
  val STORE_PAGE_FAULT = 9
  val FETCH_EXCP_MASK = 0xc1
}

/** 分支/跳转操作码（br_op） */
object BrOp {
  val BEQ  = 0
  val BNE  = 1
  val JALR = 2
  val JAL  = 3
  val BLT  = 4
  val BGE  = 5
  val BLTU = 6
  val BGEU = 7
  val NUM  = 8
}

/**
 * ALU 操作码 —— 紧凑 15 位位序（rs_alu/alu 的 alu_op[14:0]）
 * 位序：{PCADD, ORN, ANDN, LUI..ADD}，去掉了全局编码中的 MDU 空洞。
 */
object AluOpC {
  val ADD   = 0
  val SUB   = 1
  val SLT   = 2
  val SLTU  = 3
  val AND   = 4
  val NOR   = 5
  val OR    = 6
  val XOR   = 7
  val SLL   = 8
  val SRL   = 9
  val SRA   = 10
  val LUI   = 11
  val ANDN  = 12
  val ORN   = 13
  val PCADD = 14
  val WIDTH = 15
}

/** ALU 操作码 —— 全局 22 位独热（decoder 产出，RV32M 类路由到 FU_MDU） */
object AluOpG {
  val ADD  = 0
  val SUB  = 1
  val SLT  = 2
  val SLTU = 3
  val AND  = 4
  val NOR  = 5
  val OR   = 6
  val XOR  = 7
  val SLL  = 8
  val SRL  = 9
  val SRA  = 10
  val LUI  = 11
  val MUL    = 12
  val MULH   = 13
  val MULH_UNSIGNED_B = 14
  val DIV    = 15
  val DIVU   = 16
  val REM    = 17
  val REMU   = 18
  val ANDN = 19
  val ORN  = 20
  val PCADD = 21
  val NUM  = 22
  /** 全局 22 位 → 紧凑 15 位的映射（MDU 位丢弃） */
  def toCompact(g: Int): Int = g match {
    case AluOpG.ANDN  => AluOpC.ANDN
    case AluOpG.ORN   => AluOpC.ORN
    case AluOpG.PCADD => AluOpC.PCADD
    case x if x <= AluOpG.LUI => x
    case _ => AluOpC.ADD // MDU 编码不会送入 alu
  }
}

/** 访存操作码（mem_op，8 位独热） */
object MemOp {
  val ST_W  = 0
  val LD_W  = 1
  val ST_B  = 2
  val ST_H  = 3
  val LD_B  = 4
  val LD_H  = 5
  val LD_BU = 6
  val LD_HU = 7
  val ATOMIC = 8
  val NUM   = 14 // legacy one-hot low byte, atomic flag, funct5
}

/** CSR 指令操作码（csr_op） */
object CsrOp {
  val NONE  = 0
  val READ  = 1
  val WRITE = 2
  val SET   = 4
  val CLEAR = 6
}




