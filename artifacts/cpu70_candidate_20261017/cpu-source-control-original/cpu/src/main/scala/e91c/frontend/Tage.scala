// ============================================================
// e91c.frontend.Tage — cpu/tage.v 的 Chisel 移植（TAGE 方向预测器）
// ------------------------------------------------------------
// 4096 基表 + 4x1024 标记表；查询 1 拍返回；训练经单项 FIFO +
// T0 读表/T1/T2 计算/T3 写回四拍流水；同址读写靠显式前递（t3/t3_last）。
// 移植要点：
// - 基表上电初始化为弱不跳 2'b01（loadMemoryFromFile + .mem 文件）；
// - 标记表双读副本 → 单 Mem + 两个输出寄存器（功能等价，读写均为旧值）；
// - [21:2] 端口 PC 对齐位号：pc[2+:11]=pcW(10,0)、pc[11+:11]=pcW(20,10)、
//   pc[2+:12]=pcW(11,0)；基表索引 pc[2+:12]=pcW(11,0)；
// - 哈希 = 历史位按 (i % W) 折叠 XOR，再混 PC 位（Scala 期静态展开）。
// ============================================================
package e91c.frontend

import chisel3._
import chisel3.util.experimental.loadMemoryFromFileInline
import chisel3.util.{Cat, MuxCase, log2Ceil}
import e91c.config.Params._

