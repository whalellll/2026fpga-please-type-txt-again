# -*- coding: utf-8 -*-
"""T1 正式 test 评估：第 3 局 IMG00908–IMG01042（135 帧，从未参与训练/模型选择）。

评估对象：冻结候选 v1 组合（ROI640 检测器 + RGB32 质量分类器）。
口径沿用候选包冻结评估器：conf 0.05、IoU 0.5、class-aware NMS IoU 0.6；
AP 积分直接调用 yolov5 7.0.14 的 compute_ap（与历史指标同口径）。

ROI 自动化路径：board 四角标注 -> 外接矩形(+pad, 默认 40px) -> 检测器 ROI。
真值：dataset/out LabelMe circle（+ dataset_corrections.json 叠加修正）。
归格：board 四角 -> 透视映射（geometry 模块）-> 圆心/检测中心吸附格点。

路线判定门槛（写进报告）：
  整盘完全正确率 >= 85% 且 black_pao / black_ma / red_ma mAP@0.5 各 >= 0.5
  -> "roi640_v1" 路线；否则 -> "contract_yolov5n" 退回路线。

用法：
  python test_eval_t1.py --dataset <root> --v1-release <dir> --out <dir> [--limit N]
其中 <root> 含 in/ out/ board/（board 若缺省用交接包内的预标目录）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))            # src/（geometry 包）
sys.path.insert(0, str(HERE.parent.parent / "v1_release"))  # 冻结候选推理模块

from geometry.board_perspective import geometry_from_corners  # noqa: E402
from geometry.piece_fit import assign_grid  # noqa: E402
from geometry.roi import quad_to_roi  # noqa: E402

TEST_START, TEST_END = 908, 1042
CLASS_NAMES = ["red_shuai", "red_shi", "red_xiang", "red_ma", "red_ju", "red_pao",
               "red_bing", "black_jiang", "black_shi", "black_xiang", "black_ma",
               "black_ju", "black_pao", "black_zu"]
WEAK_CLASSES = ["black_pao", "black_ma", "red_ma"]

CONF = 0.05
IOU = 0.5


def load_corrections(path: Path):
    """返回 {frame_stem: [correction,...]}，文件不存在返回空。"""
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for c in doc.get("corrections", []):
        out.setdefault(c["frame"], []).append(c)
    return out


def load_gt_piece_labels(out_dir: Path, idx: int):
    """dataset/out 的 LabelMe circle -> [(label, cx, cy, r)]（未加修正）。"""
    stem = "IMG%05d" % idx
    doc = json.loads((out_dir / (stem + ".json")).read_text(encoding="utf-8"))
    pieces = []
    for sh in doc.get("shapes", []):
        if sh.get("shape_type") != "circle":
            continue
        (cx, cy), (ex, ey) = sh["points"][0], sh["points"][1]
        r = float(np.hypot(ex - cx, ey - cy))
        pieces.append({"label": sh["label"], "cx": float(cx), "cy": float(cy), "r": r})
    return pieces


def apply_grid_corrections(corrections, stem, geom, pieces):
    """按格修正叠加（class_fixed 按格+原标匹配；missing_piece_added 由几何格点合成）。

    支持两种条目格式：grid 键值式（第 3 局 T1 复核）与 shape_index 式（第 2 局
    37 帧复核，仅文档用途，test 局不含）。
    """
    from geometry.piece_fit import assign_grid
    centers = np.array([[p["cx"], p["cy"]] for p in pieces], dtype=float)
    gp, res, ok = (assign_grid(geom, centers) if len(centers)
                   else (np.zeros((0, 2), int), np.zeros(0), np.zeros(0, bool)))
    for c in corrections.get(stem, []):
        if c["type"] == "class_fixed":
            cell = tuple(c.get("grid") or c.get("corrected", {}).get("grid") or [])
            old = c["original"]["label"] if isinstance(c["original"], dict) else None
            if cell:
                for i, p in enumerate(pieces):
                    if ok[i] and tuple(gp[i]) == cell and (old is None or p["label"] == old):
                        p["label"] = c["corrected"]["label"]
                        break
            else:  # 旧格式：shape_index
                si = c["original"].get("shape_index")
                if isinstance(si, int) and 0 <= si < len(pieces):
                    pieces[si]["label"] = c["corrected"]["label"]
        elif c["type"] == "missing_piece_added":
            cc = c["corrected"]
            cell = tuple(cc.get("grid") or [])
            if cell:
                pt = geom.points().reshape(10, 9, 2)[cell[1], cell[0]]
                r = float(np.median([p["r"] for p in pieces])) if pieces else 25.0
                cx, cy = cc.get("center_px", [float(pt[0]), float(pt[1])])
                pieces.append({"label": cc["label"], "cx": float(cx), "cy": float(cy),
                               "r": float(cc.get("radius_px", r))})
    return pieces


def board_quad(board_dir: Path, idx: int):
    stem = "IMG%05d" % idx
    doc = json.loads((board_dir / (stem + ".json")).read_text(encoding="utf-8"))
    sh = doc["shapes"][0]
    assert sh["label"] == "board" and sh["shape_type"] == "polygon" and len(sh["points"]) == 4
    return np.array(sh["points"], dtype=float)


def gt_grid_map(geom, pieces):
    """GT 圆心 -> {(col,row): label}；同一格多点（异常）时按第一个。"""
    cells = {}
    centers = np.array([[p["cx"], p["cy"]] for p in pieces], dtype=float)
    gp, res, ok = assign_grid(geom, centers)
    for (c, r), lab, good in zip(gp, [p["label"] for p in pieces], ok):
        if (int(c), int(r)) not in cells:
            cells[(int(c), int(r))] = (lab, bool(good))
    return cells, float(res.max()) if len(res) else 0.0


def pred_grid_map(geom, dets):
    centers = np.array([[(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0] for b in dets], dtype=float)
    if not len(centers):
        return {}
    gp, res, ok = assign_grid(geom, centers)
    cells = {}
    for (c, r), cls, good in zip(gp, dets[:, 5].astype(int), ok):
        key = (int(c), int(r))
        if key not in cells or good:
            cells[key] = int(cls)
    return cells


def box_iou_matrix(a, b):
    """a(N,4) x b(M,4) IoU 矩阵。"""
    if not len(a) or not len(b):
        return np.zeros((len(a), len(b)))
    ax1, ay1, ax2, ay2 = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
    bx1, by1, bx2, by2 = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
    ix1 = np.maximum(ax1[:, None], bx1[None])
    iy1 = np.maximum(ay1[:, None], by1[None])
    ix2 = np.minimum(ax2[:, None], bx2[None])
    iy2 = np.minimum(ay2[:, None], by2[None])
    iw = np.clip(ix2 - ix1, 0, None)
    ih = np.clip(iy2 - iy1, 0, None)
    inter = iw * ih
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / np.clip(area_a[:, None] + area_b[None] - inter, 1e-9, None)


def compute_ap_yolov5(tp, conf, n_gt):
    """与冻结评估器同口径：yolov5 7.0.14 utils.metrics.compute_ap。"""
    from yolov5.utils.metrics import compute_ap as yolo_compute_ap
    if n_gt == 0:
        return float("nan")
    order = np.argsort(-conf)
    tp = tp[order]
    i = np.float32(np.arange(1, len(tp) + 1))
    fpc = (1 - tp).cumsum(0)
    tpc = tp.cumsum(0)
    recall = tpc / (n_gt + 1e-16)
    precision = tpc / (tpc + fpc)
    ap, _, _ = yolo_compute_ap(recall, precision)
    return float(ap)


def evaluate(detector, in_dir, out_dir, board_dir, corrections, limit=None,
             detector_size=640, roi_pad=40.0):
    import cv2
    rows = []
    all_dets = {c: {"tp": [], "conf": [], "n_gt": 0} for c in range(14)}
    frames = list(range(TEST_START, TEST_END + 1))
    if limit:
        frames = frames[:limit]
    for idx in frames:
        stem = "IMG%05d" % idx
        img = cv2.imread(str(in_dir / (stem + ".PNG")))
        assert img is not None, "missing image %s" % stem
        quad = board_quad(board_dir, idx)
        geom = geometry_from_corners(quad, confidence=1.0)
        roi = quad_to_roi(quad, pad=roi_pad)
        pieces = load_gt_piece_labels(out_dir, idx)
        pieces = apply_grid_corrections(corrections, stem, geom, pieces)
        gt_cells, gt_res_max = gt_grid_map(geom, pieces)
        t0 = time.perf_counter()
        pred = detector.predict(img, roi)
        dt = time.perf_counter() - t0
        usable = pred[pred[:, 4] >= CONF]
        pred_cells = pred_grid_map(geom, usable)
        # 整盘/格统计（90 格口径含空格：错一格扣一格）
        n_piece_correct = 0
        errors = []
        all_cells = set(gt_cells) | set(pred_cells)
        for cell in all_cells:
            g = gt_cells.get(cell)
            p = pred_cells.get(cell)
            g_lab = CLASS_NAMES.index(g[0]) if g else None
            p_lab = p
            if g_lab is not None and p_lab is not None and g_lab == p_lab:
                n_piece_correct += 1
            elif g_lab is not None and p_lab is None:
                errors.append({"cell": list(cell), "type": "miss", "gt": CLASS_NAMES[g_lab]})
            elif g_lab is None and p_lab is not None:
                errors.append({"cell": list(cell), "type": "false", "pred": CLASS_NAMES[p_lab]})
            else:
                errors.append({"cell": list(cell), "type": "wrong_class",
                               "gt": CLASS_NAMES[g_lab], "pred": CLASS_NAMES[p_lab]})
        board_exact = int(not errors)
        n_cell_correct_90 = 90 - len(errors)
        rows.append({
            "frame": stem, "n_gt": len(gt_cells), "n_pred_cells": len(pred_cells),
            "piece_cell_correct": n_piece_correct, "cell_correct_90": n_cell_correct_90,
            "board_exact": board_exact, "infer_ms": round(dt * 1000, 1),
            "gt_grid_residual_max_cell": round(gt_res_max, 4),
            "errors": errors,
        })
        # mAP 累积（box 级，IoU 0.5，class-aware 贪心匹配：置信度降序）
        gt_boxes_by_cls = {c: [] for c in range(14)}
        for p in pieces:
            c = CLASS_NAMES.index(p["label"])
            x1, y1 = p["cx"] - p["r"], p["cy"] - p["r"]
            x2, y2 = p["cx"] + p["r"], p["cy"] + p["r"]
            gt_boxes_by_cls[c].append([x1, y1, x2, y2])
        for c in range(14):
            gt_b = np.array(gt_boxes_by_cls[c], dtype=float).reshape(-1, 4)
            all_dets[c]["n_gt"] += len(gt_b)
            mask = usable[:, 5].astype(int) == c
            pb = usable[mask][:, :4]
            pc = usable[mask][:, 4]
            if not len(pb):
                continue
            if len(gt_b):
                iou = box_iou_matrix(pb, gt_b)
                order = np.argsort(-pc)
                taken = np.zeros(len(gt_b), dtype=bool)
                tp = np.zeros(len(pb), dtype=np.float32)
                for i in order:
                    j = int(np.argmax(iou[i]))
                    if iou[i, j] >= IOU and not taken[j]:
                        tp[i] = 1.0
                        taken[j] = True
                all_dets[c]["tp"].extend(tp.tolist())
                all_dets[c]["conf"].extend(pc.tolist())
            else:
                all_dets[c]["tp"].extend([0.0] * len(pb))
                all_dets[c]["conf"].extend(pc.tolist())
    return rows, all_dets


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, required=True, help="含 in/ out/ 的数据集根目录")
    ap.add_argument("--board-dir", type=Path, default=None, help="board 预标目录（默认交接包内）")
    ap.add_argument("--v1-release", type=Path, default=HERE.parent.parent / "v1_release")
    ap.add_argument("--corrections", type=Path,
                    default=HERE.parent.parent / "deliverables" / "board_detect_v2_round1" / "dataset_corrections.json")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--detector-size", type=int, default=640, choices=[320, 640])
    ap.add_argument("--roi-pad", type=float, default=40.0)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    board_dir = args.board_dir
    if board_dir is None:
        # 基线 = tar 版预标（通过 board_labels_sha256.txt 校验，见交接报告 §3）
        board_dir = (HERE.parent.parent / "训练交付包_新方案_20261018" /
                     "训练交付包_新方案_20261018" / "board")
    in_dir, out_dir = args.dataset / "in", args.dataset / "out"
    assert in_dir.is_dir() and out_dir.is_dir(), "dataset in/out missing"
    assert board_dir.is_dir(), "board dir missing"

    # 冻结候选完整性先校验（verify_package 模块体在 import 时执行并打印 PACKAGE_OK）
    sys.path.insert(0, str(args.v1_release))
    import contextlib  # noqa: E402
    import importlib  # noqa: E402
    from io import StringIO  # noqa: E402
    buf = StringIO()
    with contextlib.redirect_stdout(buf):
        importlib.import_module("verify_package")
    assert "PACKAGE_OK" in buf.getvalue(), "v1 verify_package.py failed:\n" + buf.getvalue()

    import torch  # noqa: E402
    from live_two_stage import TwoStageDetector  # noqa: E402
    det = TwoStageDetector(args.v1_release / "weights" / ("detector_roi%d.pt" % args.detector_size),
                           args.v1_release / "weights" / "piece_quality_rgb32.pt",
                           input_size=args.detector_size)
    assert torch.cuda.is_available(), "v1 组合需要 CUDA（冻结候选口径）"

    corrections = load_corrections(args.corrections)
    rows, all_dets = evaluate(det, in_dir, out_dir, board_dir, corrections,
                              limit=args.limit, detector_size=args.detector_size,
                              roi_pad=args.roi_pad)

    args.out.mkdir(parents=True, exist_ok=True)
    n_frames = len(rows)
    board_exact = sum(r["board_exact"] for r in rows)
    piece_total = sum(r["n_gt"] for r in rows)
    piece_ok = sum(r["piece_cell_correct"] for r in rows)
    cell_total = 90 * n_frames
    cell_ok = sum(r["cell_correct_90"] for r in rows)

    per_class = {}
    aps = []
    for c, name in enumerate(CLASS_NAMES):
        d = all_dets[c]
        tp = np.array(d["tp"], dtype=np.float32)
        conf = np.array(d["conf"], dtype=np.float64)
        ap = compute_ap_yolov5(tp, conf, d["n_gt"]) if d["n_gt"] else float("nan")
        per_class[name] = {"ap50": None if ap != ap else round(ap, 6),
                           "n_gt": d["n_gt"], "n_pred": int(len(tp)),
                           "n_tp": int(tp.sum())}
        if ap == ap:
            aps.append(ap)
    mAP = float(np.mean(aps)) if aps else float("nan")

    weak = {w: per_class[w]["ap50"] for w in WEAK_CLASSES}
    whole_board_rate = board_exact / n_frames if n_frames else 0.0
    weak_ok = all(v is not None and v >= 0.5 for v in weak.values())
    route = "roi640_v1" if (whole_board_rate >= 0.85 and weak_ok) else "contract_yolov5n"

    summary = {
        "task": "T1 formal test evaluation",
        "test_range": ["IMG%05d" % TEST_START, "IMG%05d" % TEST_END],
        "n_frames": n_frames,
        "detector": "detector_roi%d + piece_quality_rgb32 (frozen v1)" % args.detector_size,
        "protocol": {"conf": CONF, "iou": IOU, "nms_iou": 0.6, "class_aware": True,
                     "ap_integration": "yolov5 7.0.14 compute_ap",
                     "roi": "board quad bounding rect + pad %.0f px" % args.roi_pad,
                     "grid": "board quad perspective mapping (geometry module)"},
        "corrections_applied": sorted(corrections.keys()),
        "whole_board_exact": {"correct": board_exact, "total": n_frames,
                              "rate": round(whole_board_rate, 6)},
        "piece_cell": {"correct": piece_ok, "total": piece_total,
                       "rate": round(piece_ok / max(1, piece_total), 6)},
        "cell90": {"correct": cell_ok, "total": cell_total,
                   "rate": round(cell_ok / max(1, cell_total), 6)},
        "mAP50": round(mAP, 6),
        "per_class_ap50": per_class,
        "weak_classes": weak,
        "route_verdict": {
            "route": route,
            "gate": {"whole_board_min": 0.85, "weak_ap50_min": 0.5,
                     "whole_board_actual": round(whole_board_rate, 6),
                     "weak_actual": weak},
            "rationale": ("整盘 %s %.2f%%，三弱类 %s；门槛 85%%/0.5 -> %s"
                          % (">=" if whole_board_rate >= 0.85 else "<",
                             whole_board_rate * 100, weak, route)),
        },
    }
    (args.out / "metrics_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(args.out / "per_image_metrics.csv", "w", encoding="utf-8") as f:
        f.write("frame,n_gt,n_pred_cells,piece_cell_correct,cell_correct_90,"
                "board_exact,infer_ms,gt_grid_residual_max_cell,n_errors\n")
        for r in rows:
            f.write("%s,%d,%d,%d,%d,%d,%.1f,%.4f,%d\n" % (
                r["frame"], r["n_gt"], r["n_pred_cells"], r["piece_cell_correct"],
                r["cell_correct_90"], r["board_exact"], r["infer_ms"],
                r["gt_grid_residual_max_cell"], len(r["errors"])))
    (args.out / "errors_detail.json").write_text(
        json.dumps([{"frame": r["frame"], "errors": r["errors"]} for r in rows if r["errors"]],
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary["route_verdict"], ensure_ascii=False, indent=1))
    print("mAP@0.5 = %.6f, whole-board %d/%d" % (mAP, board_exact, n_frames))
    print("report ->", args.out)


if __name__ == "__main__":
    main()