class Tage extends Module {
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val queryValid = Input(Bool())
    val queryPc = Input(UInt(20.W))          // pc[21:2]
    val taken = Output(Bool())
    val respValid = Output(Bool())
    val meta = Output(UInt(BPU_META_W.W))
    val trainValid = Input(Bool())
    val trainPc = Input(UInt(20.W))
    val trainTaken = Input(Bool())
    val trainMispred = Input(Bool())
    val trainMeta = Input(UInt(BPU_META_W.W))
    val histCpSave = Input(Bool())
    val histCpId = Input(UInt(FTQ_W.W))
    val histRestore = Input(Bool())
    val histRestoreId = Input(UInt(FTQ_W.W))
    val histRestoreAppend = Input(Bool())
    val histRestoreTaken = Input(Bool())
    val histUpdateValid = Input(Bool())
    val histUpdateTaken = Input(Bool())
    val cmtHistValid = Input(Bool())
    val cmtHistTaken = Input(Bool())
  })

  val BASE_IDXW = 12
  val TIDXW = 10
  val TENTRY_W = 1 + TAGE_TAG_W + 3 + 2      // 18

  // ---- GHR ----
  val specGhr = RegInit(0.U(GHR_LEN.W))
  val commitGhr = RegInit(0.U(GHR_LEN.W))
  val histCp = Mem(FTQ_SIZE, UInt(GHR_LEN.W))
  val queryGhr = Mux(io.histUpdateValid, Cat(specGhr(GHR_LEN - 2, 0), io.histUpdateTaken), specGhr)

  // ---- 哈希（Scala 期静态展开折叠）----
  def foldGroups(hl: Int, w: Int): Seq[Seq[Int]] =
    (0 until w).map(p => (0 until hl).filter(_ % w == p))
  def hashOf(pc: UInt, hist: UInt, hl: Int): (UInt, UInt) = {
    val fIdx = VecInit(foldGroups(hl, TIDXW).map(g => g.map(i => hist(i)).reduceOption(_ ^ _).getOrElse(false.B)).map(_.asUInt))
    val fTag = VecInit(foldGroups(hl, TAGE_TAG_W).map(g => g.map(i => hist(i)).reduceOption(_ ^ _).getOrElse(false.B)).map(_.asUInt))
    // pc[2+:11]=pcW(10,0)；pc[11+:11]=端口位 11..21 = pcW(19,9)（[21:2] 对齐换算）
    (fIdx.asUInt ^ pc(TIDXW - 1, 0) ^ pc(TIDXW + 8, 9),
     fTag.asUInt ^ pc(TAGE_TAG_W - 1, 0))
  }
  val histLens = TAGE_HIST_LEN              // Seq(4,10,24,64)

  // ---- 训练流水寄存器 ----
  val t0Valid = RegInit(false.B)
  val t0Pc = Reg(UInt(20.W)); val t0Taken = Reg(Bool()); val t0Mispred = Reg(Bool())
  val t0Ghr = Reg(UInt(GHR_LEN.W)); val t0Meta = Reg(UInt(BPU_META_W.W))
  val t1Valid = RegInit(false.B)
  val t1Taken = Reg(Bool()); val t1Mispred = Reg(Bool()); val t1Meta = Reg(UInt(BPU_META_W.W))
  val t1AllocIdx = Seq.fill(4)(Reg(UInt(TIDXW.W)))
  val t1AllocTag = Seq.fill(4)(Reg(UInt(TAGE_TAG_W.W)))
  val t1RdEntry = Seq.fill(4)(Reg(UInt(TENTRY_W.W)))
  val t2Valid = RegInit(false.B)
  val t2Taken = Reg(Bool()); val t2Mispred = Reg(Bool()); val t2Meta = Reg(UInt(BPU_META_W.W))
  val t2AllocIdx = Seq.fill(4)(Reg(UInt(TIDXW.W)))
  val t2AllocTag = Seq.fill(4)(Reg(UInt(TAGE_TAG_W.W)))
  val t2RdEntry = Seq.fill(4)(Reg(UInt(TENTRY_W.W)))

  // ---- 训练 FIFO ----
  val QD = TAGE_UPDATE_Q_DEPTH
  val QPW = math.max(1, log2Ceil(QD)); val QCW = log2Ceil(QD + 1)
  val uqPc = Reg(Vec(QD, UInt(20.W)))
  val uqTaken = Reg(Vec(QD, Bool())); val uqMispred = Reg(Vec(QD, Bool()))
  val uqMeta = Reg(Vec(QD, UInt(BPU_META_W.W))); val uqGhr = Reg(Vec(QD, UInt(GHR_LEN.W)))
  val uqRptr = RegInit(0.U(QPW.W)); val uqWptr = RegInit(0.U(QPW.W)); val uqCount = RegInit(0.U(QCW.W))

  val uqEmpty = uqCount === 0.U
  val uqFull = uqCount === QD.U
  val trainReadGrant = !uqEmpty
  val enqueue = io.trainValid && (!uqFull || trainReadGrant)
  val dequeue = trainReadGrant
  val uqCountNext = Mux(enqueue && !dequeue, uqCount + 1.U,
                    Mux(!enqueue && dequeue, uqCount - 1.U, uqCount))

  val uqHeadPc = uqPc(uqRptr); val uqHeadTaken = uqTaken(uqRptr)
  val uqHeadMispred = uqMispred(uqRptr); val uqHeadMeta = uqMeta(uqRptr)
  val uqHeadGhr = uqGhr(uqRptr)
  if (!sys.props.get("e91c.synthesis").contains("true")) {
    val oldPc = Reg(Vec(2, UInt(20.W))); val oldTaken = Reg(Vec(2, Bool()))
    val oldMispred = Reg(Vec(2, Bool())); val oldMeta = Reg(Vec(2, UInt(BPU_META_W.W)))
    val oldGhr = Reg(Vec(2, UInt(GHR_LEN.W)))
    val oldR = RegInit(0.U(1.W)); val oldW = RegInit(0.U(1.W)); val oldCount = RegInit(0.U(2.W))
    val oldDeq = oldCount =/= 0.U
    val oldEnq = io.trainValid && (oldCount =/= 2.U || oldDeq)
    when(!reset.asBool) {
      when(oldEnq) {
        oldPc(oldW) := io.trainPc; oldTaken(oldW) := io.trainTaken
        oldMispred(oldW) := io.trainMispred; oldMeta(oldW) := io.trainMeta
        oldGhr(oldW) := histCp(io.trainMeta(55 + FTQ_W - 1, 55)); oldW := oldW + 1.U
      }
      when(oldDeq) { oldR := oldR + 1.U }
      oldCount := Mux(oldEnq && !oldDeq, oldCount + 1.U, Mux(!oldEnq && oldDeq, oldCount - 1.U, oldCount))
    }
    val checkArmed = RegNext(true.B, false.B)
    when(checkArmed) {
      assert(uqCount <= 1.U && oldCount <= 1.U, "TAGE training occupancy invariant")
      assert(enqueue === oldEnq && dequeue === oldDeq, "TAGE training cadence mismatch")
      when(dequeue) {
        assert(uqHeadPc === oldPc(oldR) && uqHeadTaken === oldTaken(oldR), "TAGE train PC/taken mismatch")
        assert(uqHeadMispred === oldMispred(oldR) && uqHeadMeta === oldMeta(oldR), "TAGE train meta mismatch")
        assert(uqHeadGhr === oldGhr(oldR), "TAGE train history mismatch")
      }
    }
  }
  val uqHeadMetaValid = uqHeadMeta(38)
  val uqHeadPvalid = uqHeadMeta(20)
  val uqHeadPid = uqHeadMeta(22, 21)
  val uqHeadPidx = uqHeadMeta(32, 23)
  val trainFtqId = io.trainMeta(55 + FTQ_W - 1, 55)

  // ---- 哈希例化（查询/队头/T0）----
  val qHash = histLens.map(hl => hashOf(io.queryPc, queryGhr, hl))
  val uqHash = histLens.map(hl => hashOf(uqHeadPc, uqHeadGhr, hl))
  val t0Hash = histLens.map(hl => hashOf(t0Pc, t0Ghr, hl))

  // ---- 存储体 ----
  // 基表需上电初始化为弱不跳 2'b01；treadle 不支持 loadMemoryFromFile，
  // 大 Reg(Vec) 又病态慢 → 拆成 数据 Mem + 已写标志 Mem：
  // 未写过读 01，写过读数据值；初始化文件同时保证导出 RTL 的上电语义。
  val baseDataMem = Mem(TAGE_BASE_DEPTH, UInt(2.W))
  val baseInitMem = Mem(TAGE_BASE_DEPTH, Bool())
  loadMemoryFromFileInline(baseInitMem, "scripts/meminit/zero_4096.hex")
  val qBaseIdx = io.queryPc(BASE_IDXW - 1, 0)
  val baseQDataR = Reg(UInt(2.W)); val baseQInitR = Reg(Bool())
  baseQDataR := baseDataMem.read(qBaseIdx)
  baseQInitR := baseInitMem.read(qBaseIdx)

  val tagMem = Seq.fill(4)(Mem(TAGE_TAG_DEPTH, UInt(TENTRY_W.W)))
  tagMem.foreach(mem => loadMemoryFromFileInline(mem, "scripts/meminit/zero_2048.hex"))
  val tQRdata = Seq.fill(4)(Reg(UInt(TENTRY_W.W)))
  val tTrainRdata = Seq.fill(4)(Reg(UInt(TENTRY_W.W)))
  val t3TWe = RegInit(0.U(4.W))
  val t3TWaddr = Seq.fill(4)(RegInit(0.U(TIDXW.W)))
  val t3TWdata = Seq.fill(4)(RegInit(0.U(TENTRY_W.W)))
  val t3LastTWe = RegInit(0.U(4.W))
  val t3LastTWaddr = Seq.fill(4)(RegInit(0.U(TIDXW.W)))
  val t3LastTWdata = Seq.fill(4)(RegInit(0.U(TENTRY_W.W)))
  val t3BaseWe = RegInit(false.B)
  val t3BaseWaddr = RegInit(0.U(BASE_IDXW.W))
  val t3BaseWdata = RegInit(0.U(2.W))

  for (g <- 0 until 4) {
    val providerReadSel = uqHeadMetaValid && uqHeadPvalid && (uqHeadPid === g.U)
    val trainRaddr = Mux(providerReadSel, uqHeadPidx, uqHash(g)._1)
    tQRdata(g) := tagMem(g).read(qHash(g)._1)
    tTrainRdata(g) := tagMem(g).read(trainRaddr)
    when(t3TWe(g)) { tagMem(g).write(t3TWaddr(g), t3TWdata(g)) }
  }
  when(t3BaseWe) { baseDataMem.write(t3BaseWaddr, t3BaseWdata); baseInitMem.write(t3BaseWaddr, true.B) }

  // ---- 查询响应（晚 1 拍）----
  val qValidR = RegInit(false.B)
  val qTagR = Seq.fill(4)(Reg(UInt(TAGE_TAG_W.W)))
  val qIdxR = Seq.fill(4)(Reg(UInt(TIDXW.W)))
  val qBidxR = Reg(UInt(BASE_IDXW.W))
  val qBaseFwdValidR = RegInit(false.B)
  val qBaseFwdDataR = Reg(UInt(2.W))
  val useAltOnNa = RegInit(0.U(4.W))

  qValidR := io.queryValid
  for (g <- 0 until 4) { qTagR(g) := qHash(g)._2; qIdxR(g) := qHash(g)._1 }
  qBidxR := qBaseIdx
  qBaseFwdValidR := t3BaseWe && (t3BaseWaddr === qBaseIdx)
  qBaseFwdDataR := t3BaseWdata

  val tQEntryEff = tQRdata                          // 直接用 BRAM 结果（无前递）
  val thitV = WireDefault(VecInit(Seq.fill(4)(false.B)))
  for (g <- 0 until 4) {
    thitV(g) := qValidR && tQEntryEff(g)(TENTRY_W - 1) && (tQEntryEff(g)(TENTRY_W - 2, TENTRY_W - 1 - TAGE_TAG_W) === qTagR(g))
  }
  val thit = thitV.asUInt
  val provValid = thit.orR
  val provId = Mux(thit(3), 3.U, Mux(thit(2), 2.U, Mux(thit(1), 1.U, 0.U)))
  val provEntry = VecInit(tQEntryEff)(provId)
  val provCtr = provEntry(4, 2)
  val provU = provEntry(1, 0)
  val provTag = provEntry(TENTRY_W - 2, TENTRY_W - 1 - TAGE_TAG_W)
  val baseQRdata = Mux(baseQInitR, baseQDataR, 1.U(2.W))   // 未写过 → 弱不跳 01
  val baseQEff = Mux(qBaseFwdValidR, qBaseFwdDataR, baseQRdata)
  val baseTaken = baseQEff(1)

  // 备选 = 次长命中表
  val altTaken = MuxCase(baseTaken, Seq(
    (provId === 3.U && thit(2)) -> tQEntryEff(2)(4),
    (provId === 3.U && !thit(2) && thit(1)) -> tQEntryEff(1)(4),
    (provId === 3.U && !thit(2) && !thit(1) && thit(0)) -> tQEntryEff(0)(4),
    (provId === 2.U && thit(1)) -> tQEntryEff(1)(4),
    (provId === 2.U && !thit(1) && thit(0)) -> tQEntryEff(0)(4),
    (provId === 1.U && thit(0)) -> tQEntryEff(0)(4)
  ))
  val provWeak = (provCtr === 3.U) || (provCtr === 4.U)
  val useAltPred = provValid && provWeak && (provU === 0.U) && (useAltOnNa >= 2.U)
  val tageFinalTaken = Mux(provValid, Mux(useAltPred, altTaken, provCtr(2)), baseTaken)

  io.respValid := qValidR
  io.taken := qValidR && tageFinalTaken

  // meta 打包
  val metaRaw = Cat(provU, provCtr, VecInit(qIdxR)(provId)(9, 0), provId, provValid,
                    altTaken, baseQEff, 0.U(1.W), qBidxR, thit)
  val metaTag = provTag << 43
  io.meta := Mux(qValidR, metaRaw | metaTag, 0.U)

  // ---- T2 meta 解包 ----
  val mBaseIdx = t2Meta(15, 4)
  val mBaseCtr = t2Meta(18, 17)
  val mAlt = t2Meta(19)
  val mPvalid = t2Meta(20)
  val mPid = t2Meta(22, 21)
  val mPidx = t2Meta(32, 23)
  val mPctr = t2Meta(35, 33)
  val mPu = t2Meta(37, 36)
  val mPtag = t2Meta(43 + TAGE_TAG_W - 1, 43)

  // T2 RAW 前递：t3(本沿写入) > t3_last(上沿写入) > 表读
  val t2ReadIdx = Wire(Vec(4, UInt(TIDXW.W)))
  val t2RdEff = Wire(Vec(4, UInt(TENTRY_W.W)))
  for (g <- 0 until 4) {
    t2ReadIdx(g) := Mux(mPvalid && (mPid === g.U), mPidx, t2AllocIdx(g))
    t2RdEff(g) := Mux(t3TWe(g) && (t3TWaddr(g) === t2ReadIdx(g)), t3TWdata(g),
                  Mux(t3LastTWe(g) && (t3LastTWaddr(g) === t2ReadIdx(g)), t3LastTWdata(g),
                      t2RdEntry(g)))
  }

  // 分配候选
  val allocCand = WireDefault(VecInit(Seq.fill(4)(false.B)))
  for (g <- 0 until 4) {
    val freeOrNotUseful = !t2RdEff(g)(TENTRY_W - 1) || (t2RdEff(g)(1, 0) === 0.U)
    allocCand(g) := freeOrNotUseful && (if (g == 0) !mPvalid else !mPvalid || (mPid < g.U))
  }
  val allocAny = allocCand.asUInt.orR
  val allocSel = Mux(allocCand(0), 0.U, Mux(allocCand(1), 1.U, Mux(allocCand(2), 2.U, 3.U)))

  val provPred = mPctr(2)
  val provCorr = provPred === t2Taken
  val usefulChg = mPvalid && (provPred =/= mAlt)
  val uNew = Mux(!usefulChg, mPu,
             Mux(provCorr, Mux(mPu === 3.U, 3.U, mPu + 1.U),
                 Mux(mPu === 0.U, 0.U, mPu - 1.U)))
  val trainProvWeak = (mPctr === 3.U) || (mPctr === 4.U)
  val trainAltBetter = mPvalid && trainProvWeak && (provPred =/= mAlt) && (mAlt === t2Taken)
  val trainProvBetter = mPvalid && trainProvWeak && (provPred =/= mAlt) && (provPred === t2Taken)
  val providerEntryValid = t2RdEff(mPid)(TENTRY_W - 1)
  val providerTagMatch = providerEntryValid &&
    (t2RdEff(mPid)(TENTRY_W - 2, TENTRY_W - 1 - TAGE_TAG_W) === mPtag)

  // T2 写命令计算
  val baseWdataCalc = Mux(t2Taken,
    Mux(mBaseCtr === 3.U, 3.U, mBaseCtr + 1.U),
    Mux(mBaseCtr === 0.U, 0.U, mBaseCtr - 1.U))
  val tWaddrCalc = WireDefault(VecInit(t2AllocIdx))
  val tWdataCalc = WireDefault(VecInit(Seq.tabulate(4)(tk =>
    Cat(true.B, t2AllocTag(tk), Mux(t2Taken, 4.U(3.W), 3.U(3.W)), 0.U(2.W)))))
  val tWeCalc = WireDefault(VecInit(Seq.fill(4)(false.B)))
  val baseWeCalc = WireDefault(false.B)
  baseWeCalc := t2Valid
  when(t2Valid) {
    when(mPvalid && providerTagMatch) {
      tWeCalc(mPid) := true.B
      tWaddrCalc(mPid) := mPidx
      tWdataCalc(mPid) := Cat(true.B, mPtag,
        Mux(t2Taken, Mux(mPctr === 7.U, 7.U, mPctr + 1.U),
            Mux(mPctr === 0.U, 0.U, mPctr - 1.U)), uNew)
    }
    when(t2Mispred && allocAny && !(mPvalid && (allocSel === mPid))) {
      tWeCalc(allocSel) := true.B
    }.elsewhen(t2Mispred && !allocAny) {
      for (tk <- 0 until 4) {
        when(!mPvalid || (tk.U > mPid)) {
          when(t2RdEff(tk)(1, 0) =/= 0.U) {
            tWeCalc(tk) := true.B
            tWaddrCalc(tk) := t2AllocIdx(tk)
            tWdataCalc(tk) := Cat(t2RdEff(tk)(TENTRY_W - 1), t2RdEff(tk)(TENTRY_W - 2, 5), t2RdEff(tk)(4, 2), 0.U(2.W))
          }
        }
      }
    }
  }

  // ---- 主时序 ----
  when(reset.asBool) {
    t0Valid := false.B; t1Valid := false.B; t2Valid := false.B
    t3BaseWe := false.B; t3TWe := 0.U; t3LastTWe := 0.U
    t3BaseWaddr := 0.U; t3BaseWdata := 0.U
    for (pk <- 0 until 4) {
      t3TWaddr(pk) := 0.U; t3TWdata(pk) := 0.U
      t3LastTWaddr(pk) := 0.U; t3LastTWdata(pk) := 0.U
    }
    useAltOnNa := 0.U
    specGhr := 0.U; commitGhr := 0.U
    uqRptr := 0.U; uqWptr := 0.U; uqCount := 0.U
  }.otherwise {
    t3BaseWe := baseWeCalc; t3BaseWaddr := mBaseIdx; t3BaseWdata := baseWdataCalc
    t3LastTWe := t3TWe; t3TWe := tWeCalc.asUInt
    for (pk <- 0 until 4) {
      t3LastTWaddr(pk) := t3TWaddr(pk); t3LastTWdata(pk) := t3TWdata(pk)
      t3TWaddr(pk) := tWaddrCalc(pk); t3TWdata(pk) := tWdataCalc(pk)
    }
    when(t2Valid && trainAltBetter && (useAltOnNa =/= "hf".U)) { useAltOnNa := useAltOnNa + 1.U }
      .elsewhen(t2Valid && trainProvBetter && (useAltOnNa =/= 0.U)) { useAltOnNa := useAltOnNa - 1.U }

    when(io.cmtHistValid) { commitGhr := Cat(commitGhr(GHR_LEN - 2, 0), io.cmtHistTaken) }

    when(io.flush) {
      specGhr := Mux(io.cmtHistValid, Cat(commitGhr(GHR_LEN - 2, 0), io.cmtHistTaken), commitGhr)
    }.elsewhen(io.histRestore) {
      specGhr := Mux(io.histRestoreAppend,
        Cat(histCp(io.histRestoreId)(GHR_LEN - 2, 0), io.histRestoreTaken),
        histCp(io.histRestoreId))
    }.elsewhen(io.histUpdateValid) {
      specGhr := Cat(specGhr(GHR_LEN - 2, 0), io.histUpdateTaken)
    }

    when(enqueue) {
      uqPc(uqWptr) := io.trainPc
      uqTaken(uqWptr) := io.trainTaken
      uqMispred(uqWptr) := io.trainMispred
      uqMeta(uqWptr) := io.trainMeta
      uqGhr(uqWptr) := histCp(trainFtqId)
      uqWptr := (if (QD == 1) 0.U else uqWptr + 1.U)
    }
    when(dequeue) { uqRptr := (if (QD == 1) 0.U else uqRptr + 1.U) }
    uqCount := uqCountNext

    t0Valid := trainReadGrant && uqHeadMetaValid
    when(trainReadGrant) {
      t0Pc := uqHeadPc; t0Taken := uqHeadTaken; t0Mispred := uqHeadMispred
      t0Meta := uqHeadMeta; t0Ghr := uqHeadGhr
    }
    t1Valid := t0Valid
    when(t0Valid) {
      t1Taken := t0Taken; t1Mispred := t0Mispred; t1Meta := t0Meta
      for (pk <- 0 until 4) {
        t1AllocIdx(pk) := t0Hash(pk)._1; t1AllocTag(pk) := t0Hash(pk)._2
        t1RdEntry(pk) := tTrainRdata(pk)
      }
    }
    t2Valid := t1Valid
    when(t1Valid) {
      t2Taken := t1Taken; t2Mispred := t1Mispred; t2Meta := t1Meta
      for (pk <- 0 until 4) {
        t2AllocIdx(pk) := t1AllocIdx(pk); t2AllocTag(pk) := t1AllocTag(pk)
        t2RdEntry(pk) := t1RdEntry(pk)
      }
    }
  }

  // A repair restores the current FTQ slot while the speculative checkpoint
  // write targets the next, still-unallocated slot.  Allow that harmless
  // write so late predecode repair does not gate the RAM write enable.
  when(!reset.asBool && io.histCpSave && !io.flush) {
    histCp(io.histCpId) := specGhr
  }
  if (!sys.props.get("e91c.synthesis").contains("true")) {
    val refCp = Reg(Vec(FTQ_SIZE, UInt(GHR_LEN.W)))
    val refSeen = RegInit(VecInit(Seq.fill(FTQ_SIZE)(false.B)))
    when(io.histCpSave && io.histRestore) {
      assert(io.histCpId =/= io.histRestoreId, "TAGE repair overwrote its checkpoint")
    }
    when(!reset.asBool && io.histCpSave && !io.flush) {
      refCp(io.histCpId) := specGhr
      refSeen(io.histCpId) := true.B
    }
    for(id <- Seq(io.histRestoreId, trainFtqId)) {
      when(refSeen(id)) { assert(histCp(id) === refCp(id), "TAGE checkpoint storage mismatch") }
    }
  }
}


